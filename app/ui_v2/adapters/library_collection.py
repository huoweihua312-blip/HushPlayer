"""Shared mock music collection used by all third-stage UI V2 pages."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Iterable

from PySide6.QtCore import QObject, Signal

from app.ui_v2.models.recent_play import RecentPlay
from app.ui_v2.models.track import Track


class LibraryCollectionAdapter(QObject):
    """Owns shared Track references and UI-only metadata without persistence."""

    tracks_changed = Signal()
    track_updated = Signal(object)
    favorite_changed = Signal(str, bool)
    playing_track_changed = Signal(str)
    recent_changed = Signal()

    def __init__(self, tracks: Iterable[Track] = (), parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._track_by_id: dict[str, Track] = {}
        self._favorite_at: dict[str, datetime] = {}
        self._recent: dict[str, RecentPlay] = {}
        self._playing_track_id = ""
        self._clock = datetime(2026, 1, 1, 12, 0)
        self.set_tracks(tracks, emit=False)

    def tracks(self) -> tuple[Track, ...]:
        return tuple(self._tracks)

    def track_ids(self) -> frozenset[str]:
        return frozenset(self._track_by_id)

    def track_for_id(self, track_id: str) -> Track | None:
        return self._track_by_id.get(str(track_id or ""))

    def tracks_for_ids(self, track_ids: Iterable[str]) -> tuple[Track, ...]:
        return tuple(
            track
            for track_id in track_ids
            if (track := self._track_by_id.get(track_id)) is not None
        )

    def set_tracks(self, tracks: Iterable[Track], *, emit: bool = True) -> None:
        self._tracks = list(tracks)
        self._track_by_id = {track.id: track for track in self._tracks}
        self._favorite_at = {
            track.id: track.added_at + timedelta(days=1)
            for track in self._tracks
            if track.is_favorite
        }
        self._recent = {
            track_id: entry
            for track_id, entry in self._recent.items()
            if track_id in self._track_by_id
        }
        if self._playing_track_id not in self._track_by_id:
            self._playing_track_id = ""
        self._clock = max(
            (track.added_at for track in self._tracks),
            default=datetime(2026, 1, 1, 12, 0),
        ) + timedelta(days=2)
        if emit:
            self.tracks_changed.emit()

    def set_favorite(self, track_id: str, value: bool) -> None:
        track = self.track_for_id(track_id)
        if track is None or track.is_favorite == bool(value):
            return
        updated = replace(track, is_favorite=bool(value))
        index = next(index for index, item in enumerate(self._tracks) if item.id == track.id)
        self._tracks[index] = updated
        self._track_by_id[updated.id] = updated
        if updated.is_favorite:
            self._favorite_at[updated.id] = self._next_timestamp()
        else:
            self._favorite_at.pop(updated.id, None)
        self.track_updated.emit(updated)
        self.favorite_changed.emit(updated.id, updated.is_favorite)

    def upsert_track(self, track: Track) -> Track:
        """Add or replace one UI-only Track without rebuilding the shared collection."""
        existing = self._track_by_id.get(track.id)
        if existing is None:
            self._tracks.append(track)
            self._track_by_id[track.id] = track
            if track.is_favorite:
                self._favorite_at[track.id] = self._next_timestamp()
            self.tracks_changed.emit()
            return track
        if existing == track:
            return existing
        index = next(index for index, item in enumerate(self._tracks) if item.id == track.id)
        self._tracks[index] = track
        self._track_by_id[track.id] = track
        self.track_updated.emit(track)
        return track

    def favorite_at(self, track_id: str) -> datetime | None:
        return self._favorite_at.get(track_id)

    def set_playing_track(self, track_id: str) -> None:
        normalized = str(track_id or "")
        if normalized == self._playing_track_id:
            return
        self._playing_track_id = normalized
        self.playing_track_changed.emit(normalized)

    @property
    def playing_track_id(self) -> str:
        return self._playing_track_id

    def record_play(self, track_id: str, position_ms: int = 0) -> None:
        if track_id not in self._track_by_id:
            return
        previous = self._recent.get(track_id)
        entry = RecentPlay(
            track_id=track_id,
            last_played_at=self._next_timestamp(),
            play_count=(previous.play_count if previous else 0) + 1,
            last_position_ms=max(0, int(position_ms)),
        )
        self._recent[track_id] = entry
        self.recent_changed.emit()

    def recent_entries(self) -> tuple[RecentPlay, ...]:
        return tuple(
            sorted(
                self._recent.values(), key=lambda entry: entry.last_played_at, reverse=True
            )
        )

    def recent_for_track(self, track_id: str) -> RecentPlay | None:
        return self._recent.get(track_id)

    def clear_recent(self) -> None:
        if not self._recent:
            return
        self._recent.clear()
        self.recent_changed.emit()

    def _next_timestamp(self) -> datetime:
        self._clock += timedelta(minutes=1)
        return self._clock
