"""The playback state machine.

Owns the play queue, the media engine and the online resolution pipeline.  The
UI only talks to this object; it never touches ``QMediaPlayer`` directly.

Flow for one track
------------------
1. ``play_rows`` / ``play_next`` / ``end_of_media`` decide *which* track.
2. ``_load(track)`` validates the source: a local file must exist, an online
   track is resolved through the Node runtime, then registered with the local
   audio proxy so seeking and caching work like a normal file.
3. ``PlaybackEngine`` plays the resulting URL.
4. Failures either fall back to another online source (same title/artist) or
   advance to the next queue item, always with a visible status message.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.logging_setup import get_logger
from ..model.track import Track
from ..online import models
from ..online.client import OnlineSourceClient
from ..online import health
from ..online.matching import (
    AUTO_MARGIN,
    AUTO_MIN_SCORE,
    CANDIDATE_MIN_SCORE,
    MatchCandidate,
    normalize_text,
    rank_candidates,
)
from ..online.models import SourceInfo, build_sources, runtime_track, tracks_from_items
from ..online.proxy import AudioProxy
from ..services import source_memory
from . import replaygain
from .engine import PlaybackEngine
from .queue import PlayQueue

log = get_logger("audio.controller")

MAX_CONSECUTIVE_FAILURES = 3
RESUME_RECHECK_MS = 240_000
#: Resolved stream URLs are reused for this long; re-resolving costs a network
#: round trip and is the main delay when skipping back and forth.
RESOLVE_CACHE_TTL_MS = 120_000       # re-resolve online streams after a long pause
FALLBACK_MAX = 4                  # how many other sources to try
#: Some plugins only expose one quality; try the common tiers before giving up.
QUALITY_CHAIN = ("standard", "higher", "320k")
#: 查找磁盘缓存时依次尝试的音质档：插件实际返回的档位不一定等于请求档位，
#: 只按请求档位查会让「已经缓存过」的歌永远查不到。
CACHE_QUALITY_TIERS = ("standard", "higher", "exhigh", "lossless", "320k", "128k")
FALLBACK_SEARCH_TIMEOUT_MS = 14000
FALLBACK_MAX_CANDIDATES = 3


def _alias_payload(alias: dict[str, Any]) -> dict[str, Any]:
    """Return the alias' own payload, never the payload of the original source.

    ``source_memory`` only started persisting ``raw`` in this version; older
    entries kept just the mapping, and reusing the original track's payload is
    exactly what made a NetEase plugin receive a Kugou song id.  A payload that
    cannot be proven to belong to the remembered source is dropped and the
    runtime builds a minimal, internally consistent request instead.
    """
    raw = alias.get("raw")
    source_id = str(alias.get("source_id") or "")
    remote_id = str(alias.get("remote_id") or "")
    if isinstance(raw, dict) and raw and models.payload_matches_source(
        raw, source_id, remote_id
    ):
        return dict(raw)
    return {}


def _track_from_alias(track: Track, alias: dict[str, Any]) -> Track:
    """A resolve-only copy of ``track`` pointing at the remembered candidate.

    The queue keeps showing the original row; only the stream comes from the
    remembered source, so artwork/artist text in the UI stays stable.
    """
    return Track(
        id=track.id,
        kind=track.kind,
        title=str(alias.get("title") or track.title),
        artist=str(alias.get("artist") or track.artist),
        album=str(alias.get("album") or track.album),
        duration_ms=int(alias.get("duration_ms") or track.duration_ms),
        source_id=str(alias.get("source_id") or ""),
        source_name=str(alias.get("source_name") or track.source_name),
        remote_id=str(alias.get("remote_id") or ""),
        artwork_url=str(alias.get("artwork_url") or track.artwork_url),
        raw=_alias_payload(alias),
    )


@dataclass(slots=True)
class ResolvedStream:
    url: str
    cache_url: str
    mime: str
    quality: str
    expires_at: float
    headers: dict[str, str]
    source_id: str


@dataclass(slots=True)
class PreloadedStream:
    """A prefetched URL together with the exact identity it was resolved for.

    Storing a bare URL was the reason a stale preload could play a different
    source (or a different song) than the one the database binding demands.
    """

    source_id: str
    remote_id: str
    quality: str
    revision: int
    request_id: int
    request: dict[str, Any]
    data: dict[str, Any]


@dataclass(slots=True)
class PlaybackIdentity:
    """*Which* recording this playback session must use, and at which revision.

    ``bound`` means the database already owns this song's source; ``alias_used``
    means only the legacy JSON memory had an opinion.  The distinction is what
    keeps old aliases from ever overriding a formal binding.
    """

    target: Track
    revision: int = 0
    bound: bool = False
    alias_used: bool = False
    alias_source: str = ""

    @property
    def source_id(self) -> str:
        return self.target.source_id

    @property
    def remote_id(self) -> str:
        return self.target.remote_id


class PlayerController(QObject):
    track_changed = Signal(object)      # Track | None
    active_source_changed = Signal(str)  # label of the source that played
    track_started = Signal(object)      # Track, when audio actually begins
    state_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    volume_changed = Signal(float)
    muted_changed = Signal(bool)
    queue_changed = Signal()
    shuffle_changed = Signal(bool)
    repeat_changed = Signal(str)
    loading_changed = Signal(bool, str)  # busy, hint text
    status_message = Signal(str)         # transient toast text
    error_message = Signal(str)
    sources_changed = Signal(list)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        volume: float = 0.72,
        engine: PlaybackEngine | None = None,
        client: OnlineSourceClient | None = None,
        proxy: AudioProxy | None = None,
        binding: object | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine or PlaybackEngine(self)
        self.client = client or OnlineSourceClient(self)
        self.proxy = proxy or AudioProxy()
        self.queue = PlayQueue(self)

        self._volume = max(0.0, min(1.0, volume))
        self._muted = False
        self._track: Track | None = None
        self._duration = 0
        self._position = 0
        self._busy = False
        self._resolve_generation = 0
        self._resolve_request_id = 0
        #: 每次 ``_load()`` 开启新的播放会话；attempt 带着它，迟到的确认回调
        #: 就不可能把「上一首/上一次播放」的成功算到当前会话头上。
        self._session = 0
        #: 上一次收到的播放位置，用于区分「真实推进」与 seek 造成的跳变。
        self._last_position_value = 0
        # Remembered source is only trusted once audio really starts: a source
        # can return a URL that then 404s on the stream, and writing it early
        # makes every later play retry a dead alias.
        self._memory_pending: tuple[Track, Track] | None = None
        self._failures = 0
        self._pending_resume = 0
        self._paused_at = 0.0
        self._paused_pending = False
        self._active_online: Track | None = None
        self._fallback_tried: set[str] = set()
        self._sources: list[SourceInfo] = []
        self._quality = "standard"
        self._quality_index = 0
        self._resolve_cache: dict[str, tuple[float, dict]] = {}
        self._preloaded: dict[str, PreloadedStream] = {}
        self._preload_requests: dict[str, tuple[int, int]] = {}
        #: 预加载世代；手动换源/切歌/绑定变化时自增，让迟到的回调作废。
        self._preload_epoch = 0
        self._replaygain: str = "off"
        self._online_fallback = True
        #: 缓存优先播放开关（settings: cache.enabled）；关闭时完全不看磁盘缓存。
        self._cache_enabled = True
        #: 启动恢复阶段：队列的 current_changed 不得顺手发起在线解析。
        self._restoring = False
        #: 已恢复但尚未 load 的会话；用户第一次按播放才真正开流。
        self._restored_pending = False
        # 绑定服务由 app 注入；None 时退化为 1.3.x 的 alias/回退行为。
        self._binding = binding
        self._attempt: dict | None = None

        self.engine.set_volume(self._volume)
        self.engine.position_changed.connect(self._on_position)
        self.engine.duration_changed.connect(self._on_duration)
        self.engine.state_changed.connect(self._on_state)
        self.engine.end_of_media.connect(self._on_end_of_media)
        self.engine.error_occurred.connect(self._on_engine_error)
        self.engine.buffering_changed.connect(self._on_buffering)

        self.client.sources_changed.connect(self._on_sources)
        self.client.failure.connect(self._on_client_failure)

        self.queue.current_changed.connect(self._on_queue_current_changed)
        self.queue.changed.connect(self.queue_changed)
        self.queue.mode_changed.connect(self._on_mode_changed)
        self._last_shuffle = self.queue.shuffle
        self._last_repeat = self.queue.repeat
        self._silent_current = False

    # ------------------------------------------------------------ properties
    @property
    def current_track(self) -> Track | None:
        return self._track

    @property
    def position(self) -> int:
        return self._position

    @property
    def duration(self) -> int:
        return self._duration or (self._track.duration_ms if self._track else 0)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def state(self) -> str:
        """UI-facing transport state.

        While an online resource is being resolved/开流 the engine has not been
        touched yet, so reporting ``engine.state`` alone made the UI claim
        "stopped" while it was really loading — and, combined with the old
        no-op pause, left the controls dead after a failed resolve.
        """
        if self._busy:
            return "loading"
        if self._paused_pending and self.engine.state == "stopped":
            return "paused"
        return self.engine.state

    @property
    def _quality_chain(self) -> tuple[str, ...]:
        chain = [self._quality or "standard"]
        for tier in QUALITY_CHAIN:
            if tier not in chain:
                chain.append(tier)
        return tuple(chain)

    @property
    def current(self):
        """当前播放曲目（队列中的 Track）。"""
        return self.queue.current

    @property
    def has_next(self) -> bool:
        return self.queue.current_row < self.queue.count - 1 or self.queue.repeat == "all"

    @property
    def shuffle(self) -> bool:
        return self.queue.shuffle

    @property
    def repeat(self) -> str:
        return self.queue.repeat

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def sources(self) -> list[SourceInfo]:
        return list(self._sources)

    def is_playing(self) -> bool:
        return self.engine.is_playing()

    def playable_sources(self) -> list[SourceInfo]:
        return [source for source in self._sources if source.can_play]

    def _source_is_playable(self, source_id: str) -> bool:
        return any(source.id == source_id and source.can_play for source in self._sources)

    # -------------------------------------------------------------- settings
    def configure(self, *, volume: float | None = None, quality: str = "standard",
                  online_fallback: bool = True, shuffle: bool | None = None,
                  repeat: str | None = None, replaygain: str | None = None,
                  muted: bool | None = None,
                  cache_enabled: bool | None = None) -> None:
        if replaygain is not None:
            self._replaygain = str(replaygain or "off")
        if volume is not None:
            self.set_volume(volume, emit=True)
        if muted is not None:
            self.set_muted(bool(muted))
        if cache_enabled is not None:
            self._cache_enabled = bool(cache_enabled)
        self._quality = quality or "standard"
        self._online_fallback = bool(online_fallback)
        if shuffle is not None:
            self.queue.set_shuffle(bool(shuffle))
        if repeat is not None:
            self.queue.set_repeat(repeat)

    def load_queue_state(self, payload: dict[str, Any]) -> int:
        """Restore a saved queue; returns the restored position in ms."""
        position = 0
        try:
            self.queue.restore(payload)
            position = int(payload.get("position_ms") or 0) if isinstance(payload, dict) else 0
        except Exception:
            log.exception("restore queue failed")
        return position

    def refresh_track(self, track: Track) -> None:
        """来源替换后，把队列与当前曲目里的旧对象换成新记录。

        手动换源会改写正式绑定：任何为这首歌排队的预加载/播放尝试都基于旧
        身份，必须立刻作废，否则迟到的回调会把旧来源又播回来。
        """

        self.queue.replace_track(track)
        self._invalidate_preloads()
        if self._attempt is not None and self._attempt.get("track_id") == track.id:
            self._attempt = None
        if self._track is not None and self._track.id == track.id:
            self._track = track
            self.track_changed.emit(track)

    # -------------------------------------------------------------- restore
    def begin_restore(self) -> None:
        """标记「正在从会话恢复队列」，期间队列换 current 不得触发加载/解析。"""
        self._restoring = True

    def end_restore(self) -> None:
        self._restoring = False

    def restore_current(self, position_ms: int = 0, *, autoplay: bool = False) -> None:
        """恢复上次的当前曲目。

        默认**不加载、不解析、不播放**：启动阶段音源可能还没起来，提前
        resolve 会失败并触发自动跳歌。只把歌曲、时长和进度摆好，用户按下
        播放时再由 ``play()/resume()`` 从该进度真正开流。
        """
        track = self.queue.current
        if track is None:
            return
        position = max(0, int(position_ms))
        if track.duration_ms:
            position = min(position, max(0, int(track.duration_ms) - 1000))
        if autoplay:
            self._load(track, position=position, autoplay=True)
            return
        self._prime_restored(track, position)

    def _prime_restored(self, track: Track, position: int) -> None:
        self._set_busy(False)
        self._paused_pending = False
        self._memory_pending = None
        self._session += 1
        self._attempt = None
        self._last_position_value = 0
        self._invalidate_preloads()
        self._restored_pending = True
        self._track = track
        self._position = int(position)
        self._pending_resume = int(position)
        self._duration = track.duration_ms or 0
        self._active_online = track if track.is_online else None
        self.track_changed.emit(track)
        self.duration_changed.emit(self._duration)
        self.position_changed.emit(self._position)
        self.state_changed.emit("stopped")

    # ------------------------------------------------------------ transport
    def play_tracks(self, tracks: Iterable[Track], start_index: int = 0, *, context: str = "") -> None:
        items = [track for track in tracks if track is not None]
        if not items:
            return
        start_index = max(0, min(start_index, len(items) - 1))
        self._failures = 0
        self._silent_current = True
        try:
            self.queue.set_tracks(items, start_index, context=context)
        finally:
            self._silent_current = False
        self._play_current(reset_position=True)

    def play_track(self, track: Track, *, context: str = "") -> None:
        self.play_tracks([track], 0, context=context)

    def play_rows(self, tracks: Iterable[Track], rows: Iterable[int], *, context: str = "") -> None:
        items = list(tracks)
        row_list = [row for row in rows if 0 <= row < len(items)]
        if not row_list:
            return
        self.play_tracks(items, row_list[0], context=context)

    def enqueue(self, tracks: Iterable[Track], *, play_now: bool = False) -> int:
        items = [track for track in tracks if track is not None]
        if not items:
            return 0
        self.queue.append(items)
        if play_now and self._track is None:
            self._play_current(reset_position=True)
        return len(items)

    def play_next_in_queue(self, tracks: Iterable[Track]) -> int:
        items = [track for track in tracks if track is not None]
        if not items:
            return 0
        self.queue.insert_next(items)
        return len(items)

    def toggle(self) -> None:
        if self._track is None:
            if self.queue.count:
                self._play_current(reset_position=True)
            return
        if self._busy or self.engine.state == "loading":
            # a pending stream counts as "playing" for the user: pressing the
            # button must cancel it, not queue another resolve
            self.pause()
            return
        if self.engine.state == "playing" or self.engine.is_playing_actual:
            self.pause()
        else:
            self.resume()

    def play(self) -> None:
        if self._track is None:
            if self.queue.count:
                self._play_current(reset_position=True)
            return
        if self._restored_pending:
            # 恢复的会话第一次按下播放：从保存的进度真正开流。
            self._load(self._track, position=self._position, autoplay=True)
            return
        if self.engine.state == "paused":
            self.resume()
        elif self.engine.state in ("stopped", "error"):
            self._load(self._track, position=self._position, autoplay=True)

    def pause(self) -> None:
        """Pause playback, including a stream that is still resolving/buffering.

        Bug fix (round 1, BUG-02): previously this silently did nothing unless
        the engine was already ``playing``. When an online resolve or proxy
        fetch failed, the controller stayed ``loading`` for ever and the
        transport control looked dead (the user's "can't pause/stop NetEase").
        """
        if self.engine.state == "playing" or self.engine.is_playing_actual:
            self._paused_at = time.monotonic()
            self.engine.pause()
            return
        if self.engine.state == "loading" or self._busy:
            self._paused_at = time.monotonic()
            # invalidate the in-flight resolve so a late answer cannot start
            # playback behind the user's back
            self._next_generation()
            self._attempt = None
            self._set_busy(False)
            self._paused_pending = True
            self.engine.halt_pending()
            self.state_changed.emit("paused")

    def resume(self) -> None:
        if self._track is None:
            return
        if self._restored_pending:
            self._load(self._track, position=self._position, autoplay=True)
            return
        long_pause = (
            self._paused_at > 0
            and (time.monotonic() - self._paused_at) * 1000 > RESUME_RECHECK_MS
            and self._track.is_online
        )
        self._paused_pending = False
        if self.engine.state == "paused" and not long_pause and self.engine.source:
            self._paused_at = 0.0
            self.engine.play()
            return
        if long_pause:
            # Online URLs expire; re-resolve and continue where the user left.
            self._load(self._track, position=self._position, autoplay=True, force_resolve=True)
            return
        self._load(self._track, position=self._position, autoplay=True)

    def stop(self) -> None:
        self._next_generation()
        self._attempt = None
        self._invalidate_preloads()
        self._paused_pending = False
        self._set_busy(False)
        # 停止后不再有「正在播放」的缓存条目：让容量清理可以回收它。
        try:
            self.proxy.note_playing(None)
        except Exception:  # noqa: BLE001 - 代理替身可能没有该方法
            log.debug("clear playing cache token failed", exc_info=True)
        self.engine.stop()
        self._position = 0
        self.position_changed.emit(0)
        self.state_changed.emit("stopped")

    def next(self, *, auto: bool = False) -> None:
        if not self.queue.count:
            return
        # The queue emits ``current_changed`` while it advances; loading there
        # *and* here would resolve the same track twice (and spawn two online
        # requests).  Suppress the signal-driven load and do one explicit load.
        self._silent_current = True
        try:
            track = self.queue.next_track(auto=auto)
        finally:
            self._silent_current = False
        if track is None:
            return
        self._play_current(reset_position=True)

    def previous(self, *, auto: bool = False) -> None:
        if not self.queue.count:
            return
        if not auto and self._position > 4000:
            self.seek(0)
            return
        self._silent_current = True
        try:
            track = self.queue.previous_track(auto=auto)
        finally:
            self._silent_current = False
        if track is None:
            return
        self._play_current(reset_position=True)

    def seek(self, ms: int) -> None:
        target = max(0, int(ms))
        if self._restored_pending and self.engine.state == "stopped":
            # 还没开流：只改保存的进度，等用户按播放时从这里开始。
            self._position = target
            self._pending_resume = target
            self.position_changed.emit(target)
            return
        self._position = target
        self.engine.seek(self._position)
        self.position_changed.emit(self._position)

    def skip_by(self, seconds: int) -> None:
        self.seek(self._position + seconds * 1000)

    # ---------------------------------------------------------------- volume
    def set_volume(self, value: float, *, emit: bool = True) -> None:
        self._volume = max(0.0, min(1.0, float(value)))
        self.engine.set_volume(self._volume)
        if emit:
            self.volume_changed.emit(self._volume)

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self.engine.set_muted(self._muted)
        self.muted_changed.emit(self._muted)

    def toggle_mute(self) -> None:
        self.set_muted(not self._muted)

    # ----------------------------------------------------------------- modes
    def toggle_shuffle(self) -> None:
        self.queue.toggle_shuffle()

    def set_shuffle(self, value: bool) -> None:
        self.queue.set_shuffle(bool(value))

    def cycle_repeat(self) -> None:
        self.queue.cycle_repeat()

    def set_repeat(self, mode: str) -> None:
        self.queue.set_repeat(mode)

    # ---------------------------------------------------------------- queue
    def remove_rows(self, rows: Iterable[int]) -> None:
        current = self._track
        self.queue.remove_rows(list(rows))
        remaining = {track.id for track in self.queue.items}
        if current is not None and current.id not in remaining:
            self.stop()
            self._track = None
            self.track_changed.emit(None)
            if self.queue.count:
                self._play_current(reset_position=True)

    def clear_queue(self) -> None:
        self.stop()
        self.queue.clear()
        self._track = None
        self.track_changed.emit(None)

    def move_row(self, from_row: int, to_row: int) -> None:
        self.queue.move_row(from_row, to_row)

    # ------------------------------------------------------------- internals
    def _set_busy(self, busy: bool, hint: str = "") -> None:
        self._busy = busy
        self.loading_changed.emit(busy, hint)

    def _next_generation(self) -> int:
        self._resolve_generation += 1
        return self._resolve_generation

    def _invalidate_preloads(self, keep_track_id: str | None = None) -> None:
        """作废预加载及其请求；``keep_track_id`` 的已存结果保留（马上要用）。"""

        self._preload_epoch += 1
        for track_id in list(self._preloaded):
            if keep_track_id and track_id == keep_track_id:
                continue
            self._preloaded.pop(track_id, None)
        cancel = getattr(self.client, "cancel", None)
        for track_id, (request_id, _epoch) in list(self._preload_requests.items()):
            self._preload_requests.pop(track_id, None)
            if request_id and cancel is not None:
                try:
                    cancel(request_id)
                except Exception:  # noqa: BLE001 - 取消失败不影响状态失效
                    log.debug("cancel preload %s failed", request_id, exc_info=True)

    def _resolve_identity(self, track: Track) -> "PlaybackIdentity":
        """决定这次播放的歌曲身份：正式绑定 > 旧记忆 > 队列原样。

        ``revision`` 取的是「确定身份这一刻」的数据库版本；之后的异步回调
        只能拿它来做比较，不允许再读一个新版本替自己背书。
        """
        stored: Track | None = None
        if self._binding is not None:
            try:
                stored = self._binding.get_target(track.id)
            except Exception:  # noqa: BLE001 - 绑定读取失败退回队列对象
                log.debug("read binding target for %s failed", track.id, exc_info=True)
                stored = None
        has_valid_binding = (
            stored is not None
            and stored.kind == "online"
            and bool(stored.source_id)
            and bool(stored.remote_id)
        )
        revision = 0
        if self._binding is not None:
            try:
                revision = int(self._binding.state(track.id).revision)
            except Exception:  # noqa: BLE001
                log.debug("read binding state for %s failed", track.id, exc_info=True)
                revision = 0
        if has_valid_binding:
            if (stored.source_id != track.source_id
                    or stored.remote_id != track.remote_id):
                log.info("binding target %s/%s for %r",
                         stored.source_id, stored.remote_id, track.title)
            return PlaybackIdentity(target=stored, revision=revision, bound=True)

        # 只有「没有有效正式绑定」时才允许兼容旧 source_memory。
        alias = source_memory.track_alias(track)
        if alias is not None:
            alias_source = str(alias.get("source_id") or "")
            same_source = alias_source == track.source_id
            playable = self._source_is_playable(alias_source)
            if (alias_source and (self._online_fallback or same_source)
                    and playable and not health.looks_broken(alias_source)):
                log.info("using remembered source %s for %r",
                         alias_source, track.title)
                return PlaybackIdentity(
                    target=_track_from_alias(track, alias),
                    revision=revision,
                    alias_used=True,
                    alias_source=alias_source,
                )
            if not alias_source or not playable:
                source_memory.forget_track(track)
        return PlaybackIdentity(target=track, revision=revision)

    def _take_preloaded(self, track: Track, identity: "PlaybackIdentity",
                        quality: str) -> dict[str, Any] | None:
        """Consume a preload only when it was resolved for *this* identity."""
        entry = self._preloaded.pop(track.id, None)
        if entry is None:
            return None
        problems = []
        if entry.request and not models.payload_matches_source(
            entry.request, identity.source_id, identity.remote_id
        ):
            problems.append("payload identity")
        if entry.source_id != identity.source_id:
            problems.append(f"source {entry.source_id!r} != {identity.source_id!r}")
        if entry.remote_id != identity.remote_id:
            problems.append(f"remote {entry.remote_id!r} != {identity.remote_id!r}")
        if entry.quality != quality:
            problems.append(f"quality {entry.quality!r} != {quality!r}")
        if int(entry.revision) != int(identity.revision):
            problems.append(f"revision {entry.revision} != {identity.revision}")
        if problems:
            log.info("丢弃过期预加载 %s：%s", track.title, "；".join(problems))
            return None
        log.info("preloaded stream hit for %r (%s/%s @ %s)",
                 track.title, entry.source_id, entry.remote_id, entry.quality)
        return dict(entry.data)

    def _play_current(self, *, reset_position: bool) -> None:
        track = self.queue.current
        if track is None:
            return
        position = 0 if reset_position else self._position
        self._failures = 0
        self._fallback_tried.clear()
        self._load(track, position=position, autoplay=True)

    def _on_queue_current_changed(self, track: object) -> None:
        # 队列从外部换了当前曲目（例如恢复会话）；恢复阶段只摆状态，不加载。
        if self._restoring or self._silent_current:
            return
        if isinstance(track, Track) and track is not self._track:
            self._load(track, position=0, autoplay=self.engine.state == "playing")

    def _on_mode_changed(self) -> None:
        if self.queue.shuffle != self._last_shuffle:
            self._last_shuffle = self.queue.shuffle
            self.shuffle_changed.emit(self._last_shuffle)
        if self.queue.repeat != self._last_repeat:
            self._last_repeat = self.queue.repeat
            self.repeat_changed.emit(self._last_repeat)

    def preload_next(self, *, delay_ms: int = 2500) -> None:
        """Resolve the upcoming online track ahead of time (no UI impact).

        The prefetch must obey the same identity rules as playback: it first
        asks the database (then, only without a binding, the legacy memory) what
        this song is, and stores that identity together with the URL so the
        consumption side can prove the two still agree.
        """
        if self.client is None:
            return
        upcoming = self.queue.upcoming(1)
        if not upcoming:
            return
        nxt = upcoming[0]
        if nxt.kind != "online" or not nxt.id:
            return
        if nxt.id in self._preloaded or nxt.id in self._preload_requests:
            return
        identity = self._resolve_identity(nxt)
        target = identity.target
        if not target.source_id or not self._source_is_playable(target.source_id):
            return
        quality = self._quality or "standard"
        payload = models.runtime_track(target, source_id=target.source_id)
        epoch = self._preload_epoch
        request_id = self.client.resolve_playback(
            target.source_id,
            payload,
            lambda response, tid=nxt.id, ident=identity, q=quality,
                   req=payload, token=epoch: self._on_preloaded(
                       tid, response, ident, q, req, token
                   ),
            quality=quality,
        )
        if request_id:
            self._preload_requests[nxt.id] = (int(request_id), epoch)

    def _on_preloaded(
        self,
        track_id: str,
        response: dict[str, Any],
        identity: "PlaybackIdentity",
        quality: str,
        request: dict[str, Any],
        epoch: int,
    ) -> None:
        registered = self._preload_requests.get(track_id)
        if registered is not None and registered[1] == epoch:
            self._preload_requests.pop(track_id, None)
        if epoch != self._preload_epoch:
            # 手动换源/切歌已经让这次预加载过期，迟到结果不得写回缓存。
            log.info("丢弃迟到的预加载回调：%s", track_id)
            return
        if not response.get("ok"):
            return
        data = response.get("data") or {}
        if not isinstance(data, dict) or not data.get("url"):
            return
        self._preloaded[track_id] = PreloadedStream(
            source_id=identity.source_id,
            remote_id=identity.remote_id,
            quality=quality,
            revision=int(identity.revision),
            request_id=int(registered[0]) if registered else 0,
            request=dict(request),
            data=dict(data),
        )

    def _apply_replaygain(self, track: Track, source: str) -> None:
        mode = str(self._replaygain or "off")
        if mode == "off" or track.kind != "local" or not track.path or source.startswith("http"):
            self.engine.set_gain(1.0)
            return
        self.engine.set_gain(replaygain.scale_for(track.path, mode))

    def _load(self, track: Track, *, position: int = 0, autoplay: bool = True,
              force_resolve: bool = False) -> None:
        if track is None:
            return
        was_playing = self.engine.state == "playing"
        if self._busy and not self.engine.state == "loading":
            # A new load supersedes the previous resolve; drop the stale spinner
            # so the bar shows "buffering" for the track we are actually loading.
            self._set_busy(False)
        self._paused_pending = False
        self._memory_pending = None
        # A new load starts a new playback session: any attempt/confirm from the
        # previous session is invalid, and preloads for other tracks are stale.
        self._session += 1
        self._attempt = None
        self._last_position_value = 0
        self._restored_pending = False
        self._invalidate_preloads(keep_track_id=track.id)
        self._track = track
        self._pending_resume = max(0, int(position))
        self._position = self._pending_resume
        self._duration = track.duration_ms or 0
        self.track_changed.emit(track)
        self.duration_changed.emit(self._duration)
        self.position_changed.emit(self._position)

        if track.is_local:
            self._active_online = None
            path = track.path or ""
            if not path or not os.path.isfile(path):
                self._handle_missing_local(track, autoplay=autoplay)
                return
            self._apply_replaygain(track, path)
            self.engine.load(path, duration_hint=track.duration_ms, autoplay=autoplay)
            self._apply_pending_position()
            return

        self._active_online = track
        self.engine.set_gain(1.0)
        self._resolve_online(track, autoplay=autoplay, force=force_resolve, tried=set(), was_playing=was_playing)

    def _apply_pending_position(self) -> None:
        if self._pending_resume > 0:
            target = self._pending_resume
            self._pending_resume = 0
            QTimer.singleShot(120, lambda: self.seek(target))

    def _handle_missing_local(self, track: Track, *, autoplay: bool = True) -> None:
        message = f"文件已不存在：{os.path.basename(track.path or track.title)}"
        log.warning(message)
        self.status_message.emit(message)
        self._failures += 1
        # 只有「本来就是用户要求开始播放」时才自动跳下一首；恢复会话时静默停在
        # 这首歌，绝不能因为文件缺失就自行播放队列里的另一首。
        if autoplay and self._failures < MAX_CONSECUTIVE_FAILURES and self.queue.count > 1:
            self._schedule_auto_next(350)
        else:
            self.engine.stop()
            self.error_message.emit("本地文件不可用，播放已停止")

    def _schedule_auto_next(self, delay_ms: int) -> None:
        """延迟跳下一首，但只对发起它的那个播放会话生效。"""
        generation = self._resolve_generation
        QTimer.singleShot(
            delay_ms,
            lambda: self.next(auto=True) if generation == self._resolve_generation else None,
        )

    def _resolve_online(self, track: Track, *, autoplay: bool, force: bool,
                        tried: set[str], was_playing: bool,
                        identity: PlaybackIdentity | None = None,
                        quality: str | None = None) -> None:
        """Resolve a stream for the *formal* identity of ``track``.

        ``force`` only bypasses the URL cache (expired/poisoned URLs); it never
        re-decides which song/source to play.  Retries pass ``identity`` and
        ``quality`` explicitly so every attempt keeps the exact same
        ``source_id + remote_id``.
        """
        if identity is None:
            identity = self._resolve_identity(track)
        target = identity.target
        revision = int(identity.revision)
        bound = bool(identity.bound)
        if quality is None:
            quality = self._quality or "standard"
        generation = self._next_generation()

        source_id = target.source_id
        if not source_id:
            self._online_failed(track, "该在线歌曲缺少音源信息", tried, autoplay,
                                attempted=target, kind="source-unavailable")
            return

        # 1) 完整磁盘缓存优先。这一步必须早于「音源是否可用」判断：插件被禁用、
        #    断网或服务器故障时，已经缓存过的歌仍然必须能播。
        if self._cache_enabled and self.proxy is not None:
            hit = self._cached_stream(identity, quality)
            if hit is not None:
                path, hit_quality = hit
                log.info("cache hit for %r (%s/%s @ %s)",
                         track.title, identity.source_id, identity.remote_id, hit_quality)
                self._begin_attempt(track, target, revision, quality=hit_quality)
                self._apply_cached(track, path, generation, autoplay, was_playing,
                                   identity=identity, quality=hit_quality)
                return

        # 只有「源本身不可用」（插件缺失/被禁用）才允许换源；URL 失效留给
        # 同一身份的刷新/音质降级处理。
        if not self._source_is_playable(source_id):
            if self._online_fallback and self._fallback_all_sources(
                track, {source_id, track.source_id}, autoplay,
                "原音源不可用，正在其他音源中查找", quality=quality,
                failed_source=source_id,
            ):
                return
            self._online_failed(track, "原音源不可用", tried, autoplay,
                                attempted=target, kind="source-unavailable")
            return

        # 旧 source_map 只对「没有正式绑定」且没有别名可用的歌曲生效。
        if not bound and not identity.alias_used and self._online_fallback:
            mapped = source_memory.source_map(track.source_id)
            if (mapped and mapped != source_id
                    and self._source_is_playable(mapped)
                    and health.looks_broken(track.source_id)):
                log.info("skip broken source %s for %r → %s",
                         track.source_id, track.title, mapped)
                self.status_message.emit(
                    f"{self._source_label(track.source_id)} 最近无法播放，"
                    f"正在使用 {self._source_label(mapped)}"
                )
                if self._fallback_all_sources(track, {track.source_id}, autoplay,
                                              "该音源最近解析失败", only=mapped,
                                              quality=quality,
                                              failed_source=track.source_id):
                    return

        preloaded = None if force else self._take_preloaded(track, identity, quality)
        if preloaded is not None:
            self._begin_attempt(track, target, revision, quality=quality)
            self._apply_resolved(track, preloaded, generation, autoplay,
                                 was_playing, identity=identity, quality=quality,
                                 tried=tried)
            return

        cache_key = self._resolve_cache_key(target, quality)
        cached = self._resolve_cache.get(cache_key)
        if cached is not None and not force:
            stamped, payload = cached
            age_ms = (time.monotonic() - stamped) * 1000
            expires_at = float(payload.get("expiresAt") or 0)
            fresh = age_ms < RESOLVE_CACHE_TTL_MS and (
                not expires_at or expires_at * 1000 - time.time() * 1000 > 15_000
            )
            if fresh:
                log.info("resolve cache hit for %s (%.0fms old)", track.title, age_ms)
                self._begin_attempt(track, target, revision, quality=quality)
                self._apply_resolved(track, payload, generation, autoplay,
                                     was_playing, identity=identity,
                                     quality=quality, tried=tried)
                return
            self._resolve_cache.pop(cache_key, None)

        self._set_busy(True, "正在获取播放地址…")
        if self._resolve_request_id:
            try:
                self.client.cancel(self._resolve_request_id)
            except Exception:  # noqa: BLE001
                log.debug("cancel resolve %s failed", self._resolve_request_id, exc_info=True)
            self._resolve_request_id = 0
        self._begin_attempt(track, target, revision, quality=quality)
        self._resolve_request_id = self.client.resolve_playback(
            source_id,
            runtime_track(target, source_id=source_id),
            lambda response: self._on_resolved(
                track, response, generation, autoplay, tried, was_playing,
                identity=identity, quality=quality,
            ),
            quality=quality,
        ) or 0

    def _on_resolved(self, track: Track, response: dict, generation: int,
                     autoplay: bool, tried: set[str], was_playing: bool,
                     *, identity: PlaybackIdentity, quality: str) -> None:
        """解析结果回调：成功就播放，失败才降级/回退。"""

        if generation != self._resolve_generation:
            return
        self._set_busy(False)
        target = identity.target
        if not response.get("ok"):
            error = str(response.get("error") or "未知错误")
            log.info("resolve failed for %r via %s/%s @ %s: %s",
                     track.title, target.source_id, target.remote_id, quality, error)
            # 同一绑定源换一档音质再试，仍然不改身份。旧别名不参与音质阶梯：
            # 它本来就是兼容路径，失败就该进入跨源搜索，而不是拖慢三倍。
            next_quality = None if identity.alias_used else _next_quality(quality)
            if next_quality is not None:
                self._resolve_online(
                    track, autoplay=autoplay, force=True, tried=tried,
                    was_playing=was_playing, identity=identity,
                    quality=next_quality,
                )
                return
            if identity.alias_used:
                # 别名的音质都失败了：不能再退回原源，也不能继续信这个名字。
                if identity.alias_source and source_memory.preferred() == identity.alias_source:
                    source_memory.clear_preferred()
                source_memory.mark_alias_failed(track)
            if identity.bound and self._binding is not None:
                try:
                    self._binding.mark_failed(
                        track.id, expected_revision=int(identity.revision)
                    )
                except Exception:  # noqa: BLE001 - 状态写入失败不应影响播放
                    log.debug("mark binding failed for %s", track.id, exc_info=True)
            # 别名失败时把原源也加入 tried：不能立刻绕回刚刚不可用的来源。
            failed_tried = set(tried)
            if identity.alias_used and track.source_id:
                failed_tried.add(track.source_id)
            self._online_failed(track, error, failed_tried, autoplay,
                                attempted=target, kind="resolve")
            return

        payload = response.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}
        resolved_quality = str(payload.get("quality") or quality)
        # 缓存键永远是「实际播放目标」的身份，绝不用原队列歌曲的 remote_id。
        self._resolve_cache[self._resolve_cache_key(target, resolved_quality)] = (
            time.monotonic(), payload
        )
        health.record_ok(target.source_id or track.source_id or "")
        self._apply_resolved(track, payload, generation, autoplay, was_playing,
                             identity=identity, quality=quality, tried=tried)

    def _begin_attempt(self, track: Track, target: Track, revision: int,
                       *, was_fallback: bool = False, quality: str = "") -> None:
        """记录「这一次播放尝试」的身份，供播放确认时校验。"""
        if target.kind != "online" or not target.source_id:
            self._attempt = None
            return
        from ..services.binding import BindingChoice

        self._attempt = {
            "track_id": track.id,
            # 会话标识让「上一首歌/上一次加载」的迟到的确认无法落到当前播放上。
            "session": self._session,
            "choice": BindingChoice.from_track(target),
            "source_id": target.source_id,
            "remote_id": target.remote_id,
            "quality": str(quality or ""),
            "revision": int(revision),
            "was_fallback": bool(was_fallback),
            "confirmed": False,
        }

    def _confirm_attempt(self) -> None:
        """音频真的向前推进后，才把这次来源写入正式绑定。"""
        attempt = self._attempt
        if attempt is None or attempt.get("confirmed"):
            return
        if attempt.get("session") != self._session:
            attempt["confirmed"] = True
            return
        track = self._track
        if track is None or track.id != attempt["track_id"]:
            return
        if self.engine.state != "playing":
            return
        if self._binding is None:
            # 没有绑定服务时才由旧 JSON 记忆兜底；同样只认真实播放。
            attempt["confirmed"] = True
            self._commit_memory_pending()
            return
        current = self._binding.state(track.id)
        if current.revision != int(attempt["revision"]):
            # 播放期间用户/导入改过绑定：旧回调不得覆盖新选择。
            attempt["confirmed"] = True
            log.info("丢弃过期播放确认：%s revision %s != %s",
                     track.id, attempt["revision"], current.revision)
            return
        choice = attempt["choice"]
        if attempt.get("was_fallback") and choice.source_id != (track.source_id or ""):
            ok = self._binding.adopt_verified_fallback(
                track.id, choice, expected_revision=current.revision
            )
        else:
            ok = self._binding.mark_play_verified(
                track.id, expected_revision=current.revision, choice=choice
            )
        attempt["confirmed"] = True
        if not ok:
            # manual 绑定永不被自动回退改写；这里静默失败是正确行为。
            log.info("播放确认未写入 %s（来源 %s 未被采纳）", track.id, choice.source_id)
            return
        updated = self._binding.get_target(track.id)
        if updated is None:
            return
        self._track = updated
        self.queue.replace_track(updated)
        self.track_changed.emit(updated)
        self.active_source_changed.emit(self._source_label(updated.source_id or ""))
        try:
            self._binding.notify_updated(updated.id)
        except Exception:  # noqa: BLE001 - UI 刷新失败不影响播放
            pass
        # 旧 JSON 记忆只在数据库确认之后同步，不能独立地更早确立身份。
        self._commit_memory_pending()

    def _resolve_cache_key(self, track: Track, quality: str | None = None) -> str:
        return f"{track.source_id}:{track.remote_id or track.id}:{quality or self._quality}"

    def _cache_qualities(self, quality: str) -> list[str]:
        """音质候选顺序：请求档位优先，再试其它常见档位（插件可能降级返回）。"""
        order = [quality, self._quality, *QUALITY_CHAIN, *CACHE_QUALITY_TIERS]
        seen: set[str] = set()
        result: list[str] = []
        for tier in order:
            name = str(tier or "standard")
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result

    def _cached_stream(self, identity: PlaybackIdentity,
                       quality: str) -> tuple[str, str] | None:
        """按正式身份查完整磁盘缓存，返回 ``(本地路径, 命中的音质)``。"""
        proxy = self.proxy
        if proxy is None:
            return None
        remote_id = identity.remote_id
        if not identity.source_id or not remote_id:
            return None
        for tier in self._cache_qualities(quality):
            cache_key = f"{identity.source_id}:{remote_id}:{tier}"
            path = proxy.local_path(cache_key)
            if path:
                try:
                    proxy.note_playing(cache_key)
                except Exception:  # noqa: BLE001 - 保护标记失败不影响播放
                    log.debug("note playing cache token failed", exc_info=True)
                return path, tier
        return None

    def _apply_cached(self, track: Track, path: str, generation: int,
                      autoplay: bool, was_playing: bool, *,
                      identity: PlaybackIdentity, quality: str) -> None:
        """播放本地完整缓存：不联网、不标记源健康度，但仍保留正式绑定与会话。"""
        if generation != self._resolve_generation:
            return
        self._set_busy(False)
        log.info("离线缓存播放 %r（%s/%s @ %s）",
                 track.title, identity.source_id, identity.remote_id, quality)
        self.active_source_changed.emit(
            self._source_label(identity.source_id or track.source_id or "")
        )
        self._last_position_value = 0
        self.engine.load(path, duration_hint=track.duration_ms, autoplay=autoplay)
        self._apply_pending_position()
        if was_playing and not autoplay:
            self.engine.play()

    def _apply_resolved(self, track: Track, data: dict, generation: int,
                        autoplay: bool, was_playing: bool, *,
                        identity: PlaybackIdentity, quality: str,
                        tried: set[str] | None = None) -> None:
        tried = tried if tried is not None else set()
        if generation != self._resolve_generation:
            return
        self._set_busy(False)
        url = str(data.get("url") or "")
        if not url:
            self._online_failed(track, "音源没有返回播放地址", tried, autoplay,
                                attempted=identity.target, kind="resolve")
            return
        headers = data.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}
        headers = {str(k): str(v) for k, v in headers.items() if isinstance(v, (str, int, float))}
        mime = str(data.get("mimeType") or "")
        resolved_quality = str(data.get("quality") or quality)
        try:
            expires = float(data.get("expiresAt") or 0)
        except (TypeError, ValueError):
            expires = 0.0
        # 缓存键 = 实际播放目标 + 实际音质；不能用原队列歌曲的 remote_id。
        cache_key = (f"{identity.source_id}:"
                     f"{identity.remote_id or track.id}:{resolved_quality}")
        ext = self._guess_ext(url, mime)
        try:
            stream_url = self.proxy.register(
                cache_key, url, headers, mime=mime, ext=ext, expires_at=expires,
                quality=resolved_quality,
            )
        except Exception as exc:
            log.exception("proxy register failed")
            self._online_failed(track, f"本地缓存服务不可用：{exc}", tried, autoplay,
                                attempted=identity.target, kind="media")
            return
        try:
            self.proxy.note_playing(cache_key)
        except Exception:  # noqa: BLE001 - 清理保护失败不影响播放
            log.debug("note playing cache token failed", exc_info=True)
        health.record_ok(identity.source_id or track.source_id or "")
        self.active_source_changed.emit(
            self._source_label(identity.source_id or track.source_id or "")
        )
        # 新流的第一拍位置不是「播放进度」，不能拿来确认播放成功。
        self._last_position_value = 0
        self.engine.load(stream_url, duration_hint=track.duration_ms, autoplay=autoplay)
        self._apply_pending_position()
        if was_playing and not autoplay:
            self.engine.play()

    def _online_failed(self, track: Track, error: str, tried: set[str], autoplay: bool,
                       *, attempted: Track | None = None, kind: str = "resolve",
                       failed_source: str = "") -> None:
        """Record a failure against the source that *actually* failed.

        ``attempted`` is the bound/fallback target that produced ``error``; the
        queue row may point at a completely different source, and blaming it
        used to poison the wrong plugin's health and the ``tried`` set.
        ``failed_source`` carries an already-blamed source through a fallback
        round without recording a second failure for it.
        """
        self._set_busy(False)
        if kind == "cancelled":
            return
        blamed = str(attempted.source_id) if attempted is not None else str(failed_source or "")
        failed_remote = str(attempted.remote_id) if attempted is not None else ""
        failed_tried = set(tried)
        if attempted is not None and blamed:
            health.record_fail(blamed, error)
            failed_tried.add(blamed)
            log.info("resolve failed for %s via %s/%s (%s): %s",
                     track.title, blamed, failed_remote, kind, error)
        else:
            log.info("resolve failed for %s (%s): %s", track.title, kind, error)
        if self._online_fallback and len(failed_tried) <= FALLBACK_MAX:
            # Original HushPlayer behaviour: an unavailable source silently
            # falls back to any other enabled source that has the same song.
            if self._fallback_all_sources(track, failed_tried, autoplay, error,
                                          failed_source=blamed):
                return
        # Nothing else to try: surface it as a real error (toast) instead of a
        # transient status line, otherwise a failed resolve looks silent.
        self.error_message.emit(f"无法播放《{track.display_title}》：{_short(error)}")
        self._failures += 1
        # 只有本次加载本来就是「要求自动播放」时才跳下一首；否则（恢复会话、
        # 后台预备）绝不能因为一次失败就自己换歌。
        if autoplay and self._failures < MAX_CONSECUTIVE_FAILURES and self.queue.count > 1:
            self._schedule_auto_next(600)
        else:
            # The attempt is over: settle on a stopped, usable state instead of
            # leaving ``loading`` stuck for ever with dead transport controls.
            self._next_generation()
            self._attempt = None
            self._set_busy(False)
            self.engine.stop()
            self.error_message.emit("在线播放失败，已停止")

    def _fallback_all_sources(
        self, track: Track, tried: set[str], autoplay: bool, error: str,
        *, only: str | None = None, quality: str = "standard",
        failed_source: str = "",
    ) -> bool:
        """Search every remaining playable source for the same recording.

        ``only`` restricts the search to the source we already know works for
        this plugin (remembered mapping), which keeps track switching fast when
        the original plugin is stale.

        Returns True when a search was kicked off (playback may still fail and
        continue through the chain); False means nothing else can be tried.
        """
        remaining = [s for s in self.playable_sources() if s.id not in tried]
        if only:
            focused = [s for s in remaining if s.id == only]
            if focused:
                sources = focused
            else:
                sources = remaining
        else:
            preferred = source_memory.preferred()
            healthy = [s for s in remaining if not health.recently_failed(s.id)]
            if healthy:
                remaining = healthy
            sources = sorted(remaining, key=lambda s: 0 if s.id == preferred else 1)
        sources = sources[:FALLBACK_MAX]
        if not sources:
            return False
        generation = self._resolve_generation
        keyword = f"{track.title} {track.artist}".strip() or track.title
        pending = {source.id for source in sources}
        searched = {source.id for source in sources}
        collected: list[MatchCandidate] = []
        names = "、".join(source.label for source in sources)
        blamed = failed_source or track.source_id
        self.status_message.emit(
            f"{self._source_label(blamed)} 暂时无法播放（{_short(error)}），正在其他音源中查找：{names}"
        )
        focused_only = bool(only) and {s.id for s in sources} == {only}

        settled = False

        def choose() -> None:
            nonlocal settled
            if settled:
                return
            settled = True
            if generation != self._resolve_generation:
                return
            if not collected:
                if focused_only:
                    # The remembered source has nothing: continue with the
                    # normal chain instead of giving up.
                    self._online_failed(
                        track, "其他音源没有找到同一首歌",
                        set(tried) | {only or ""}, autoplay,
                        failed_source=failed_source,
                    )
                    return
                # Everything was already searched: do not fall back again in a
                # loop (this used to re-search the same dead sources forever).
                self._online_failed(track, "其他音源没有找到同一首歌",
                                    set(tried) | searched, autoplay,
                                    failed_source=failed_source)
                return
            # Duplicates of the same recording (common in one source's result
            # list) must not shrink the margin against a *different* song.
            best_by_song: dict[tuple[str, str], MatchCandidate] = {}
            for item in collected:
                key = (
                    normalize_text(item.track.title),
                    normalize_text(item.track.artist),
                )
                current = best_by_song.get(key)
                if current is None or item.score > current.score:
                    best_by_song[key] = item
            ordered = sorted(best_by_song.values(), key=lambda item: item.score, reverse=True)
            best = ordered[0]
            margin = best.score - ordered[1].score if len(ordered) > 1 else best.score
            confident = best.score >= AUTO_MIN_SCORE and margin >= AUTO_MARGIN
            if not confident and best.score < CANDIDATE_MIN_SCORE:
                self._online_failed(track, "其他音源没有找到同一首歌",
                                    set(tried) | searched, autoplay,
                                    failed_source=failed_source)
                return
            label = self._source_label(best.track.source_id)
            if confident:
                self.status_message.emit(f"已切换到 {label} 音源播放")
            else:
                self.status_message.emit(f"未找到完全一致的版本，已用 {label} 的最接近结果继续播放")
            self._play_candidate(track, best.track, tried, autoplay, quality)

        def on_search(source: SourceInfo, response: dict) -> None:
            if generation != self._resolve_generation:
                return
            pending.discard(source.id)
            if response.get("ok"):
                items = response.get("data") or []
                if isinstance(items, dict):
                    items = items.get("items") or items.get("songs") or []
                try:
                    candidates = tracks_from_items(items, source=source)
                except Exception as exc:  # noqa: BLE001
                    log.warning("解析回退搜索结果失败：%s", exc)
                    candidates = []
                collected.extend(rank_candidates(track, candidates))
            else:
                # 搜索失败归于正在搜索的那个源，而不是原队列歌曲的源。
                health.record_fail(source.id, str(response.get("error") or "搜索失败"))
            if not pending:
                choose()

        for source in sources:
            self.client.search(
                source.id,
                keyword,
                1,
                lambda response, s=source: on_search(s, response),
                timeout=FALLBACK_SEARCH_TIMEOUT_MS,
            )
        # A source may never answer (runtime restart, dropped request); never
        # leave the player stuck on "loading" because one callback is missing.
        QTimer.singleShot(FALLBACK_SEARCH_TIMEOUT_MS + 2500, choose)
        return True

    def _play_candidate(self, track: Track, match: Track, tried: set[str],
                        autoplay: bool, quality: str = "standard") -> None:
        generation = self._next_generation()
        tried.add(match.source_id)
        # The revision belongs to the moment this playback identity was chosen;
        # the callback must not re-read a newer revision and pretend to be it.
        revision = 0
        if self._binding is not None:
            try:
                revision = int(self._binding.state(track.id).revision)
            except Exception:  # noqa: BLE001
                log.debug("read binding revision for %s failed", track.id, exc_info=True)
        self._set_busy(True, "正在获取播放地址…")
        self.client.resolve_playback(
            match.source_id,
            runtime_track(match, source_id=match.source_id),
            lambda response: self._on_fallback_resolved(
                track, match, response, generation, autoplay, tried, quality, revision
            ),
            quality=quality,
        )

    def _pick_fallback(self, track: Track, tried: set[str]) -> SourceInfo | None:
        for source in self.playable_sources():
            if source.id in tried:
                continue
            return source
        return None

    def _search_fallback(self, track: Track, source: SourceInfo, tried: set[str], autoplay: bool) -> None:
        keyword = f"{track.title} {track.artist}".strip()
        generation = self._resolve_generation

        def on_search(response: dict) -> None:
            if generation != self._resolve_generation:
                return
            if not response.get("ok"):
                error = str(response.get("error") or "搜索失败")
                health.record_fail(source.id, error)
                self._online_failed(track, error, tried, autoplay, attempted=source)
                return
            candidates = tracks_from_items(response.get("data") or [], source=source)
            match = self._best_match(track, candidates)
            if match is None:
                self._online_failed(track, "其他音源没有找到同一首歌",
                                    set(tried) | {source.id}, autoplay, attempted=source)
                return
            # Reuse the current row: the queue keeps showing the original track,
            # but playback uses the matched stream.
            self._play_candidate(track, match, tried, autoplay, self._quality)

        self.client.search(source.id, keyword, 1, on_search)

    def _on_fallback_resolved(self, track: Track, match: Track, response: dict, generation: int,
                              autoplay: bool, tried: set[str],
                              quality: str = "standard", revision: int = 0) -> None:
        if generation != self._resolve_generation:
            return
        self._set_busy(False)
        if not response.get("ok"):
            self._online_failed(track, str(response.get("error") or "播放地址解析失败"),
                                tried, autoplay, attempted=match, kind="resolve")
            return
        data = response.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        url = str(data.get("url") or "")
        if not url:
            self._online_failed(track, "音源没有返回播放地址", tried, autoplay,
                                attempted=match, kind="resolve")
            return
        headers = data.get("headers") or {}
        headers = {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {}
        mime = str(data.get("mimeType") or "")
        resolved_quality = str(data.get("quality") or quality)
        try:
            expires = float(data.get("expiresAt") or 0)
        except (TypeError, ValueError):
            expires = 0.0
        # 键用实际匹配到的目标身份；原队列歌曲的 remote_id 不参与。
        cache_key = f"{match.source_id}:{match.remote_id or match.id}:{resolved_quality}"
        try:
            stream_url = self.proxy.register(
                cache_key, url, headers, mime=mime, ext=self._guess_ext(url, mime),
                expires_at=expires, quality=resolved_quality,
            )
        except Exception as exc:
            log.exception("proxy register failed")
            self._online_failed(track, f"本地缓存服务不可用：{exc}", tried, autoplay,
                                attempted=match, kind="media")
            return
        try:
            self.proxy.note_playing(cache_key)
        except Exception:  # noqa: BLE001
            log.debug("note playing cache token failed", exc_info=True)
        # A fallback that actually produced a URL is evidence the source works;
        # without this the alias source can stay "broken" from older failures
        # and get skipped on the next play, forcing another search.
        health.record_ok(match.source_id)
        self._resolve_cache[self._resolve_cache_key(match, resolved_quality)] = (
            time.monotonic(), data
        )
        self._begin_attempt(track, match, revision, was_fallback=True, quality=quality)
        self.status_message.emit(f"已通过 {self._source_label(match.source_id)} 播放")
        self.active_source_changed.emit(self._source_label(match.source_id))
        # Remember the pairing only once audio really starts (see _commit_memory_pending):
        # some plugins return a URL that then 404s on the stream.
        self._memory_pending = (track, match)
        if match.duration_ms and not track.duration_ms:
            self._duration = match.duration_ms
            self.duration_changed.emit(self._duration)
        # Leaving ``busy`` set would keep the UI on "loading" although the
        # fallback stream is already playing.
        self._set_busy(False)
        self._last_position_value = 0
        self.engine.load(stream_url, duration_hint=self._duration or match.duration_ms, autoplay=autoplay)
        self._apply_pending_position()

    @staticmethod
    def _best_match(track: Track, candidates: list[Track]) -> Track | None:
        wanted_title = _normalise_text(track.title)
        wanted_artist = _normalise_text(track.artist)
        best: Track | None = None
        best_score = 0
        for candidate in candidates:
            score = 0
            if _normalise_text(candidate.title) == wanted_title:
                score += 3
            elif wanted_title and wanted_title in _normalise_text(candidate.title):
                score += 1
            artist_text = _normalise_text(candidate.artist)
            if wanted_artist and artist_text:
                if wanted_artist == artist_text:
                    score += 2
                elif wanted_artist in artist_text or artist_text in wanted_artist:
                    score += 1
            if track.duration_ms and candidate.duration_ms:
                if abs(candidate.duration_ms - track.duration_ms) < 5000:
                    score += 1
            if score > best_score:
                best, best_score = candidate, score
        return best if best_score >= 2 else None

    def _source_label(self, source_id: str) -> str:
        for source in self._sources:
            if source.id == source_id:
                return source.label
        return "该音源"

    @staticmethod
    def _guess_ext(url: str, mime: str) -> str:
        lowered = (mime or "").lower()
        if "flac" in lowered:
            return "flac"
        if "mpeg" in lowered or "mp3" in lowered:
            return "mp3"
        if "mp4" in lowered or "aac" in lowered or "m4a" in lowered:
            return "m4a"
        if "ogg" in lowered:
            return "ogg"
        clean = url.split("?", 1)[0]
        suffix = os.path.splitext(clean)[1].lower().lstrip(".")
        if suffix in ("mp3", "flac", "m4a", "aac", "ogg", "wav"):
            return suffix
        return "mp3"

    # ------------------------------------------------------------- signals
    def _on_position(self, value: int) -> None:
        value = int(value)
        previous = self._last_position_value
        self._last_position_value = value
        self._position = value
        self.position_changed.emit(value)
        # 只有「真实向前推进」才算播放成功：seek、恢复上次进度、回绕都会造成
        # 单次巨大跳变，不能拿它当验证依据。
        if (0 < value - previous <= 1200 and value >= 1200
                and self.engine.state == "playing"):
            self._confirm_attempt()

    def _on_duration(self, value: int) -> None:
        if value > 0:
            self._duration = int(value)
            self.duration_changed.emit(self._duration)
            if self._track is not None and not self._track.duration_ms:
                self._track.duration_ms = self._duration

    def _commit_memory_pending(self) -> None:
        """Persist the fallback pairing once audio really starts.

        A plugin can return a resolve URL that 404s when the stream opens; if we
        wrote the alias at resolve time, every later play would first retry that
        dead source (the "还是要重新搜索" report).
        """
        pending = self._memory_pending
        self._memory_pending = None
        if pending is None or self._track is None:
            return
        track, match = pending
        if track.id != self._track.id:
            return
        try:
            source_memory.remember_track(track, match)
            source_memory.remember_source_map(track.source_id, match.source_id)
            source_memory.set_preferred(match.source_id)
        except Exception:  # noqa: BLE001
            log.debug("cannot persist source memory", exc_info=True)
    def _on_state(self, state: str) -> None:
        if state == "playing" and self._track is not None:
            # 有数据库绑定时，旧 JSON 记忆只能跟着 _confirm_attempt 走；
            # 只有完全没有绑定服务时它才作为兜底。
            if self._binding is None:
                self._commit_memory_pending()
            self._failures = 0
            self._paused_at = 0.0
            self.track_started.emit(self._track)
            QTimer.singleShot(2500, self.preload_next)
        self.state_changed.emit(state)

    def _on_buffering(self, percent: int) -> None:
        if percent < 5 and self.engine.state == "loading":
            self._set_busy(True, "正在缓冲…")
        elif percent >= 5:
            self._set_busy(False)

    def _on_end_of_media(self) -> None:
        if self.queue.count == 0:
            return
        if self.queue.repeat == "one":
            self.seek(0)
            self.engine.play()
            return
        track = self.queue.next_track(auto=True)
        if track is None:
            self.engine.stop()
            return
        self._play_current(reset_position=True)

    def _on_engine_error(self, message: str, fatal: bool) -> None:
        self._set_busy(False)
        log.warning("engine error: %s", message)
        track = self._track
        if track is not None and track.is_online and not fatal:
            attempt = self._attempt or {}
            # Attribute the media failure to what is actually playing, not to
            # the queue row's original source.
            source_id = str(attempt.get("source_id") or track.source_id or "")
            remote_id = str(attempt.get("remote_id") or track.remote_id or "")
            if self._fallback_tried.isdisjoint({source_id}):
                self._fallback_tried.add(source_id)
                # The cached URL is the suspect: drop it, keep the binding.
                prefix = f"{source_id}:{remote_id}:" if remote_id else f"{source_id}:"
                for key in [k for k in self._resolve_cache if k.startswith(prefix)]:
                    self._resolve_cache.pop(key, None)
                self._attempt = None
                self.status_message.emit("在线音频读取失败，正在重新获取…")
                self._next_generation()
                self._load(track, position=self._position, autoplay=True, force_resolve=True)
                return
        self.status_message.emit(message)
        self._failures += 1
        if self._failures < MAX_CONSECUTIVE_FAILURES and self.queue.count > 1:
            self._schedule_auto_next(700)
        else:
            # never leave the UI in a fake playing/loading state after a fatal
            # error: stop the pipeline and clear the busy flag
            self._next_generation()
            self._attempt = None
            self._set_busy(False)
            self.engine.stop()
            self.error_message.emit("播放出错，已停止")

    def _on_sources(self, raw: list) -> None:
        self._sources = build_sources(raw)
        self.sources_changed.emit(self._sources)

    def _on_client_failure(self, message: str) -> None:
        self._sources = []
        self.sources_changed.emit(self._sources)
        self.status_message.emit(message)

    # ------------------------------------------------------------- teardown
    def shutdown(self) -> None:
        try:
            self.engine.shutdown()
        except Exception:
            pass
        try:
            self.client.stop()
        except Exception:
            pass
        try:
            self.proxy.shutdown()
        except Exception:
            pass


def _normalise_text(value: str) -> str:
    text = (value or "").lower()
    for char in " \t\u3000()（）[]【】-–—_.,，。'\"“”‘’&、/":
        text = text.replace(char, "")
    return text


def _short(text: str, limit: int = 80) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _next_quality(quality: str) -> str | None:
    """Next quality tier for the *same* identity, or None when exhausted."""
    try:
        index = QUALITY_CHAIN.index(quality)
    except ValueError:
        return None
    if index + 1 >= len(QUALITY_CHAIN):
        return None
    return QUALITY_CHAIN[index + 1]


__all__ = ["PlayerController", "ResolvedStream"]
