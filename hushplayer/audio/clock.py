"""Interpolating playback clock.

``QMediaPlayer`` reports ``positionChanged`` a handful of times per second, which
is enough for a progress bar but visibly steppy for karaoke-style lyric sweeps.
This clock keeps the last reported position, extrapolates it with a monotonic
timer while audio is playing, and emits a 60 Hz ``tick`` so lyric views can
animate smoothly without polling the media player.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal

TICK_INTERVAL_MS = 16
#: A reported position this far away from the extrapolated one resets the clock
#: (seeks, buffering, resume-after-pause all land here).
RESYNC_THRESHOLD_MS = 140


class PlaybackClock(QObject):
    """Smoothly interpolated playback position."""

    tick = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._base_ms = 0
        self._base_at = time.monotonic()
        self._playing = False
        self._duration = 0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------ 状态
    def set_position(self, position_ms: int) -> None:
        position_ms = max(0, int(position_ms))
        # Every authoritative report (including seeks) restarts the interpolation
        # window, so drift never accumulates across a pause or a seek.
        self._base_ms = position_ms
        self._base_at = time.monotonic()
        if not self._playing:
            self.tick.emit(self._base_ms)

    def set_playing(self, playing: bool) -> None:
        playing = bool(playing)
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._base_at = time.monotonic()
            self._timer.start()
        else:
            self._base_ms = self.position()
            self._base_at = time.monotonic()
            self._timer.stop()
            self.tick.emit(self._base_ms)

    def set_duration(self, duration_ms: int) -> None:
        self._duration = max(0, int(duration_ms))

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def duration(self) -> int:
        return self._duration

    def position(self) -> int:
        if not self._playing:
            return self._base_ms
        elapsed_ms = int((time.monotonic() - self._base_at) * 1000)
        value = self._base_ms + max(0, elapsed_ms)
        if self._duration and value > self._duration:
            value = self._duration
        return value

    def reset(self) -> None:
        self._base_ms = 0
        self._base_at = time.monotonic()
        self._duration = 0
        self._timer.stop()
        self._playing = False
        self.tick.emit(0)

    def shutdown(self) -> None:
        self._timer.stop()

    # ------------------------------------------------------------------ 内部
    def _on_tick(self) -> None:
        self.tick.emit(self.position())


__all__ = ["PlaybackClock", "RESYNC_THRESHOLD_MS", "TICK_INTERVAL_MS"]
