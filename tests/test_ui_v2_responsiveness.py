"""User-facing checks for search, empty states, motion, and recent filtering."""

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.recent_adapter import RecentAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.empty_state import EmptyState
from app.ui_v2.widgets.search_box import SearchBox


class SearchResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.search = SearchBox()
        self.queries = []
        self.search.text_changed.connect(self.queries.append)

    def tearDown(self):
        self.search.deleteLater()
        self.app.processEvents()

    def test_typing_is_coalesced_but_enter_and_clear_are_immediate(self):
        QTest.keyClicks(self.search.line_edit, "Paper Moon")
        self.assertEqual(self.queries, [])
        QTest.qWait(220)
        self.assertEqual(self.queries, ["Paper Moon"])
        QTest.keyClicks(self.search.line_edit, " Live")
        QTest.keyClick(self.search.line_edit, Qt.Key.Key_Return)
        self.assertEqual(self.queries[-1], "Paper Moon Live")
        QTest.keyClicks(self.search.line_edit, " next")
        self.search.line_edit.clear()
        self.assertEqual(self.queries[-1], "")
        count = len(self.queries)
        QTest.qWait(220)
        self.assertEqual(len(self.queries), count)

    def test_programmatic_updates_and_route_sync_cancel_pending_typing(self):
        QTest.keyClicks(self.search.line_edit, "old")
        self.search.set_text("new")
        self.assertEqual(self.queries, ["new"])
        QTest.keyClicks(self.search.line_edit, " pending")
        self.search.input_controller.sync_text("another page")
        QTest.qWait(220)
        self.assertEqual(self.queries, ["new"])
        self.assertEqual(self.search.line_edit.text(), "another page")

    def test_chinese_composition_does_not_filter_until_committed(self):
        QCoreApplication.sendEvent(self.search.line_edit, QInputMethodEvent("中文", []))
        self.assertEqual(self.queries, [])
        commit = QInputMethodEvent()
        commit.setCommitString("中文")
        QCoreApplication.sendEvent(self.search.line_edit, commit)
        QTest.qWait(220)
        self.assertEqual(self.queries, ["中文"])

    def test_empty_state_restores_normal_action_and_updates_icon(self):
        state = EmptyState()
        try:
            for mode in ("dark", "light"):
                state.set_theme(get_theme(mode))
                state.set_state("empty", "收藏歌曲会显示在这里。")
                state.set_action("浏览音乐库")
                state.set_search_query("not found")
                self.assertEqual(state.title_label.text(), "未找到匹配歌曲")
                self.assertEqual(state.action_button.text(), "清空搜索")
                self.assertEqual(state.empty_icon_name, "search")
                search_icon = state.icon_label.pixmap().cacheKey()
                state.set_state("error")
                self.assertEqual(state.title_label.text(), "无法显示歌曲")
                self.assertNotEqual(state.icon_label.pixmap().cacheKey(), search_icon)
                state.set_search_query("")
                state.set_state("empty", "收藏歌曲会显示在这里。")
                self.assertEqual(state.detail_label.text(), "收藏歌曲会显示在这里。")
                self.assertEqual(state.action_button.text(), "浏览音乐库")
        finally:
            state.deleteLater()

    def test_recent_filter_reads_the_sorted_history_once(self):
        latest = datetime(2026, 9, 8)
        tracks = [replace(track, last_played_at=latest - timedelta(days=index % 10))
                  for index, track in enumerate(create_mock_tracks(2000))]
        collection = LibraryCollectionAdapter(tracks, read_only=True)
        recent = RecentAdapter(collection)
        with patch.object(collection, "recent_entries", wraps=collection.recent_entries) as reads:
            recent.set_range_days(3)
        self.assertEqual(reads.call_count, 1)
        self.assertEqual({track.id for track in recent.tracks()},
                         {track.id for track in tracks if track.last_played_at >= latest - timedelta(days=3)})
        recent.set_range_days(None)
        self.assertEqual(len(recent.tracks()), len(tracks))


class ShellResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {
            "HUSHPLAYER_APP_DATA_DIR": str(root / "appdata"),
            "HUSHPLAYER_CACHE_DIR": str(root / "cache"),
        })
        self.environment.start()
        self.window = MainWindow(data_mode="mock", settings_path=root / "settings.json")
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._finalize_close()
        self.window.deleteLater()
        self.app.processEvents()
        self.environment.stop()
        self.temp.cleanup()

    def test_no_results_clear_restores_library_and_does_not_open_settings(self):
        window = self.window
        window.navigation_adapter.set_route("library")
        window.title_bar.search_input.setText("__no_match_fixture__")
        self.assertEqual(window.library_page.empty_state.title_label.text(), "未找到匹配歌曲")
        window.library_page.empty_state.action_button.click()
        self.assertEqual(window.library_adapter.query, "")
        self.assertEqual(window.title_bar.search_input.text(), "")
        self.assertEqual(window.library_page.current_view_state, "content")
        self.assertIsNone(window.settings_overlay)

    def test_pending_query_does_not_leak_into_new_page(self):
        window = self.window
        window.navigation_adapter.set_route("library")
        window.title_bar.search_input.setText("Paper")
        QTest.keyClicks(window.title_bar.search_input, "pending")
        window.navigation_adapter.set_route("favorites")
        QTest.qWait(220)
        self.assertEqual(window.router.currentWidget().adapter.query, "")
        self.assertEqual(window.title_bar.search_input.text(), "")
        window.navigation_adapter.set_route("library")
        self.assertEqual(window.title_bar.search_input.text(), "Paper")
        self.assertEqual(window.library_adapter.query, "Paper")

    def test_motion_setting_previews_cancels_and_saves(self):
        window = self.window
        window.open_settings_overlay("appearance")
        overlay = window.settings_overlay
        control = overlay._controls["reduce_motion"]
        control.setChecked(True)
        self.assertTrue(window._reduce_motion)
        self.assertFalse(window.settings_bridge.read_snapshot().get("reduce_motion", False))
        window._animate_next_theme_change = True
        with patch.object(window, "_prepare_theme_reveal", side_effect=AssertionError("unexpected animation")):
            window.set_theme("light" if window.theme.mode == "dark" else "dark")
        self.assertIsNone(window._theme_reveal_overlay)
        overlay.cancel_and_close()
        self.assertFalse(window._reduce_motion)
        window.open_settings_overlay("appearance")
        control.setChecked(True)
        self.assertTrue(overlay.save())
        self.assertTrue(window.settings_bridge.read_snapshot().get("reduce_motion"))


if __name__ == "__main__":
    unittest.main()
