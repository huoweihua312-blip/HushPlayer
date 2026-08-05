"""One UI-independent local playback backend for formal application shells."""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from app.models.playback_queue_item import PlaybackQueueItem
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
        self.queue.replace(values, active_identity)
        if self._current_item is not None and self.queue.current_identity != self._current_item.stable_identity:
            self._current_item = self.queue.current_item
        self.queue_changed.emit(tuple(self.queue.items))

    def play_item(self, value: PlaybackQueueItem | str) -> bool:
        identity = value.stable_identity if isinstance(value, PlaybackQueueItem) else str(value or "")
        index = self.queue.index_for_identity(identity)
        if index < 0:
            self._emit_error("The requested track is not in the playback queue.")
            return False
        item = self.queue.items[index]
        if item.kind != "local":
            self._emit_error("Online playback is not available in this version.")
            return False
        path = Path(item.local_path)
        if not path.is_file():
            self._emit_error("The local audio file is unavailable.")
            return False

        self.queue.set_current_identity(item.stable_identity)
        self._current_item = item
        self._duration_ms = None
        self._generation += 1
        self._handled_end_generation = -1
        self.track_changed.emit(item)
        self.duration_changed.emit(None)
        self.position_changed.emit(0)
        self.queue_changed.emit(tuple(self.queue.items))
        try:
            self.media_player.stop()
            self.media_player.setSource(QUrl.fromLocalFile(str(path)))
            self.media_player.setPosition(0)
            self.media_player.play()
        except (RuntimeError, OSError) as error:
            self._set_playing(False)
            self._emit_error(str(error) or "The local audio file could not be played.")
            return False
        self._set_playing(True)
        return True

    def play(self) -> bool:
        if self._current_item is None:
            item = next((value for value in self.queue.items if value.kind == "local"), None)
            return self.play_item(item) if item is not None else False
        if self._current_item.kind != "local":
            self._emit_error("Online playback is not available in this version.")
            return False
        if not Path(self._current_item.local_path).is_file():
            self._emit_error("The local audio file is unavailable.")
            return False
        self.media_player.play()
        self._set_playing(True)
        return True

    def pause(self) -> None:
        if self._is_playing:
            self.media_player.pause()
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
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.queue.clear()
        self._current_item = None
        self._duration_ms = None
        self._generation += 1
        self._handled_end_generation = -1
        self.track_changed.emit(None)
        self.duration_changed.emit(None)
        self.position_changed.emit(0)
        self._set_playing(False)
        self.queue_changed.emit(())

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
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

    def _emit_error(self, message: str) -> None:
        self._set_playing(False)
        self.error_occurred.emit(str(message or "Playback failed."))

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

    @Slot(object)
    def _on_media_status_changed(self, status) -> None:
        self.media_status_changed.emit(status)
        if (
            self._end_of_media_enabled
            and status == QMediaPlayer.MediaStatus.EndOfMedia
            and self._current_item is not None
        ):
            self._handle_end_of_media()

    @Slot(object, str)
    def _on_player_error(self, _error, message: str) -> None:
        self._emit_error(message or self.media_player.errorString())

    @Slot(bool)
    def _on_muted_changed(self, value: bool) -> None:
        self.muted_changed.emit(bool(value))
