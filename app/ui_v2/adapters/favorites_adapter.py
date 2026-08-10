"""Favorite-track view with its own latest-favorite ordering."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Qt

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn


class FavoritesAdapter(TrackListAdapter):
    """Shows favorites without owning or copying the underlying Track values."""

    def __init__(self, collection: LibraryCollectionAdapter, parent: QObject | None = None) -> None:
        super().__init__(
            collection,
            parent,
            predicate=lambda track: track.is_favorite,
            sort_column=TrackColumn.ADDED_AT,
            sort_order=Qt.SortOrder.DescendingOrder,
        )

    def _sort_value(self, track: Track, column: TrackColumn):
        if column == TrackColumn.ADDED_AT:
            return self.collection.favorite_at(track.id) or datetime.min
        return super()._sort_value(track, column)
