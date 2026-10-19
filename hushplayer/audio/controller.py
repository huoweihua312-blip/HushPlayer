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
FALLBACK_SEARCH_TIMEOUT_MS = 14000
FALLBACK_MAX_CANDIDATES = 3


@dataclass(slots=True)
class ResolvedStream:
    url: str
    cache_url: str
    mime: str
    quality: str
    expires_at: float
    headers: dict[str, str]
    source_id: str


class PlayerController(QObject):
    track_changed = Signal(object)      # Track | None
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
        self._online_fallback = True

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

    # -------------------------------------------------------------- settings
    def configure(self, *, volume: float | None = None, quality: str = "standard",
                  online_fallback: bool = True, shuffle: bool | None = None,
                  repeat: str | None = None) -> None:
        if volume is not None:
            self.set_volume(volume, emit=True)
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

    def restore_current(self, position_ms: int = 0, *, autoplay: bool = False) -> None:
        """Load the restored queue's current track at ``position_ms`` without starting."""
        track = self.queue.current
        if track is None:
            return
        self._load(track, position=max(0, int(position_ms)), autoplay=autoplay)

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
            self._resolve_generation += 1
            self._set_busy(False)
            self._paused_pending = True
            self.engine.halt_pending()
            self.state_changed.emit("paused")

    def resume(self) -> None:
        if self._track is None:
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
        self._resolve_generation += 1
        self._paused_pending = False
        self._set_busy(False)
        self.engine.stop()
        self._position = 0
        self.position_changed.emit(0)
        self.state_changed.emit("stopped")

    def next(self, *, auto: bool = False) -> None:
        if not self.queue.count:
            return
        track = self.queue.next_track(auto=auto)
        if track is None:
            return
        self._play_current(reset_position=True)

    def previous(self, *, auto: bool = False) -> None:
        if not self.queue.count:
            return
        if not auto and self._position > 4000:
            self.seek(0)
            return
        track = self.queue.previous_track(auto=auto)
        if track is None:
            return
        self._play_current(reset_position=True)

    def seek(self, ms: int) -> None:
        self._position = max(0, int(ms))
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

    def _play_current(self, *, reset_position: bool) -> None:
        track = self.queue.current
        if track is None:
            return
        position = 0 if reset_position else self._position
        self._failures = 0
        self._fallback_tried.clear()
        self._load(track, position=position, autoplay=True)

    def _on_queue_current_changed(self, track: object) -> None:
        # Queue changed the current row from the outside (e.g. restore); reload.
        if self._silent_current:
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

    def _load(self, track: Track, *, position: int = 0, autoplay: bool = True,
              force_resolve: bool = False) -> None:
        if track is None:
            return
        was_playing = self.engine.state == "playing"
        self._paused_pending = False
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
                self._handle_missing_local(track)
                return
            self.engine.load(path, duration_hint=track.duration_ms, autoplay=autoplay)
            self._apply_pending_position()
            return

        self._active_online = track
        self._resolve_online(track, autoplay=autoplay, force=force_resolve, tried=set(), was_playing=was_playing)

    def _apply_pending_position(self) -> None:
        if self._pending_resume > 0:
            target = self._pending_resume
            self._pending_resume = 0
            QTimer.singleShot(120, lambda: self.seek(target))

    def _handle_missing_local(self, track: Track) -> None:
        message = f"文件已不存在：{os.path.basename(track.path or track.title)}"
        log.warning(message)
        self.status_message.emit(message)
        self._failures += 1
        if self._failures < MAX_CONSECUTIVE_FAILURES and self.queue.count > 1:
            QTimer.singleShot(350, lambda: self.next(auto=True))
        else:
            self.engine.stop()
            self.error_message.emit("本地文件不可用，播放已停止")

    def _resolve_online(self, track: Track, *, autoplay: bool, force: bool,
                        tried: set[str], was_playing: bool) -> None:
        source_id = track.source_id
        if not source_id:
            self._online_failed(track, "该在线歌曲缺少音源信息", tried, autoplay)
            return
        self._resolve_generation += 1
        generation = self._resolve_generation
        self._quality_index = 0
        cache_key = self._resolve_cache_key(track)
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
                self._apply_resolved(track, payload, generation, autoplay, was_playing)
                return
            self._resolve_cache.pop(cache_key, None)
        self._set_busy(True, "正在获取播放地址…")
        self.client.resolve_playback(
            source_id,
            runtime_track(track),
            lambda response: self._on_resolved(track, response, generation, autoplay, tried, was_playing),
            quality=self._quality,
        )

    def _on_resolved(self, track: Track, response: dict, generation: int,
                     autoplay: bool, tried: set[str], was_playing: bool) -> None:
        if generation != self._resolve_generation:
            return
        self._set_busy(False)
        if not response.get("ok"):
            error = str(response.get("error") or "未知错误")
            chain = self._quality_chain
            if self._quality_index + 1 < len(chain):
                # Some plugins only resolve one quality tier; try the next
                # tier before declaring the whole source unusable.
                self._quality_index += 1
                next_quality = chain[self._quality_index]
                log.info("retry %s with quality %s (%s)", track.title, next_quality, error)
                self.client.resolve_playback(
                    track.source_id,
                    runtime_track(track),
                    lambda resp: self._on_resolved(
                        track, resp, generation, autoplay, tried, was_playing
                    ),
                    quality=next_quality,
                )
                return
            self._quality_index = 0
            self._online_failed(track, error, tried, autoplay)
            return
        data = dict(response.get("data") or {})
        self._resolve_cache[self._resolve_cache_key(track)] = (time.monotonic(), data)
        self._apply_resolved(track, data, generation, autoplay, was_playing, tried)

    def _resolve_cache_key(self, track: Track) -> str:
        return f"{track.source_id}:{track.remote_id or track.id}:{self._quality}"

    def _apply_resolved(self, track: Track, data: dict, generation: int,
                        autoplay: bool, was_playing: bool,
                        tried: set[str] | None = None) -> None:
        tried = tried if tried is not None else set()
        if generation != self._resolve_generation:
            return
        self._set_busy(False)
        url = str(data.get("url") or "")
        if not url:
            self._online_failed(track, "音源没有返回播放地址", tried, autoplay)
            return
        headers = data.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}
        headers = {str(k): str(v) for k, v in headers.items() if isinstance(v, (str, int, float))}
        mime = str(data.get("mimeType") or "")
        quality = str(data.get("quality") or self._quality)
        try:
            expires = float(data.get("expiresAt") or 0)
        except (TypeError, ValueError):
            expires = 0.0
        cache_key = f"{track.source_id}:{track.remote_id or track.id}:{quality}"
        ext = self._guess_ext(url, mime)
        try:
            stream_url = self.proxy.register(
                cache_key, url, headers, mime=mime, ext=ext, expires_at=expires
            )
        except Exception as exc:
            log.exception("proxy register failed")
            self._online_failed(track, f"本地缓存服务不可用：{exc}", tried, autoplay)
            return
        health.record_ok(track.source_id or "")
        self.engine.load(stream_url, duration_hint=track.duration_ms, autoplay=autoplay)
        self._apply_pending_position()
        if was_playing and not autoplay:
            self.engine.play()

    def _online_failed(self, track: Track, error: str, tried: set[str], autoplay: bool) -> None:
        self._set_busy(False)
        health.record_fail(track.source_id or "", error)
        log.info("resolve failed for %s: %s", track.title, error)
        tried.add(track.source_id)
        if self._online_fallback and len(tried) <= FALLBACK_MAX:
            # Original HushPlayer behaviour: an unavailable source silently
            # falls back to any other enabled source that has the same song.
            if self._fallback_all_sources(track, tried, autoplay, error):
                return
        # Nothing else to try: surface it as a real error (toast) instead of a
        # transient status line, otherwise a failed resolve looks silent.
        self.error_message.emit(f"无法播放《{track.display_title}》：{_short(error)}")
        self._failures += 1
        if self._failures < MAX_CONSECUTIVE_FAILURES and self.queue.count > 1:
            QTimer.singleShot(600, lambda: self.next(auto=True))
        else:
            # The attempt is over: settle on a stopped, usable state instead of
            # leaving ``loading`` stuck for ever with dead transport controls.
            self._resolve_generation += 1
            self._set_busy(False)
            self.engine.stop()
            self.error_message.emit("在线播放失败，已停止")

    def _fallback_all_sources(
        self, track: Track, tried: set[str], autoplay: bool, error: str
    ) -> bool:
        """Search every remaining playable source for the same recording.

        Returns True when a search was kicked off (playback may still fail and
        continue through the chain); False means nothing else can be tried.
        """
        sources = [s for s in self.playable_sources() if s.id not in tried][:FALLBACK_MAX]
        if not sources:
            return False
        generation = self._resolve_generation
        keyword = f"{track.title} {track.artist}".strip() or track.title
        pending = {source.id for source in sources}
        collected: list[MatchCandidate] = []
        names = "、".join(source.label for source in sources)
        self.status_message.emit(
            f"{self._source_label(track.source_id)} 暂时无法播放（{_short(error)}），正在其他音源中查找：{names}"
        )

        settled = False

        def choose() -> None:
            nonlocal settled
            if settled:
                return
            settled = True
            if generation != self._resolve_generation:
                return
            if not collected:
                self._online_failed(track, "其他音源没有找到同一首歌", tried, autoplay)
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
                self._online_failed(track, "其他音源没有找到同一首歌", tried, autoplay)
                return
            label = self._source_label(best.track.source_id)
            if confident:
                self.status_message.emit(f"已切换到 {label} 音源播放")
            else:
                self.status_message.emit(f"未找到完全一致的版本，已用 {label} 的最接近结果继续播放")
            self._play_candidate(track, best.track, tried, autoplay)

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

    def _play_candidate(self, track: Track, match: Track, tried: set[str], autoplay: bool) -> None:
        self._resolve_generation += 1
        generation = self._resolve_generation
        tried.add(match.source_id)
        self._set_busy(True, "正在获取播放地址…")
        self.client.resolve_playback(
            match.source_id,
            runtime_track(match),
            lambda response: self._on_fallback_resolved(
                track, match, response, generation, autoplay, tried
            ),
            quality=self._quality_chain[0],
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
                self._online_failed(track, str(response.get("error") or "搜索失败"), tried, autoplay)
                return
            candidates = tracks_from_items(response.get("data") or [], source=source)
            match = self._best_match(track, candidates)
            if match is None:
                self._online_failed(track, "其他音源没有找到同一首歌", tried, autoplay)
                return
            # Reuse the current row: the queue keeps showing the original track,
            # but playback uses the matched stream.
            self._resolve_generation += 1
            generation2 = self._resolve_generation
            self.client.resolve_playback(
                source.id,
                runtime_track(match),
                lambda resp: self._on_fallback_resolved(track, match, resp, generation2, autoplay, tried),
                quality=self._quality,
            )

        self.client.search(source.id, keyword, 1, on_search)

    def _on_fallback_resolved(self, track: Track, match: Track, response: dict, generation: int,
                              autoplay: bool, tried: set[str]) -> None:
        if generation != self._resolve_generation:
            return
        if not response.get("ok"):
            self._online_failed(track, str(response.get("error") or "播放地址解析失败"), tried, autoplay)
            return
        data = response.get("data") or {}
        url = str(data.get("url") or "")
        if not url:
            self._online_failed(track, "音源没有返回播放地址", tried, autoplay)
            return
        headers = data.get("headers") or {}
        headers = {str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {}
        mime = str(data.get("mimeType") or "")
        quality = str(data.get("quality") or self._quality)
        cache_key = f"{match.source_id}:{match.remote_id or match.id}:{quality}"
        try:
            stream_url = self.proxy.register(
                cache_key, url, headers, mime=mime, ext=self._guess_ext(url, mime)
            )
        except Exception as exc:
            log.exception("proxy register failed")
            self._online_failed(track, f"本地缓存服务不可用：{exc}", tried, autoplay)
            return
        self.status_message.emit(f"已通过 {self._source_label(match.source_id)} 播放")
        if match.duration_ms and not track.duration_ms:
            self._duration = match.duration_ms
            self.duration_changed.emit(self._duration)
        # Leaving ``busy`` set would keep the UI on "loading" although the
        # fallback stream is already playing.
        self._set_busy(False)
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
        self._position = int(value)
        self.position_changed.emit(self._position)

    def _on_duration(self, value: int) -> None:
        if value > 0:
            self._duration = int(value)
            self.duration_changed.emit(self._duration)
            if self._track is not None and not self._track.duration_ms:
                self._track.duration_ms = self._duration

    def _on_state(self, state: str) -> None:
        if state == "playing" and self._track is not None:
            self._failures = 0
            self._paused_at = 0.0
            self.track_started.emit(self._track)
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
            # Cached stream may have been truncated: drop the cache entry once.
            if self._fallback_tried.isdisjoint({track.source_id}):
                self._fallback_tried.add(track.source_id)
                self.status_message.emit("在线音频读取失败，正在重新获取…")
                self._resolve_generation += 1
                self._load(track, position=self._position, autoplay=True, force_resolve=True)
                return
        self.status_message.emit(message)
        self._failures += 1
        if self._failures < MAX_CONSECUTIVE_FAILURES and self.queue.count > 1:
            QTimer.singleShot(700, lambda: self.next(auto=True))
        else:
            # never leave the UI in a fake playing/loading state after a fatal
            # error: stop the pipeline and clear the busy flag
            self._resolve_generation += 1
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


__all__ = ["PlayerController", "ResolvedStream"]
