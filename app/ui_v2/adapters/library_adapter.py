"""All-songs view adapter backed by the shared UI V2 mock collection."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QObject, Qt

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn


class LibraryAdapter(TrackListAdapter):
    """The all-songs view; it owns a collection only when used standalone in tests."""

    def __init__(
        self,
        tracks: Iterable[Track] = (),
        parent: QObject | None = None,
        *,
        collection: LibraryCollectionAdapter | None = None,
    ) -> None:
        self._owned_collection = collection is None
        shared = collection or LibraryCollectionAdapter(tracks, parent)
        super().__init__(
            shared,
            parent,
            sort_column=TrackColumn.ADDED_AT,
            sort_order=Qt.SortOrder.DescendingOrder,
        )

    def set_playing_track(self, track_id: str) -> None:
        self.collection.set_playing_track(track_id)

    def set_tracks(self, tracks: Iterable[Track]) -> None:
        self.collection.set_tracks(tracks)

    def clear(self) -> None:
        self.collection.set_tracks(())

    def load_mock_tracks(self, count: int) -> None:
        self.collection.set_tracks(create_mock_tracks(count))
