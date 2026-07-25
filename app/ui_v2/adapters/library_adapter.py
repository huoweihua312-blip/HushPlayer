"""Mock-backed library state for UI V2's first development phase."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from PySide6.QtCore import QObject, Qt, Signal

from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn


class LibraryAdapter(QObject):
    """Owns filtering, sorting, and lightweight UI-only track state."""

    tracks_reset = Signal(object)
    track_updated = Signal(object)
    playing_track_changed = Signal(str)
    play_requested = Signal(str)
    favorite_changed = Signal(str, bool)
    query_changed = Signal(str)
    sort_changed = Signal(int, object)

    def __init__(self, tracks: Iterable[Track] = (), parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all_tracks = list(tracks)
        self._visible_tracks: list[Track] = []
        self._query = ""
        self._sort_column = TrackColumn.ADDED_AT
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._playing_track_id = ""
        self._rebuild_visible_tracks(emit=False)

    def tracks(self) -> tuple[Track, ...]:
        return tuple(self._visible_tracks)

    def set_query(self, text: str) -> None:
        query = str(text or "").strip()
        if query == self._query:
            return
        self._query = query
        self._rebuild_visible_tracks()
        self.query_changed.emit(query)

    def set_sort(self, column: int | TrackColumn, order: Qt.SortOrder) -> None:
        try:
            sort_column = TrackColumn(column)
        except ValueError:
            return
        if self._sort_column == sort_column and self._sort_order == order:
            return
        self._sort_column = sort_column
        self._sort_order = order
        self._rebuild_visible_tracks()
        self.sort_changed.emit(int(sort_column), order)

    def set_playing_track(self, track_id: str) -> None:
        normalized_id = str(track_id or "")
        if normalized_id == self._playing_track_id:
            return
        self._playing_track_id = normalized_id
        self.playing_track_changed.emit(normalized_id)

    def request_play(self, track_id: str) -> None:
        track = self._track_by_id(track_id)
        if track is None or track.is_missing:
            return
        self.set_playing_track(track.id)
        self.play_requested.emit(track.id)

    def toggle_favorite(self, track_id: str) -> None:
        track = self.track_for_id(track_id)
        if track is not None:
            self.set_favorite(track_id, not track.is_favorite)

    def set_favorite(self, track_id: str, value: bool) -> None:
        for row, track in enumerate(self._all_tracks):
            if track.id != track_id:
                continue
            favorite = bool(value)
            if track.is_favorite == favorite:
                return
            updated = replace(track, is_favorite=favorite)
            self._all_tracks[row] = updated
            visible_row = next(
                (index for index, item in enumerate(self._visible_tracks) if item.id == track_id),
                None,
            )
            if visible_row is not None:
                self._visible_tracks[visible_row] = updated
                self.track_updated.emit(updated)
            self.favorite_changed.emit(updated.id, updated.is_favorite)
            return

    def all_tracks(self) -> tuple[Track, ...]:
        return tuple(self._all_tracks)

    def track_for_id(self, track_id: str) -> Track | None:
        return self._track_by_id(track_id)

    def set_tracks(self, tracks: Iterable[Track]) -> None:
        self._all_tracks = list(tracks)
        if self._playing_track_id and self._track_by_id(self._playing_track_id) is None:
            self._playing_track_id = ""
            self.playing_track_changed.emit("")
        self._rebuild_visible_tracks()

    def clear(self) -> None:
        self.set_tracks(())

    def load_mock_tracks(self, count: int) -> None:
        self.set_tracks(create_mock_tracks(count))

    @property
    def playing_track_id(self) -> str:
        return self._playing_track_id

    @property
    def query(self) -> str:
        return self._query

    @property
    def sort_column(self) -> TrackColumn:
        return self._sort_column

    @property
    def sort_order(self) -> Qt.SortOrder:
        return self._sort_order

    def _track_by_id(self, track_id: str) -> Track | None:
        return next((track for track in self._all_tracks if track.id == track_id), None)

    def _rebuild_visible_tracks(self, emit: bool = True) -> None:
        query = self._query.casefold()
        filtered = [
            track
            for track in self._all_tracks
            if not query
            or query in " ".join(
                (track.title, track.artist, track.album, track.source_name)
            ).casefold()
        ]
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        self._visible_tracks = sorted(
            filtered,
            key=lambda track: self._sort_value(track, self._sort_column),
            reverse=reverse,
        )
        if emit:
            self.tracks_reset.emit(tuple(self._visible_tracks))

    @staticmethod
    def _sort_value(track: Track, column: TrackColumn):
        if column == TrackColumn.FAVORITE:
            return track.is_favorite
        if column == TrackColumn.TITLE:
            return track.title.casefold()
        if column == TrackColumn.ARTIST:
            return track.artist.casefold()
        if column == TrackColumn.ALBUM:
            return track.album.casefold()
        if column == TrackColumn.DURATION:
            return (track.duration_ms is None, track.duration_ms or 0)
        if column == TrackColumn.SOURCE:
            return track.source_name.casefold()
        return track.added_at
