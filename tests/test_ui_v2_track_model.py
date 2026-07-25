from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track_table_model import TrackColumn, TrackTableModel


class UiV2TrackModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.adapter = LibraryAdapter(create_mock_tracks(1000))
        self.model = TrackTableModel(self.adapter.tracks())
        self.adapter.tracks_reset.connect(self.model.set_tracks)
        self.adapter.track_updated.connect(self.model.update_track)
        self.adapter.playing_track_changed.connect(self.model.set_playing_track)

    def _first_available_row(self) -> int:
        return next(row for row, track in enumerate(self.model.tracks()) if not track.is_missing)

    def test_model_has_1000_virtual_rows_and_complete_tooltips(self) -> None:
        self.assertEqual(self.model.rowCount(), 1000)
        self.assertEqual(self.model.columnCount(), 7)
        row = self._first_available_row()
        title_index = self.model.index(row, int(TrackColumn.TITLE))
        title_tooltip = title_index.data(Qt.ItemDataRole.ToolTipRole)
        self.assertIn(self.model.track_at(row).title, title_tooltip)
        self.assertIn("添加时间:", title_tooltip)
        self.assertEqual(self.model.index(row, int(TrackColumn.DURATION)).data(Qt.ItemDataRole.ToolTipRole), self.model.index(row, int(TrackColumn.DURATION)).data())

    def test_search_chinese_and_sort_keep_existing_track_objects(self) -> None:
        identities = {track.id: track for track in self.adapter.tracks()}
        self.adapter.set_query("夜航")
        self.assertGreater(self.model.rowCount(), 0)
        self.assertTrue(all("夜航" in track.title for track in self.model.tracks()))
        self.adapter.set_query("")
        self.adapter.set_sort(TrackColumn.TITLE, Qt.SortOrder.AscendingOrder)
        self.assertTrue(all(track is identities[track.id] for track in self.model.tracks()))
        self.adapter.set_sort(TrackColumn.DURATION, Qt.SortOrder.AscendingOrder)
        known_durations = [track.duration_ms for track in self.model.tracks() if track.duration_ms is not None]
        self.assertEqual(known_durations, sorted(known_durations))

    def test_favorite_and_playing_emit_only_affected_rows(self) -> None:
        changes = []
        self.model.dataChanged.connect(
            lambda top, bottom, roles: changes.append((top.row(), bottom.row(), roles))
        )
        first_row = self._first_available_row()
        first_track = self.model.track_at(first_row)
        self.adapter.toggle_favorite(first_track.id)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], first_row)
        self.assertEqual(changes[0][1], first_row)
        changes.clear()
        second_row = next(
            row for row, track in enumerate(self.model.tracks())
            if not track.is_missing and track.id != first_track.id
        )
        self.adapter.set_playing_track(first_track.id)
        changes.clear()
        self.adapter.set_playing_track(self.model.track_at(second_row).id)
        self.assertEqual({change[0] for change in changes}, {first_row, second_row})
        self.assertTrue(all(change[0] == change[1] for change in changes))

    def test_missing_and_online_statuses_are_exposed(self) -> None:
        missing_row = next(row for row, track in enumerate(self.model.tracks()) if track.is_missing)
        online_row = next(row for row, track in enumerate(self.model.tracks()) if track.is_online)
        self.assertFalse(bool(self.model.flags(self.model.index(missing_row, 0)) & Qt.ItemFlag.ItemIsEnabled))
        self.assertIn("在线", self.model.index(online_row, int(TrackColumn.SOURCE)).data(Qt.ItemDataRole.ToolTipRole))


if __name__ == "__main__":
    unittest.main()
