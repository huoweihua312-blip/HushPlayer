"""One UI-independent local playback backend for formal application shells."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from app.models.media_item import MediaItem
from app.models.playback_queue_item import PlaybackQueueItem
from app.services.online_audio_cache import OnlineAudioCacheService
from app.services.online_media_resolver import OnlineMediaResolver
from app.services.playback_queue import PlaybackQueue


class ProductionPlaybackController(QObject):
    """Own the one local QMediaPlayer backend and formal PlaybackQueue.

    This controller intentionally has no widget knowledge.  The legacy window
    may retain its established online/session handling around these owned Qt
    objects, while UI V2 uses the command and state bridge directly for local
    playback.
    """

    track_changed = Signal(object)
    playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(object)
    volume_changed = Signal(int)
    muted_changed = Signal(bool)
    play_mode_changed = Signal(str)
    queue_changed = Signal(object)
    error_occurred = Signal(str)
    media_status_changed = Signal(object)
    playback_status_changed = Signal(str, str)
    remote_track_state_changed = Signal(str, str, str, object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        queue: PlaybackQueue | None = None,
        volume: int = 65,
        play_mode: str = "list_loop",
        handle_end_of_media: bool = True,
        media_player: QMediaPlayer | None = None,
        audio_output: QAudioOutput | None = None,
        media_devices: QMediaDevices | None = None,
        online_resolver: OnlineMediaResolver | None = None,
        online_audio_cache: OnlineAudioCacheService | None = None,
        online_cache_allowed: Callable[[MediaItem], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue or PlaybackQueue()
        self._play_mode = self._normalize_play_mode(play_mode)
        self._end_of_media_enabled = bool(handle_end_of_media)
        self._current_item: PlaybackQueueItem | None = self.queue.current_item
        self._duration_ms: int | None = None
        self._is_playing = False
        self._generation = 0
        self._handled_end_generation = -1
        self._last_end_at = 0.0
        self._closed = False
        self._playback_status = "idle"
        self._online_resolver: OnlineMediaResolver | None = None
        self._pending_online_token = 0
        self._resolved_online_identity = ""
        self._online_audio_cache: OnlineAudioCacheService | None = None
        self._online_cache_allowed: Callable[[MediaItem], bool] = (
            online_cache_allowed or (lambda _media_item: False)
        )
        self._online_recovery_generation = -1
        self._online_recovery_attempted = False
        self._online_cache_key = ""
        self._switching_item = False
        self._deferred_online_cache: tuple[int, str, MediaItem, dict] | None = None
        self._online_cache_timer = QTimer(self)
        self._online_cache_timer.setSingleShot(True)
        self._online_cache_timer.setInterval(250)
        self._online_cache_timer.timeout.connect(self._flush_deferred_online_cache)

        self.media_devices = media_devices or QMediaDevices(self)
        self.default_audio_output_sync_timer = QTimer(self)
        self.default_audio_output_sync_timer.setSingleShot(True)
        self.default_audio_output_sync_timer.setInterval(250)
        self.default_audio_output_sync_timer.timeout.connect(
            self.sync_default_audio_output
        )
        self.media_devices.audioOutputsChanged.connect(
            self.schedule_default_audio_output_sync
        )

        default_device = QMediaDevices.defaultAudioOutput()
        self.audio_output = audio_output or QAudioOutput(default_device, self)
        self.media_player = media_player or QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.set_volume(volume)
        self.sync_default_audio_output()

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.media_player.errorOccurred.connect(self._on_player_error)
        muted_changed = getattr(self.audio_output, "mutedChanged", None)
        if muted_changed is not None:
            muted_changed.connect(self._on_muted_changed)

        if default_device.isNull():
            self.error_occurred.emit("No audio output device is available.")
        self.set_online_resolver(online_resolver)
        self.set_online_audio_cache(
            online_audio_cache,
            cache_allowed=online_cache_allowed,
        )

    @property
    def current_item(self) -> PlaybackQueueItem | None:
        return self._current_item

    @property
    def current_index(self) -> int:
        return self.queue.current_index

    @property
    def duration_ms(self) -> int | None:
        return self._duration_ms

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def playback_status(self) -> str:
        return self._playback_status

    @property
    def play_mode(self) -> str:
        return self._play_mode

    @property
    def volume(self) -> int:
        return max(0, min(100, round(float(self.audio_output.volume()) * 100)))

    @property
    def is_muted(self) -> bool:
        is_muted = getattr(self.audio_output, "isMuted", None)
        return bool(is_muted()) if callable(is_muted) else False

    @staticmethod
    def _normalize_play_mode(value: str) -> str:
        return value if value in PlaybackQueue.VALID_MODES else "list_loop"

    def set_online_resolver(self, resolver: OnlineMediaResolver | None) -> None:
        if resolver is self._online_resolver:
            return
        if self._online_resolver is not None:
            for signal, slot in (
                (self._online_resolver.resolve_succeeded, self._on_online_resolved),
                (self._online_resolver.resolve_failed, self._on_online_resolve_failed),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self._online_resolver = resolver
        if resolver is not None:
            resolver.resolve_succeeded.connect(self._on_online_resolved)
            resolver.resolve_failed.connect(self._on_online_resolve_failed)

    def set_online_audio_cache(
        self,
        cache: OnlineAudioCacheService | None,
        *,
        cache_allowed: Callable[[MediaItem], bool] | None = None,
    ) -> None:
        """Attach the one existing cache without creating another playback owner."""

        self._online_audio_cache = cache
        if cache_allowed is not None:
            self._online_cache_allowed = cache_allowed

    @staticmethod
    def audio_device_name(device) -> str:
        if device is None or device.isNull():
            return "Unavailable output"
        return device.description() or "Unnamed output"

    @Slot()
    def schedule_default_audio_output_sync(self) -> None:
        if not self._closed:
            self.default_audio_output_sync_timer.start()

    @Slot()
    def sync_default_audio_output(self) -> None:
        if not self._closed:
            self.apply_default_audio_output(QMediaDevices.defaultAudioOutput())

    def apply_default_audio_output(self, default_device) -> bool:
        current_device = self.audio_output.device()
        if default_device is None or default_device.isNull():
            self.error_occurred.emit("No audio output device is available.")
            return False
        if (
            current_device is not None
            and not current_device.isNull()
            and bytes(current_device.id()) == bytes(default_device.id())
        ):
            return False
        self.audio_output.setDevice(default_device)
        return True

    def set_queue(
        self,
        values: Iterable[PlaybackQueueItem],
        *,
        current_identity: str = "",
    ) -> None:
        active_identity = current_identity or self.queue.current_identity
        previous_identity = self._current_item.stable_identity if self._current_item else ""
        self.queue.replace(values, active_identity)
        if self._current_item is not None and self.queue.current_identity != self._current_item.stable_identity:
            self._current_item = self.queue.current_item
        if previous_identity and previous_identity != self.queue.current_identity:
            self._cancel_online_resolution()
        self.queue_changed.emit(tuple(self.queue.items))

    def play_item(self, value: PlaybackQueueItem | str) -> bool:
        identity = value.stable_identity if isinstance(value, PlaybackQueueItem) else str(value or "")
        index = self.queue.index_for_identity(identity)
        if index < 0:
            self._emit_error("The requested track is not in the playback queue.")
            return False
        item = self.queue.items[index]
        if item.kind == "local":
            path = Path(item.local_path)
            if not path.is_file():
                self._emit_error("The local audio file is unavailable.")
                return False

        self._cancel_online_resolution()
        self._switching_item = True
        self.queue.set_current_identity(item.stable_identity)
        self._current_item = item
        self._duration_ms = (
            max(0, int(item.media_item.duration * 1000))
            if item.media_item.duration > 0
            else None
        )
        self._generation += 1
        self._handled_end_generation = -1
        self._resolved_online_identity = ""
        self._online_recovery_generation = self._generation
        self._online_recovery_attempted = False
        self._online_cache_key = ""
        try:
            self.media_player.stop()
            if item.kind == "local":
                self.media_player.setSource(QUrl.fromLocalFile(str(path)))
                self.media_player.setPosition(0)
                self._set_status("loading", "正在加载本地歌曲…")
                self.media_player.play()
                self._switching_item = False
                self._emit_track_context(item)
                self._set_playing(True)
                return True
            else:
                self.media_player.setSource(QUrl())
                cache_record = self._valid_online_cache(item.media_item)
                if cache_record is not None:
                    cache_path = Path(str(cache_record.get("local_path") or ""))
                    if self._start_online_media_source(
                        item,
                        QUrl.fromLocalFile(str(cache_path)),
                        detail="正在从本地音频缓存加载…",
                        state_detail="正在使用本地音频缓存。",
                        payload={
                            "cached": True,
                            "cacheKey": str(cache_record.get("cache_key") or ""),
                        },
                        cache_key=str(cache_record.get("cache_key") or ""),
                    ):
                        self._switching_item = False
                        self._emit_track_context(item)
                        return True
        except (RuntimeError, OSError) as error:
            self._switching_item = False
            self._emit_track_context(item)
            self._set_playing(False)
            self._emit_error(str(error) or "The local audio file could not be played.")
            return False

        self._emit_track_context(item)
        self._set_status("resolving", "正在解析在线播放地址…")
        resolver = self._online_resolver
        if resolver is None:
            self._switching_item = False
            self._emit_remote_state(
                item.stable_identity,
                "source_unavailable",
                "当前在线来源不可用。",
                {},
            )
            self._emit_error("暂时无法播放这首在线歌曲。")
            return False
        self._pending_online_token = resolver.resolve(item, self._generation)
        self._switching_item = False
        if not self._pending_online_token:
            self._emit_remote_state(
                item.stable_identity,
                "resolve_failed",
                "暂时无法播放这首在线歌曲。",
                {},
            )
            self._emit_error("暂时无法播放这首在线歌曲。")
            return False
        self._emit_remote_state(
            item.stable_identity,
            "resolving",
            "正在解析在线播放地址…",
            {},
        )
        self._set_playing(False)
        return True

    def _emit_track_context(self, item: PlaybackQueueItem) -> None:
        """Publish the new track after the media transition has been started."""

        self.track_changed.emit(item)
        self.duration_changed.emit(self._duration_ms)
        self.position_changed.emit(0)
        self.queue_changed.emit(tuple(self.queue.items))

    def play(self) -> bool:
        if self._current_item is None:
            item = next((value for value in self.queue.items if value.kind == "local"), None)
            return self.play_item(item) if item is not None else False
        if self._current_item.kind == "remote":
            if (
                self._resolved_online_identity == self._current_item.stable_identity
                and self.media_player.source().isValid()
            ):
                self.media_player.play()
                self._set_status("playing", "正在播放")
                self._set_playing(True)
                return True
            return self.play_item(self._current_item)
        if not Path(self._current_item.local_path).is_file():
            self._emit_error("The local audio file is unavailable.")
            return False
        self.media_player.play()
        self._set_status("playing", "正在播放")
        self._set_playing(True)
        return True

    def pause(self) -> None:
        if self._playback_status == "resolving":
            self._cancel_online_resolution()
            self._set_status("paused", "已暂停")
            self._set_playing(False)
            return
        if self._is_playing:
            self.media_player.pause()
            self._set_status("paused", "已暂停")
            self._set_playing(False)

    def toggle_playback(self) -> None:
        self.pause() if self._is_playing else self.play()

    def play_previous(self) -> bool:
        return self._play_relative(-1)

    def play_next(self) -> bool:
        return self._play_relative(1)

    def seek(self, position_ms: int) -> bool:
        if self._current_item is None or self._duration_ms is None:
            return False
        seekable = getattr(self.media_player, "isSeekable", None)
        if callable(seekable) and not seekable():
            return False
        if self._playback_status == "resolving":
            return False
        target = max(0, min(int(position_ms), self._duration_ms))
        self.media_player.setPosition(target)
        self.position_changed.emit(target)
        return True

    def set_volume(self, value: int) -> None:
        volume = max(0, min(100, int(value)))
        if volume == self.volume:
            return
        self.audio_output.setVolume(volume / 100)
        self.volume_changed.emit(volume)

    def set_muted(self, value: bool) -> None:
        set_muted = getattr(self.audio_output, "setMuted", None)
        if callable(set_muted):
            set_muted(bool(value))
        self.muted_changed.emit(bool(value))

    def set_play_mode(self, value: str) -> None:
        mode = self._normalize_play_mode(value)
        if mode == self._play_mode:
            return
        self._play_mode = mode
        self.play_mode_changed.emit(mode)

    def clear(self) -> None:
        self._cancel_online_resolution()
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.queue.clear()
        self._current_item = None
        self._duration_ms = None
        self._generation += 1
        self._handled_end_generation = -1
        self._resolved_online_identity = ""
        self._online_recovery_generation = self._generation
        self._online_recovery_attempted = False
        self._online_cache_key = ""
        self.track_changed.emit(None)
        self.duration_changed.emit(None)
        self.position_changed.emit(0)
        self._set_playing(False)
        self._set_status("idle", "")
        self.queue_changed.emit(())

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_online_resolution()
        self._online_cache_timer.stop()
        self._deferred_online_cache = None
        self.default_audio_output_sync_timer.stop()
        self.media_player.stop()
        self.media_player.setSource(QUrl())

    def _play_relative(self, direction: int) -> bool:
        if not self.queue.items:
            return False
        index = self.queue.next_index(self._play_mode, direction)
        if index is None:
            self._set_playing(False)
            return False
        return self.play_item(self.queue.items[index])

    def _handle_end_of_media(self) -> None:
        generation = self._generation
        now = time.monotonic()
        if (
            self._handled_end_generation == generation
            or now - self._last_end_at < 0.35
        ):
            return
        self._handled_end_generation = generation
        self._last_end_at = now
        self._set_playing(False)
        self.play_next()

    def _set_playing(self, value: bool) -> None:
        value = bool(value)
        if value == self._is_playing:
            return
        self._is_playing = value
        self.playing_changed.emit(value)

    def _set_status(self, status: str, detail: str = "") -> None:
        normalized = str(status or "idle")
        if normalized == self._playback_status and not detail:
            return
        self._playback_status = normalized
        self.playback_status_changed.emit(normalized, str(detail or ""))

    def _cancel_online_resolution(self) -> None:
        resolver = self._online_resolver
        if resolver is not None:
            resolver.cancel_active()
        self._pending_online_token = 0
        self._online_cache_timer.stop()
        self._deferred_online_cache = None

    def _valid_online_cache(self, media_item: MediaItem) -> dict | None:
        cache = self._online_audio_cache
        if cache is None:
            return None
        try:
            record = cache.valid_cache(media_item)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None
        return dict(record) if isinstance(record, dict) else None

    def _online_cache_is_allowed(self, media_item: MediaItem) -> bool:
        if self._online_audio_cache is None:
            return False
        try:
            return bool(self._online_cache_allowed(media_item))
        except Exception:
            return False

    def _start_online_media_source(
        self,
        item: PlaybackQueueItem,
        source: QUrl,
        *,
        detail: str,
        state_detail: str,
        payload: dict,
        cache_key: str = "",
    ) -> bool:
        if not source.isValid():
            return False
        try:
            self.media_player.stop()
            self.media_player.setSource(source)
            self.media_player.setPosition(0)
            self._resolved_online_identity = item.stable_identity
            self._online_cache_key = str(cache_key or "")
            self._set_status("buffering", detail)
            self._emit_remote_state(
                item.stable_identity,
                "playable",
                state_detail,
                payload,
            )
            self.media_player.play()
            return True
        except (RuntimeError, OSError):
            self._resolved_online_identity = ""
            self._online_cache_key = ""
            return False

    def _start_online_cache(self, media_item: MediaItem, resolution: dict) -> None:
        cache = self._online_audio_cache
        if cache is None or not self._online_cache_is_allowed(media_item):
            return
        self._deferred_online_cache = (
            self._generation,
            media_item.stable_identity,
            media_item,
            dict(resolution),
        )
        self._online_cache_timer.start()

    def _flush_deferred_online_cache(self) -> None:
        pending = self._deferred_online_cache
        self._deferred_online_cache = None
        if pending is None or self._closed:
            return
        generation, identity, media_item, resolution = pending
        current = self._current_item
        if (
            generation != self._generation
            or current is None
            or current.kind != "remote"
            or current.stable_identity != identity
            or self._online_audio_cache is None
        ):
            return
        try:
            self._online_audio_cache.start_cache(media_item, resolution)
        except (OSError, RuntimeError, TypeError, ValueError):
            return

    def _try_recover_online_playback(self, reason: str) -> bool:
        item = self._current_item
        if (
            self._closed
            or item is None
            or item.kind != "remote"
            or self._pending_online_token
            or self._resolved_online_identity != item.stable_identity
        ):
            return False
        if self._online_recovery_generation != self._generation:
            self._online_recovery_generation = self._generation
            self._online_recovery_attempted = False
        if self._online_recovery_attempted:
            return False
        self._online_recovery_attempted = True
        self._resolved_online_identity = ""
        self._online_cache_key = ""

        cache_record = self._valid_online_cache(item.media_item)
        if cache_record is not None:
            cache_path = Path(str(cache_record.get("local_path") or ""))
            if self._start_online_media_source(
                item,
                QUrl.fromLocalFile(str(cache_path)),
                detail="正在从本地音频缓存恢复…",
                state_detail="正在使用本地音频缓存恢复播放。",
                payload={
                    "cached": True,
                    "cacheKey": str(cache_record.get("cache_key") or ""),
                    "recovery": True,
                },
                cache_key=str(cache_record.get("cache_key") or ""),
            ):
                return True

        resolver = self._online_resolver
        if resolver is None:
            return False
        self._set_status("resolving", "正在刷新在线播放地址…")
        self._set_playing(False)
        token = resolver.resolve(item, self._generation)
        self._pending_online_token = int(token or 0)
        if not self._pending_online_token:
            return False
        self._emit_remote_state(
            item.stable_identity,
            "resolving",
            f"正在刷新在线播放地址：{reason}",
            {},
        )
        return True

    def _online_error_message(self, code: str, detail: str) -> str:
        if code in {"SourceUnavailable", "Unavailable", "PermissionDenied"}:
            return "暂时无法播放这首在线歌曲：当前来源不可用。"
        if code == "NoPlayableMedia":
            return "暂时无法播放这首在线歌曲：来源没有可播放媒体。"
        if code == "ExpiredMedia":
            return "暂时无法播放这首在线歌曲：播放地址已失效。"
        if code == "UnsupportedMedia":
            return "暂时无法播放这首在线歌曲：当前媒体格式不受支持。"
        if code == "NetworkError":
            return "暂时无法播放这首在线歌曲：网络暂不可用。"
        if code == "Cancelled":
            return "在线播放请求已取消。"
        return "暂时无法播放这首在线歌曲。"

    @staticmethod
    def _online_failure_state(code: str) -> str:
        normalized = str(code or "").strip()
        if normalized in {"SourceUnavailable", "Unavailable"}:
            return "source_unavailable"
        if normalized == "PermissionDenied":
            return "permission_denied"
        if normalized in {
            "NoPlayableMedia",
            "ExpiredMedia",
            "UnsupportedMedia",
            "NetworkError",
        }:
            return "resolve_failed"
        return "playback_error"

    def _emit_remote_state(
        self,
        identity: str,
        state: str,
        detail: str = "",
        payload: object = None,
    ) -> None:
        if not identity:
            return
        self.remote_track_state_changed.emit(
            str(identity),
            str(state or "not_resolved"),
            str(detail or ""),
            payload if payload is not None else {},
        )

    def _emit_error(self, message: str) -> None:
        self._set_playing(False)
        self._set_status("error", str(message or "播放失败。"))
        self.error_occurred.emit(str(message or "Playback failed."))

    def _on_online_resolved(
        self,
        token: int,
        generation: int,
        identity: str,
        resolution: object,
    ) -> None:
        item = self._current_item
        if (
            int(token) != self._pending_online_token
            or int(generation) != self._generation
            or item is None
            or item.kind != "remote"
            or str(identity or "") != item.stable_identity
        ):
            return
        self._pending_online_token = 0
        payload = dict(resolution) if isinstance(resolution, dict) else {}
        if payload.get("headers"):
            self._emit_remote_state(
                item.stable_identity,
                "resolve_failed",
                "当前来源需要不支持的请求头。",
                payload,
            )
            self._emit_error("暂时无法播放这首在线歌曲：当前来源需要不支持的请求头。")
            return
        url = QUrl(str(payload.get("url") or payload.get("play_url") or ""))
        if not url.isValid() or url.scheme().lower() not in {"http", "https"}:
            self._emit_remote_state(
                item.stable_identity,
                "resolve_failed",
                "播放地址无效。",
                payload,
            )
            self._emit_error("暂时无法播放这首在线歌曲：播放地址无效。")
            return
        resolved_media_item = item.media_item.with_resolution(payload)
        if not self._start_online_media_source(
            item,
            url,
            detail="正在加载在线歌曲…",
            state_detail="在线播放地址已准备。",
            payload=payload,
        ):
            self._emit_remote_state(
                item.stable_identity,
                "playback_error",
                "当前无法播放这首在线歌曲。",
                payload,
            )
            self._emit_error("暂时无法播放这首在线歌曲。")
            return
        self._start_online_cache(resolved_media_item, payload)

    def _on_online_resolve_failed(
        self,
        token: int,
        generation: int,
        identity: str,
        code: str,
        detail: str,
    ) -> None:
        item = self._current_item
        if (
            int(token) != self._pending_online_token
            or int(generation) != self._generation
            or item is None
            or item.kind != "remote"
            or str(identity or "") != item.stable_identity
        ):
            return
        self._pending_online_token = 0
        self._resolved_online_identity = ""
        message = self._online_error_message(str(code or ""), str(detail or ""))
        self._emit_remote_state(
            item.stable_identity,
            self._online_failure_state(str(code or "")),
            message,
            {},
        )
        self._set_status(
            "unavailable" if str(code or "") in {"SourceUnavailable", "PermissionDenied"} else "error",
            message,
        )
        self._set_playing(False)
        self.error_occurred.emit(message)

    @Slot(int)
    def _on_position_changed(self, position: int) -> None:
        self.position_changed.emit(max(0, int(position)))

    @Slot(int)
    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = int(duration) if duration > 0 else None
        self.duration_changed.emit(self._duration_ms)

    @Slot(object)
    def _on_playback_state_changed(self, state) -> None:
        self._set_playing(state == QMediaPlayer.PlaybackState.PlayingState)
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_status("playing", "正在播放")
        elif state == QMediaPlayer.PlaybackState.PausedState and self._current_item is not None:
            self._set_status("paused", "已暂停")

    @Slot(object)
    def _on_media_status_changed(self, status) -> None:
        self.media_status_changed.emit(status)
        if (
            self._switching_item
            and self._current_item is not None
            and self._current_item.kind == "remote"
            and status in {
                QMediaPlayer.MediaStatus.NoMedia,
                QMediaPlayer.MediaStatus.InvalidMedia,
            }
        ):
            # Clearing the old remote source is part of an explicit track
            # switch.  Do not start a second recovery request for that
            # transient state before the new resolver request is installed.
            return
        if self._current_item is not None and self._current_item.kind == "remote":
            if status == QMediaPlayer.MediaStatus.StalledMedia:
                self._set_status("buffering", "缓冲中…")
            elif status == QMediaPlayer.MediaStatus.LoadingMedia:
                self._set_status("buffering", "正在加载在线歌曲…")
            elif status == QMediaPlayer.MediaStatus.InvalidMedia:
                if self._pending_online_token:
                    return
                if self._try_recover_online_playback("媒体无效"):
                    return
                self._emit_remote_state(
                    self._current_item.stable_identity,
                    "playback_error",
                    "暂时无法播放这首在线歌曲：媒体无效。",
                    {},
                )
                self._emit_error("暂时无法播放这首在线歌曲：媒体无效。")
        if (
            self._end_of_media_enabled
            and status == QMediaPlayer.MediaStatus.EndOfMedia
            and self._current_item is not None
        ):
            self._handle_end_of_media()

    @Slot(object, str)
    def _on_player_error(self, _error, message: str) -> None:
        if (
            self._current_item is not None
            and self._current_item.kind == "remote"
            and self._pending_online_token
        ):
            return
        if (
            self._current_item is not None
            and self._current_item.kind == "remote"
            and self._try_recover_online_playback("播放器错误")
        ):
            return
        if self._current_item is not None and self._current_item.kind == "remote":
            self._emit_remote_state(
                self._current_item.stable_identity,
                "playback_error",
                message or self.media_player.errorString(),
                {},
            )
        self._emit_error(message or self.media_player.errorString())

    @Slot(bool)
    def _on_muted_changed(self, value: bool) -> None:
        self.muted_changed.emit(bool(value))
