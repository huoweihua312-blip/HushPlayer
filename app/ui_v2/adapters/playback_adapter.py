"""Timer-driven mock playback state for UI V2 previews and tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from PySide6.QtCore import QObject, QTimer, Signal

from app.ui_v2.models.playback_state import PlaybackState, RepeatMode
from app.ui_v2.models.track import Track


class PlaybackAdapter(QObject):
    """Owns one coherent mock playback state without touching any widget."""

    track_changed = Signal(object)
    playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(object)
    volume_changed = Signal(int)
    favorite_changed = Signal(bool)
    shuffle_changed = Signal(bool)
    repeat_mode_changed = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        timer_enabled: bool = True,
        tick_interval_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self._queue: list[Track] = []
        self._state = PlaybackState()
        self._timer = QTimer(self)
        self._timer.setInterval(max(100, int(tick_interval_ms)))
        self._timer.timeout.connect(self._on_timer_timeout)
        self._timer_enabled = bool(timer_enabled)

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def has_tracks(self) -> bool:
        return any(not track.is_missing for track in self._queue)

    def set_queue(self, tracks: Iterable[Track]) -> None:
        current_id = self._state.current_track.id if self._state.current_track else ""
        self._queue = list(tracks)
        if current_id and not any(track.id == current_id for track in self._queue):
            self.clear()
            return
        if current_id:
            current_index = next(
                index for index, track in enumerate(self._queue) if track.id == current_id
            )
            self._state = replace(self._state, current_index=current_index)

    def update_track(self, updated: Track) -> None:
        """Refresh one mock queue reference after shared UI-only metadata changes."""
        self._queue = [
            updated if track.id == updated.id else track for track in self._queue
        ]
        current = self._state.current_track
        if current is not None and current.id == updated.id:
            self._state = replace(self._state, current_track=updated)

    def play_track(self, track_id: str) -> None:
        target_index = next(
            (
                index
                for index, track in enumerate(self._queue)
                if track.id == track_id and not track.is_missing
            ),
            -1,
        )
        if target_index < 0:
            return
        track = self._queue[target_index]
        self._state = replace(
            self._state,
            current_track=track,
            current_index=target_index,
            is_playing=True,
            position_ms=0,
            duration_ms=track.duration_ms,
            is_favorite=track.is_favorite,
        )
        self.track_changed.emit(track)
        self.duration_changed.emit(track.duration_ms)
        self.position_changed.emit(0)
        self.favorite_changed.emit(track.is_favorite)
        self.playing_changed.emit(True)
        self._start_timer()

    def play(self) -> None:
        if self._state.current_track is None:
            first_available = next(
                (track for track in self._queue if not track.is_missing), None
            )
            if first_available is not None:
                self.play_track(first_available.id)
            return
        if self._state.is_playing:
            return
        self._state = replace(self._state, is_playing=True)
        self.playing_changed.emit(True)
        self._start_timer()

    def pause(self) -> None:
        if not self._state.is_playing:
            return
        self._state = replace(self._state, is_playing=False)
        self._timer.stop()
        self.playing_changed.emit(False)

    def toggle_playback(self) -> None:
        self.pause() if self._state.is_playing else self.play()

    def play_previous(self) -> None:
        self._play_relative(-1)

    def play_next(self) -> None:
        self._play_relative(1)

    def seek(self, position_ms: int) -> None:
        duration = self._state.duration_ms
        if self._state.current_track is None or duration is None:
            return
        position = max(0, min(int(position_ms), duration))
        if position == self._state.position_ms:
            return
        self._state = replace(self._state, position_ms=position)
        self.position_changed.emit(position)

    def set_volume(self, value: int) -> None:
        volume = max(0, min(100, int(value)))
        if volume == self._state.volume:
            return
        self._state = replace(self._state, volume=volume)
        self.volume_changed.emit(volume)

    def toggle_favorite(self) -> None:
        if self._state.current_track is None:
            return
        self.set_current_favorite(not self._state.is_favorite)

    def set_current_favorite(self, value: bool) -> None:
        if self._state.current_track is None or bool(value) == self._state.is_favorite:
            return
        self._state = replace(self._state, is_favorite=bool(value))
        self.favorite_changed.emit(self._state.is_favorite)

    def toggle_shuffle(self) -> None:
        self._state = replace(
            self._state, shuffle_enabled=not self._state.shuffle_enabled
        )
        self.shuffle_changed.emit(self._state.shuffle_enabled)

    def cycle_repeat_mode(self) -> None:
        sequence = (RepeatMode.ALL, RepeatMode.ONE, RepeatMode.OFF)
        current_index = sequence.index(self._state.repeat_mode)
        self._state = replace(
            self._state, repeat_mode=sequence[(current_index + 1) % len(sequence)]
        )
        self.repeat_mode_changed.emit(self._state.repeat_mode)

    def clear(self) -> None:
        self._timer.stop()
        self._state = PlaybackState()
        self.track_changed.emit(None)
        self.playing_changed.emit(False)
        self.duration_changed.emit(None)
        self.position_changed.emit(0)
        self.volume_changed.emit(self._state.volume)
        self.favorite_changed.emit(False)
        self.shuffle_changed.emit(False)
        self.repeat_mode_changed.emit(self._state.repeat_mode)

    def advance_for_test(self, elapsed_ms: int) -> None:
        """Advance mock playback deterministically without depending on QTimer."""
        self._advance_position(max(0, int(elapsed_ms)))

    def _start_timer(self) -> None:
        if self._timer_enabled and not self._timer.isActive():
            self._timer.start()

    def _on_timer_timeout(self) -> None:
        self._advance_position(self._timer.interval())

    def _advance_position(self, elapsed_ms: int) -> None:
        if not self._state.is_playing or self._state.current_track is None:
            return
        duration = self._state.duration_ms
        if duration is None:
            return
        target = self._state.position_ms + elapsed_ms
        if target < duration:
            self._state = replace(self._state, position_ms=target)
            self.position_changed.emit(target)
            return
        self._handle_track_end(duration)

    def _handle_track_end(self, duration: int) -> None:
        if self._state.repeat_mode == RepeatMode.ONE:
            self._state = replace(self._state, position_ms=0)
            self.position_changed.emit(0)
            return
        if self._state.repeat_mode == RepeatMode.OFF:
            self._state = replace(self._state, position_ms=duration, is_playing=False)
            self.position_changed.emit(duration)
            self.playing_changed.emit(False)
            self._timer.stop()
            return
        self.play_next()

    def _play_relative(self, offset: int) -> None:
        available = [track for track in self._queue if not track.is_missing]
        if not available:
            return
        if self._state.current_track is None:
            self.play_track(available[0].id)
            return
        if self._state.shuffle_enabled and len(available) > 1:
            current = next(
                index
                for index, track in enumerate(available)
                if track.id == self._state.current_track.id
            )
            next_track = available[(current + (3 if offset > 0 else -3)) % len(available)]
            self.play_track(next_track.id)
            return
        current = next(
            index
            for index, track in enumerate(available)
            if track.id == self._state.current_track.id
        )
        self.play_track(available[(current + offset) % len(available)].id)
