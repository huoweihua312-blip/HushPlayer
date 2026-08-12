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
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.track_delegate import RowVisualState
from app.ui_v2.models.track_table_model import TrackColumn


class UiV2LibraryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.adapter = LibraryAdapter(create_mock_tracks(80))
        self.page = LibraryPage(self.adapter, get_theme("dark"))
        self.page.resize(900, 600)
        self.page.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()

    def _available_index(self):
        return next(
            self.page.track_table.model.index(row, 1)
            for row, track in enumerate(self.page.track_table.model.tracks())
            if not track.is_missing
        )

    def test_double_click_requests_play_and_right_click_menu_constructs(self) -> None:
        index = self._available_index()
        requested = []
        self.page.track_table.play_requested.connect(requested.append)
        self.page.track_table.doubleClicked.emit(index)
        self.app.processEvents()
        self.assertEqual(requested, [self.page.track_table.model.track_at(index.row()).id])
        menu = self.page.track_table.build_context_menu(index)
        self.assertEqual([action.text() for action in menu.actions()], ["播放", "添加到我喜欢", "添加到歌单", "查看歌曲信息"])
        menu.deleteLater()

    def test_missing_favorite_can_be_removed_but_not_added(self) -> None:
        model = self.page.track_table.model
        missing_favorite_row = next(
            row
            for row, track in enumerate(model.tracks())
            if track.is_missing and track.is_favorite
        )
        missing_row = next(
            row
            for row, track in enumerate(model.tracks())
            if track.is_missing and not track.is_favorite
        )

        menu = self.page.track_table.build_context_menu(
            model.index(missing_favorite_row, int(TrackColumn.MORE))
        )
        favorite_action = next(action for action in menu.actions() if action.text() == "取消收藏")
        self.assertTrue(favorite_action.isEnabled())
        self.assertFalse(next(action for action in menu.actions() if action.text() == "播放").isEnabled())
        favorite_action.trigger()
        self.app.processEvents()
        self.assertFalse(self.page.adapter.collection.track_for_id(model.track_at(missing_favorite_row).id).is_favorite)
        menu.deleteLater()

        menu = self.page.track_table.build_context_menu(
            model.index(missing_row, int(TrackColumn.MORE))
        )
        favorite_action = next(action for action in menu.actions() if action.text() == "添加到我喜欢")
        self.assertFalse(favorite_action.isEnabled())
        menu.deleteLater()

    def test_missing_track_exposes_online_recovery_action(self) -> None:
        model = self.page.track_table.model
        row = next(
            row
            for row, track in enumerate(model.tracks())
            if track.is_missing and not track.is_online
        )
        track = model.track_at(row)
        requested = []
        self.page.track_table.online_recovery_requested.connect(requested.append)
        menu = self.page.track_table.build_context_menu(
            model.index(row, int(TrackColumn.MORE))
        )
        recovery = next(action for action in menu.actions() if action.text() == "在线寻找并播放")
        self.assertTrue(recovery.isEnabled())
        recovery.trigger()
        self.assertEqual(requested, [track])
        menu.deleteLater()

    def test_empty_loading_error_and_content_states(self) -> None:
        self.adapter.clear()
        self.app.processEvents()
        self.assertEqual(self.page.current_view_state, "empty")
        self.page.set_view_state("loading")
        self.assertEqual(self.page.current_view_state, "loading")
        self.page.set_view_state("error", "模拟错误")
        self.assertEqual(self.page.current_view_state, "error")
        self.adapter.load_mock_tracks(20)
        self.app.processEvents()
        self.page.set_view_state("content")
        self.assertEqual(self.page.current_view_state, "content")

    def test_search_and_theme_toggle_keep_the_same_table_model(self) -> None:
        model = self.page.track_table.model
        self.page.search_box.set_text("Paper Moon")
        self.app.processEvents()
        self.assertGreater(self.page.track_table.model.rowCount(), 0)
        modes = []
        self.page.theme_changed.connect(modes.append)
        self.page.theme_toggle.click()
        self.assertEqual(modes, ["light"])
        self.page.set_theme(get_theme("light"))
        self.assertIs(self.page.track_table.model, model)

    def test_hover_is_resolved_once_for_the_whole_row(self) -> None:
        table = self.page.track_table
        row = self._available_index().row()
        track = table.model.track_at(row)
        table._set_hovered_row(row)
        self.app.processEvents()
        states = {
            table.delegate.row_visual_state(
                track,
                selected=False,
                hovered=table.is_row_hovered(row),
                playing=False,
            )
            for _column in range(table.model.columnCount())
        }
        self.assertEqual(states, {RowVisualState.HOVER})
        self.assertFalse(table.is_row_hovered(row + 1))
        self.assertEqual(
            table.delegate.background_color(RowVisualState.HOVER).name(),
            QColor(self.page.theme.colors.hover_background).name(),
        )
        image = table.viewport().grab().toImage()
        expected_color = QColor(self.page.theme.colors.hover_background).name()
        for column in range(table.model.columnCount()):
            if table.isColumnHidden(column):
                continue
            cell = table.visualRect(table.model.index(row, column))
            self.assertEqual(
                image.pixelColor(cell.left() + 3, cell.top() + 6).name(),
                expected_color,
            )

    def test_selected_playing_state_keeps_selection_and_playing_identity(self) -> None:
        table = self.page.track_table
        row = self._available_index().row()
        track = table.model.track_at(row)
        self.adapter.set_playing_track(track.id)
        table.selectRow(row)
        self.app.processEvents()
        self.assertEqual(
            table.delegate.row_visual_state(
                track,
                selected=True,
                hovered=True,
                playing=True,
            ),
            RowVisualState.SELECTED_PLAYING,
        )
        self.assertEqual(
            table.delegate.background_color(RowVisualState.SELECTED_PLAYING).name(),
            QColor(self.page.theme.colors.selected_background).name(),
        )


if __name__ == "__main__":
    unittest.main()
