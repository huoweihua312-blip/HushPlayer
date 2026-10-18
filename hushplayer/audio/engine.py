"""Thin, predictable wrapper around ``QMediaPlayer`` + ``QAudioOutput``.

The engine knows nothing about queues, libraries or online sources: it plays one
URL at a time and reports what happened.  Everything above it (see
``hushplayer.audio.controller``) owns the state machine.

Design notes
------------
* ``QMediaPlayer`` is created once and reused.  Recreating it per track leaks
  FFmpeg backends and causes audible gaps.
* Volume is mapped through a logarithmic curve so the slider feels linear.
* ``position_changed`` is throttled by Qt itself (~every 100 ms); we do not add
  another timer on top.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from ..core.logging_setup import get_logger

log = get_logger("audio.engine")

STATE_STOPPED = "stopped"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_LOADING = "loading"


def _convert_volume(value: float) -> float:
    """Map a 0..1 slider position to a perceptual linear amplitude."""
    value = max(0.0, min(1.0, float(value)))
    try:
        from PySide6.QtMultimedia import QAudio

        return float(
            QAudio.convertVolume(
                value,
                QAudio.VolumeScale.LogarithmicVolumeScale,
                QAudio.VolumeScale.LinearVolumeScale,
            )
        )
    except Exception:  # pragma: no cover - older Qt or missing enum
        return value**2


class PlaybackEngine(QObject):
    position_changed = Signal(int)
    duration_changed = Signal(int)
    state_changed = Signal(str)
    media_changed = Signal()          # new source attached
    end_of_media = Signal()
    error_occurred = Signal(str, bool)  # message, fatal
    buffering_changed = Signal(int)     # 0..100, -1 when unknown

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)

        self._source: str = ""
        self._state: str = STATE_STOPPED
        self._volume: float = 0.72
        self._muted: bool = False
        self._ended: bool = False
        self._duration_hint: int = 0
        self._error_count: int = 0

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)
        self._player.bufferProgressChanged.connect(self._on_buffer)

        self._output.setVolume(_convert_volume(self._volume))
        self._output.setMuted(False)

    # ------------------------------------------------------------- properties
    @property
    def player(self) -> QMediaPlayer:
        return self._player

    @property
    def source(self) -> str:
        return self._source

    @property
    def state(self) -> str:
        return self._state

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    def position(self) -> int:
        return int(self._player.position())

    def duration(self) -> int:
        reported = int(self._player.duration())
        if reported > 0:
            return reported
        return self._duration_hint

    def is_playing(self) -> bool:
        return self._state == STATE_PLAYING

    def available(self) -> bool:
        return self._player.isAvailable()

    # --------------------------------------------------------------- loading
    @staticmethod
    def to_url(source: str) -> QUrl:
        if not source:
            return QUrl()
        lowered = source.lower()
        if lowered.startswith(("http://", "https://", "file://", "qrc:")):
            return QUrl(source)
        return QUrl.fromLocalFile(os.path.abspath(source))

    def load(self, source: str, *, duration_hint: int = 0, autoplay: bool = True) -> None:
        """Attach ``source`` and optionally start playing."""
        self._duration_hint = int(duration_hint or 0)
        self._ended = False
        self._error_count = 0
        self._set_state(STATE_LOADING if autoplay else STATE_STOPPED)
        self._source = source or ""
        self._player.stop()
        self._player.setSource(self.to_url(source))
        self.media_changed.emit()
        if autoplay:
            self._player.play()

    def unload(self) -> None:
        self._source = ""
        self._duration_hint = 0
        self._player.stop()
        self._player.setSource(QUrl())
        self._set_state(STATE_STOPPED)

    # --------------------------------------------------------------- control
    def play(self) -> None:
        if not self._source:
            return
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self._state == STATE_PLAYING:
            self.pause()
        else:
            if self._state == STATE_LOADING or not self._source:
                return
            self.play()

    def stop(self) -> None:
        self._player.stop()
        self._set_state(STATE_STOPPED)

    def seek(self, ms: int) -> None:
        target = max(0, int(ms))
        total = self.duration()
        if total > 0:
            target = min(target, total)
        self._player.setPosition(target)
        self.position_changed.emit(target)

    def set_volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, float(value)))
        if not self._muted:
            self._output.setVolume(_convert_volume(self._volume))
        self._player.setAudioOutput(self._output)

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._output.setMuted(self._muted)
        if not self._muted:
            self._output.setVolume(_convert_volume(self._volume))

    def toggle_mute(self) -> None:
        self.set_muted(not self._muted)

    def set_audio_device(self, device) -> None:
        if device is not None:
            self._output.setDevice(device)

    def audio_device(self):
        return self._output.device()

    # ----------------------------------------------------------------- slots
    def _set_state(self, state: str) -> None:
        if self._state != state:
            self._state = state
            self.state_changed.emit(state)

    def _on_position(self, value: int) -> None:
        self.position_changed.emit(int(value))

    def _on_duration(self, value: int) -> None:
        if value > 0:
            self._duration_hint = int(value)
        self.duration_changed.emit(self.duration())

    def _on_playback_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_state(STATE_PLAYING)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._set_state(STATE_PAUSED)
        else:
            if self._state not in (STATE_STOPPED, STATE_LOADING):
                self._set_state(STATE_STOPPED)

    def _on_media_status(self, status) -> None:
        enum = QMediaPlayer.MediaStatus
        if status == enum.EndOfMedia:
            if not self._ended:
                self._ended = True
                self._set_state(STATE_STOPPED)
                self.end_of_media.emit()
        elif status in (enum.LoadingMedia, enum.BufferingMedia):
            if self._state not in (STATE_PLAYING, STATE_PAUSED):
                self._set_state(STATE_LOADING)
        elif status == enum.BufferedMedia:
            if self._state == STATE_LOADING:
                self._set_state(STATE_PAUSED)
        elif status == enum.NoMedia:
            self.buffering_changed.emit(0)

    def _on_buffer(self, percent: int) -> None:
        self.buffering_changed.emit(int(percent))

    def _on_error(self, error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        self._error_count += 1
        text = (message or "").strip()
        name = getattr(error, "name", str(error))
        detail = f"{name}: {text}" if text else str(name)
        if "InvalidMedia" in name or "FormatError" in name:
            detail = f"无法播放该音频（{detail}）"
        elif "ResourceError" in name:
            detail = f"无法读取音频资源（{detail}）"
        elif "AccessDenied" in name:
            detail = f"没有访问该音频的权限（{detail}）"
        elif "NetworkError" in name:
            detail = f"网络错误，无法加载音频（{detail}）"
        log.warning("playback error: %s", detail)
        self._set_state(STATE_STOPPED)
        self.error_occurred.emit(detail, self._error_count >= 2)

    # -------------------------------------------------------------- teardown
    def shutdown(self) -> None:
        try:
            self._player.stop()
            self._player.setSource(QUrl())
        except Exception:  # pragma: no cover - teardown
            pass
        self._source = ""
        self._duration_hint = 0
        self._set_state(STATE_STOPPED)


__all__ = [
    "PlaybackEngine",
    "STATE_LOADING",
    "STATE_PAUSED",
    "STATE_PLAYING",
    "STATE_STOPPED",
]
