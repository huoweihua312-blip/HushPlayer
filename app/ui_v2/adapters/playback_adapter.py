"""Playback state bridge for UI V2 mock previews and formal local playback."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from PySide6.QtCore import QObject, QTimer, Signal

from app.models.media_item import MediaItem
from app.models.playback_queue_item import PlaybackQueueItem
from app.services.production_playback_controller import ProductionPlaybackController
from app.ui_v2.models.playback_state import PlaybackState, RepeatMode
from app.ui_v2.models.track import Track


class PlaybackAdapter(QObject):
    """Bridge one playback backend into the state expected by V2 surfaces.

    The existing timer implementation remains the isolated mock backend.  A
    production controller is supplied only by the real V2 startup path and is
    the sole owner of Qt multimedia state in that process.
    """

    track_changed = Signal(object)
    playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(object)
    volume_changed = Signal(int)
    muted_changed = Signal(bool)
    favorite_changed = Signal(bool)
    shuffle_changed = Signal(bool)
    repeat_mode_changed = Signal(object)
    queue_changed = Signal(object)
    error_occurred = Signal(str)
    playback_status_changed = Signal(str, str)
    remote_track_state_changed = Signal(str, str, str, object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        timer_enabled: bool = True,
        tick_interval_ms: int = 1000,
        controller: ProductionPlaybackController | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._queue: list[Track] = []
        self._tracks_by_identity: dict[str, Track] = {}
        self._requested_tracks_by_id: dict[str, Track] = {}
        self._state = PlaybackState()
        self._timer = QTimer(self)
        self._timer.setInterval(max(100, int(tick_interval_ms)))
        self._timer.timeout.connect(self._on_timer_timeout)
        self._timer_enabled = bool(timer_enabled) and controller is None
        if controller is not None:
            if controller.parent() is None:
                controller.setParent(self)
            self._connect_controller(controller)
            self._state = replace(
                self._state,
                volume=controller.volume,
                is_muted=controller.is_muted,
                status=controller.playback_status,
            )

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def controller(self) -> ProductionPlaybackController | None:
        return self._controller

    @property
    def has_real_backend(self) -> bool:
        return self._controller is not None

    @property
    def has_tracks(self) -> bool:
        return any(not track.is_missing or track.is_online for track in self.queue_tracks)

    @property
    def queue_tracks(self) -> tuple[Track, ...]:
        if self._controller is None:
            return tuple(self._queue)
        return tuple(
            track
            for item in self._controller.queue.items
            if (track := self._tracks_by_identity.get(item.stable_identity)) is not None
        )

    @property
    def display_queue_tracks(self) -> tuple[Track, ...]:
        """Return a current-context view for the queue surface only.

        The stable queue membership exposed by ``queue_tracks`` remains
        unchanged.  In the real backend this view follows the controller's
        sequence/shuffle history so the floating queue shows the actual next
        playback order without rewriting a playlist.
        """

        if self._controller is None:
            tracks = list(self._queue)
            current = self._state.current_track
            if current is None:
                return tuple(tracks)
            current_index = next(
                (index for index, track in enumerate(tracks) if track.id == current.id),
                -1,
            )
            if current_index < 0:
                return tuple(tracks)
            return tuple(tracks[current_index:] + tracks[:current_index])

        return tuple(
            track
            for item in self._controller.queue.presentation_items(self._controller.play_mode)
            if (track := self._tracks_by_identity.get(item.stable_identity)) is not None
        )

    def set_queue(
        self,
        tracks: Iterable[Track],
        *,
        preserve_current_context: bool = False,
    ) -> None:
        if self._controller is None:
            self._set_mock_queue(tracks)
            return
        values = tuple(tracks)
        self._requested_tracks_by_id = {track.id: track for track in values}
        playable = tuple(track for track in values if self._is_queue_playable_track(track))
        self._tracks_by_identity = {
            track.stable_identity: track for track in playable if track.stable_identity
        }
        current = self._state.current_track
        current_identity = (
            current.stable_identity
            if current is not None and current.stable_identity in self._tracks_by_identity
            else ""
        )
        self._controller.set_queue(
            (self._queue_item_from_track(track) for track in playable),
            current_identity=current_identity,
        )
        self._sync_queue_from_controller()
        if current_identity:
            self._sync_current_from_controller()
        elif self._state.current_track is not None and not preserve_current_context:
            self._controller.clear()

    def update_track(self, updated: Track) -> None:
        if self._controller is None:
            self._queue = [
                updated
                if track.id == updated.id
                else track
                for track in self._queue
            ]
            current = self._state.current_track
            if current is not None and current.id == updated.id:
                old_duration = current.duration_ms
                duration = self._state.duration_ms
                if duration is None and updated.duration_ms is not None:
                    duration = updated.duration_ms
                self._state = replace(
                    self._state,
                    current_track=updated,
                    duration_ms=duration,
                    is_favorite=updated.is_favorite,
                )
                self.track_changed.emit(updated)
                if old_duration != updated.duration_ms and duration == updated.duration_ms:
                    self.duration_changed.emit(duration)
            return
        if updated.stable_identity in self._tracks_by_identity:
            current = self._state.current_track
            was_current = current is not None and current.stable_identity == updated.stable_identity
            old_duration = current.duration_ms if was_current else None
            self._tracks_by_identity[updated.stable_identity] = updated
            if was_current:
                duration = self._state.duration_ms
                if duration is None and updated.duration_ms is not None:
                    duration = updated.duration_ms
                self._set_state(
                    current_track=updated,
                    is_favorite=updated.is_favorite,
                    duration_ms=duration,
                )
                self.track_changed.emit(updated)
                if old_duration != updated.duration_ms and duration == updated.duration_ms:
                    self.duration_changed.emit(duration)
            self._sync_queue_from_controller()

    def play_track(self, track_id: str) -> None:
        if self._controller is None:
            self._play_mock_track(track_id)
            return
        track = next(
            (candidate for candidate in self.queue_tracks if candidate.id == track_id),
            None,
        )
        if track is None:
            rejected = self._requested_tracks_by_id.get(track_id)
            return
        self._controller.play_item(track.stable_identity)

    def play(self) -> None:
        if self._controller is not None:
            self._controller.play()
            return
        if self._state.current_track is None:
            first_available = next(
                (track for track in self._queue if self._is_queue_playable_track(track)), None
            )
            if first_available is not None:
                self._play_mock_track(first_available.id)
            return
        if self._state.is_playing:
            return
        self._state = replace(self._state, is_playing=True)
        self.playing_changed.emit(True)
        self._start_timer()

    def pause(self) -> None:
        if self._controller is not None:
            self._controller.pause()
            return
        if not self._state.is_playing:
            return
        self._state = replace(self._state, is_playing=False)
        self._timer.stop()
        self.playing_changed.emit(False)

    def toggle_playback(self) -> None:
        self.pause() if self._state.is_playing else self.play()

    def play_previous(self) -> None:
        if self._controller is not None:
            self._controller.play_previous()
            return
        self._play_mock_relative(-1)

    def play_next(self) -> None:
        if self._controller is not None:
            self._controller.play_next()
            return
        self._play_mock_relative(1)

    def seek(self, position_ms: int) -> None:
        if self._controller is not None:
            self._controller.seek(position_ms)
            return
        duration = self._state.duration_ms
        if self._state.current_track is None or duration is None:
            return
        position = max(0, min(int(position_ms), duration))
        if position == self._state.position_ms:
            return
        self._state = replace(self._state, position_ms=position)
        self.position_changed.emit(position)

    def set_volume(self, value: int) -> None:
        if self._controller is not None:
            self._controller.set_volume(value)
            return
        volume = max(0, min(100, int(value)))
        if volume == self._state.volume:
            return
        self._state = replace(self._state, volume=volume)
        self.volume_changed.emit(volume)

    def set_muted(self, value: bool) -> None:
        if self._controller is not None:
            self._controller.set_muted(value)
            return
        muted = bool(value)
        if muted == self._state.is_muted:
            return
        self._state = replace(self._state, is_muted=muted)
        self.muted_changed.emit(muted)

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
        if self._controller is not None:
            mode = "list_loop" if self._state.shuffle_enabled else "shuffle"
            self._controller.set_play_mode(mode)
            return
        self._state = replace(
            self._state, shuffle_enabled=not self._state.shuffle_enabled
        )
        self.shuffle_changed.emit(self._state.shuffle_enabled)

    def cycle_repeat_mode(self) -> None:
        sequence = (RepeatMode.ALL, RepeatMode.ONE, RepeatMode.OFF)
        current_index = sequence.index(self._state.repeat_mode)
        mode = sequence[(current_index + 1) % len(sequence)]
        if self._controller is not None:
            self._controller.set_play_mode(
                "single_loop" if mode is RepeatMode.ONE else "sequence" if mode is RepeatMode.OFF else "shuffle" if self._state.shuffle_enabled else "list_loop"
            )
            return
        self._state = replace(self._state, repeat_mode=mode)
        self.repeat_mode_changed.emit(mode)

    def clear(self) -> None:
        if self._controller is not None:
            self._controller.clear()
            return
        self._timer.stop()
        self._state = PlaybackState()
        self.track_changed.emit(None)
        self.playing_changed.emit(False)
        self.duration_changed.emit(None)
        self.position_changed.emit(0)
        self.volume_changed.emit(self._state.volume)
        self.muted_changed.emit(self._state.is_muted)
        self.favorite_changed.emit(False)
        self.shuffle_changed.emit(False)
        self.repeat_mode_changed.emit(self._state.repeat_mode)

    def advance_for_test(self, elapsed_ms: int) -> None:
        """Advance only the mock backend deterministically for UI tests."""
        if self._controller is None:
            self._advance_mock_position(max(0, int(elapsed_ms)))

    def _connect_controller(self, controller: ProductionPlaybackController) -> None:
        controller.track_changed.connect(self._on_controller_track_changed)
        controller.playing_changed.connect(self._on_controller_playing_changed)
        controller.position_changed.connect(self._on_controller_position_changed)
        controller.duration_changed.connect(self._on_controller_duration_changed)
        controller.volume_changed.connect(self._on_controller_volume_changed)
        controller.muted_changed.connect(self._on_controller_muted_changed)
        controller.play_mode_changed.connect(self._on_controller_play_mode_changed)
        controller.queue_changed.connect(self._on_controller_queue_changed)
        controller.playback_status_changed.connect(self._on_controller_status_changed)
        controller.remote_track_state_changed.connect(self._on_controller_remote_track_state_changed)
        controller.error_occurred.connect(self.error_occurred)

    @staticmethod
    def _is_local_playable_track(track: Track) -> bool:
        return not track.is_missing and not track.is_online and bool(track.local_path)

    @staticmethod
    def _is_queue_playable_track(track: Track) -> bool:
        return PlaybackAdapter._is_local_playable_track(track) or track.is_online

    @staticmethod
    def _queue_item_from_track(track: Track) -> PlaybackQueueItem:
        if track.is_online:
            payload = dict(track.remote_payload) if isinstance(track.remote_payload, dict) else {}
            provider_raw = payload.get("raw")
            payload.update(
                {
                    "remoteStableId": track.stable_identity,
                    "sourceId": track.source_id,
                    "sourceName": track.source_name,
                    "id": track.remote_track_id or track.remote_identity or track.id,
                    "remote_stable_id": track.stable_identity,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "duration": (track.duration_ms or 0) / 1000,
                    "artwork": track.artwork_url or track.artwork_key,
                    "artworkUrl": track.artwork_url,
                    "artwork_url": track.artwork_url,
                    "availability": track.availability,
                    # Search results already carry the provider's raw item.
                    # Keep that nested mapping intact; replacing it with the
                    # whole normalized payload breaks source-specific fields
                    # such as NetEase quality variants during playback resolve.
                    "raw": (
                        dict(provider_raw)
                        if isinstance(provider_raw, dict)
                        else dict(track.remote_payload)
                        if isinstance(track.remote_payload, dict)
                        else {}
                    ),
                }
            )
            return PlaybackQueueItem(MediaItem.from_online(payload))
        return PlaybackQueueItem(
            MediaItem.from_local(
                {
                    "track_id": track.id,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "duration": (track.duration_ms or 0) / 1000,
                    "path": track.local_path,
                }
            )
        )

    def _set_mock_queue(self, tracks: Iterable[Track]) -> None:
        current_id = self._state.current_track.id if self._state.current_track else ""
        self._queue = list(tracks)
        self.queue_changed.emit(self.queue_tracks)
        if current_id and not any(track.id == current_id for track in self._queue):
            self.clear()
            return
        if current_id:
            current_index = next(
                index for index, track in enumerate(self._queue) if track.id == current_id
            )
            self._state = replace(self._state, current_index=current_index)

    def _play_mock_track(self, track_id: str) -> None:
        target_index = next(
            (
                index
                for index, track in enumerate(self._queue)
                if track.id == track_id and self._is_queue_playable_track(track)
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

    def _sync_queue_from_controller(self) -> None:
        self.queue_changed.emit(self.queue_tracks)

    def _sync_current_from_controller(self) -> None:
        controller = self._controller
        if controller is None:
            return
        item = controller.current_item
        track = self._tracks_by_identity.get(item.stable_identity) if item is not None else None
        if track is None:
            return
        self._set_state(
            current_track=track,
            current_index=controller.current_index,
            is_favorite=track.is_favorite,
        )

    def _set_state(self, **changes) -> None:
        self._state = replace(self._state, **changes)

    def _start_timer(self) -> None:
        if self._timer_enabled and not self._timer.isActive():
            self._timer.start()

    def _on_timer_timeout(self) -> None:
        self._advance_mock_position(self._timer.interval())

    def _advance_mock_position(self, elapsed_ms: int) -> None:
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
        self._handle_mock_track_end(duration)

    def _handle_mock_track_end(self, duration: int) -> None:
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
        self._play_mock_relative(1)

    def _play_mock_relative(self, offset: int) -> None:
        available = [
            track for track in self._queue
            if self._is_queue_playable_track(track)
        ]
        if not available:
            return
        if self._state.current_track is None:
            self._play_mock_track(available[0].id)
            return
        if self._state.shuffle_enabled and len(available) > 1:
            current = next(
                index
                for index, track in enumerate(available)
                if track.id == self._state.current_track.id
            )
            next_track = available[(current + (3 if offset > 0 else -3)) % len(available)]
            self._play_mock_track(next_track.id)
            return
        current = next(
            index
            for index, track in enumerate(available)
            if track.id == self._state.current_track.id
        )
        self._play_mock_track(available[(current + offset) % len(available)].id)

    def _on_controller_track_changed(self, item: PlaybackQueueItem | None) -> None:
        track = self._tracks_by_identity.get(item.stable_identity) if item is not None else None
        self._set_state(
            current_track=track,
            current_index=self._controller.current_index if self._controller is not None else -1,
            is_favorite=track.is_favorite if track is not None else False,
            position_ms=0,
            duration_ms=None,
        )
        self.track_changed.emit(track)
        self.favorite_changed.emit(self._state.is_favorite)

    def _on_controller_playing_changed(self, playing: bool) -> None:
        self._set_state(is_playing=bool(playing))
        self.playing_changed.emit(bool(playing))

    def _on_controller_position_changed(self, position: int) -> None:
        self._set_state(position_ms=max(0, int(position)))
        self.position_changed.emit(self._state.position_ms)

    def _on_controller_duration_changed(self, duration: int | None) -> None:
        value = int(duration) if duration is not None and int(duration) > 0 else None
        self._set_state(duration_ms=value)
        self.duration_changed.emit(value)

    def _on_controller_volume_changed(self, volume: int) -> None:
        self._set_state(volume=max(0, min(100, int(volume))))
        self.volume_changed.emit(self._state.volume)

    def _on_controller_muted_changed(self, muted: bool) -> None:
        self._set_state(is_muted=bool(muted))
        self.muted_changed.emit(self._state.is_muted)

    def _on_controller_play_mode_changed(self, mode: str) -> None:
        mapping = {
            "sequence": (False, RepeatMode.OFF),
            "list_loop": (False, RepeatMode.ALL),
            "single_loop": (False, RepeatMode.ONE),
            "shuffle": (True, RepeatMode.ALL),
        }
        shuffle, repeat = mapping.get(mode, mapping["list_loop"])
        changed_shuffle = shuffle != self._state.shuffle_enabled
        changed_repeat = repeat != self._state.repeat_mode
        self._set_state(shuffle_enabled=shuffle, repeat_mode=repeat)
        if changed_shuffle:
            self.shuffle_changed.emit(shuffle)
        if changed_repeat:
            self.repeat_mode_changed.emit(repeat)

    def _on_controller_queue_changed(self, _items) -> None:
        self._sync_queue_from_controller()

    def _on_controller_status_changed(self, status: str, detail: str) -> None:
        self._set_state(status=str(status or "idle"), status_detail=str(detail or ""))
        self.playback_status_changed.emit(self._state.status, self._state.status_detail)

    def _on_controller_remote_track_state_changed(
        self,
        identity: str,
        state: str,
        detail: str,
        payload: object,
    ) -> None:
        self.remote_track_state_changed.emit(
            str(identity or ""),
            str(state or "not_resolved"),
            str(detail or ""),
            payload if payload is not None else {},
        )
