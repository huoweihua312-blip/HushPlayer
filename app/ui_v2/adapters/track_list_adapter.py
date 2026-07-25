"""Filtered Track views backed by one shared LibraryCollectionAdapter."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, Qt, Signal

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn


TrackFilter = Callable[[Track], bool]


class TrackListAdapter(QObject):
    """Keeps a view-local query and sort state while sharing Track ownership."""

    tracks_reset = Signal(object)
    track_updated = Signal(object)
    playing_track_changed = Signal(str)
    play_requested = Signal(str)
    favorite_changed = Signal(str, bool)
    query_changed = Signal(str)
    sort_changed = Signal(int, object)

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        parent: QObject | None = None,
        *,
        predicate: TrackFilter | None = None,
        sort_column: TrackColumn = TrackColumn.ADDED_AT,
        sort_order: Qt.SortOrder = Qt.SortOrder.DescendingOrder,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self._predicate = predicate or (lambda track: True)
        self._visible_tracks: list[Track] = []
        self._query = ""
        self._sort_column = sort_column
        self._sort_order = sort_order
        collection.tracks_changed.connect(self._rebuild_visible_tracks)
        collection.track_updated.connect(self._on_track_updated)
        collection.playing_track_changed.connect(self.playing_track_changed)
        collection.favorite_changed.connect(self.favorite_changed)
        self._rebuild_visible_tracks(emit=False)

    def tracks(self) -> tuple[Track, ...]:
        return tuple(self._visible_tracks)

    def all_tracks(self) -> tuple[Track, ...]:
        return self.collection.tracks()

    def track_for_id(self, track_id: str) -> Track | None:
        return self.collection.track_for_id(track_id)

    @property
    def playing_track_id(self) -> str:
        return self.collection.playing_track_id

    @property
    def query(self) -> str:
        return self._query

    @property
    def sort_column(self) -> TrackColumn:
        return self._sort_column

    @property
    def sort_order(self) -> Qt.SortOrder:
        return self._sort_order

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

    def set_predicate(self, predicate: TrackFilter) -> None:
        self._predicate = predicate
        self._rebuild_visible_tracks()

    def request_play(self, track_id: str) -> None:
        track = self.collection.track_for_id(track_id)
        if track is None or track.is_missing:
            return
        self.collection.set_playing_track(track.id)
        self.play_requested.emit(track.id)

    def toggle_favorite(self, track_id: str) -> None:
        track = self.collection.track_for_id(track_id)
        if track is not None:
            self.collection.set_favorite(track_id, not track.is_favorite)

    def set_favorite(self, track_id: str, value: bool) -> None:
        self.collection.set_favorite(track_id, value)

    def _on_track_updated(self, track: Track) -> None:
        previous_row = next(
            (row for row, item in enumerate(self._visible_tracks) if item.id == track.id), -1
        )
        is_visible = self._matches(track)
        if (previous_row >= 0) != is_visible:
            self._rebuild_visible_tracks()
            return
        if previous_row >= 0:
            self._visible_tracks[previous_row] = track
            self.track_updated.emit(track)

    def _matches(self, track: Track) -> bool:
        if not self._predicate(track):
            return False
        query = self._query.casefold()
        return not query or query in " ".join(
            (track.title, track.artist, track.album, track.source_name)
        ).casefold()

    def _rebuild_visible_tracks(self, emit: bool = True) -> None:
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        self._visible_tracks = sorted(
            (track for track in self.collection.tracks() if self._matches(track)),
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
