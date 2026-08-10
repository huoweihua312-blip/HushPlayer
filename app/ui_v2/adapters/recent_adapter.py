"""Recent-play view derived from shared mock playback records."""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import QObject, Qt

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.models.recent_play import RecentPlay
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn


class RecentAdapter(TrackListAdapter):
    """Presents one row per Track, ordered by the most recent mock play."""

    def __init__(self, collection: LibraryCollectionAdapter, parent: QObject | None = None) -> None:
        self._range_days: int | None = None
        super().__init__(
            collection,
            parent,
            predicate=self._is_recent_in_range,
            sort_column=TrackColumn.ADDED_AT,
            sort_order=Qt.SortOrder.DescendingOrder,
        )
        collection.recent_changed.connect(self._rebuild_visible_tracks)

    @property
    def range_days(self) -> int | None:
        return self._range_days

    def set_range_days(self, days: int | None) -> None:
        normalized = max(1, int(days)) if days else None
        if normalized == self._range_days:
            return
        self._range_days = normalized
        self._rebuild_visible_tracks()

    def clear(self) -> None:
        self.collection.clear_recent()

    def recent_for_track(self, track_id: str) -> RecentPlay | None:
        return self.collection.recent_for_track(track_id)

    def row_metadata(self, track: Track) -> str:
        """Expose only recorded recent metadata; never synthesize play counts."""

        entry = self.collection.recent_for_track(track.id)
        if entry is None:
            return ""
        timestamp = entry.last_played_at.strftime("%m-%d %H:%M")
        return f"{timestamp}  ·  播放 {entry.play_count} 次"

    def _is_recent_in_range(self, track: Track) -> bool:
        entry = self.collection.recent_for_track(track.id)
        if entry is None:
            return False
        if self._range_days is None:
            return True
        entries = self.collection.recent_entries()
        latest = entries[0].last_played_at if entries else entry.last_played_at
        return entry.last_played_at >= latest - timedelta(days=self._range_days)

    def _sort_value(self, track: Track, column: TrackColumn):
        if column == TrackColumn.ADDED_AT:
            entry = self.collection.recent_for_track(track.id)
            return entry.last_played_at if entry is not None else track.added_at
        return super()._sort_value(track, column)
