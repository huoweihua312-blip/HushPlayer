from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.online_track_model import ONLINE_PLAYING_ROLE, OnlineColumn
from app.ui_v2.pages.online_search_page import OnlineSearchPage
from app.ui_v2.pages.online_source_page import OnlineSourcePage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.widgets.settings_control_factory import ToolbarComboBox


class OnlineAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = LibraryCollectionAdapter(create_mock_tracks(80))
        self.playlists = PlaylistAdapter(self.collection)
        self.adapter = OnlineAdapter(self.collection, self.playlists, timer_enabled=False)

    def _search(self, query: str = "夜航") -> None:
        self.adapter.set_query(query)
        self.assertTrue(self.adapter.search())
        self.adapter.complete_for_test()

    def test_success_empty_partial_and_total_failure_scenarios(self) -> None:
        self._search("中文 English")
        self.assertEqual(self.adapter.state.phase, "results")
        self.assertGreaterEqual(len(self.adapter.results()), 80)
        self.adapter.load_mock_scenario("empty")
        self._search("empty")
        self.assertEqual(self.adapter.state.phase, "empty")
        self.assertFalse(self.adapter.results())
        self.adapter.load_mock_scenario("partial_failure")
        self._search("partial")
        self.assertEqual(self.adapter.state.phase, "results")
        self.assertTrue(any(source.status == "failed" for source in self.adapter.sources()))
        self.adapter.load_mock_scenario("total_failure")
        self.adapter.set_query("failure")
        self.assertTrue(self.adapter.search())
        self.adapter.complete_for_test()
        self.assertEqual(self.adapter.state.phase, "failed")
        self.assertTrue(all(source.status in {"failed", "disabled"} for source in self.adapter.sources()))

    def test_empty_query_cancel_and_generation_guard(self) -> None:
        self.assertFalse(self.adapter.search())
        self.adapter.set_query("old")
        self.assertTrue(self.adapter.search())
        old_generation = self.adapter.state.generation
        self.adapter.set_query("new")
        self.assertTrue(self.adapter.search())
        self.adapter.complete_for_test(old_generation)
        self.assertEqual(self.adapter.state.phase, "searching")
        self.assertEqual(self.adapter.state.query, "new")
        self.adapter.cancel_search()
        self.adapter.advance_for_test()
        self.assertEqual(self.adapter.state.phase, "idle")
        self.assertFalse(self.adapter.results())

    def test_history_dedup_order_removal_and_clear(self) -> None:
        self._search("中文查询")
        self._search("English Query")
        self._search("中文查询")
        self.assertEqual([item.query for item in self.adapter.history()], ["中文查询", "English Query"])
        self.adapter.remove_history_item("English Query")
        self.assertEqual([item.query for item in self.adapter.history()], ["中文查询"])
        self.adapter.clear_history()
        self.assertFalse(self.adapter.history())

    def test_source_selection_status_and_result_identity_rules(self) -> None:
        self.adapter.set_enabled_sources(())
        self.adapter.set_query("none")
        self.assertFalse(self.adapter.search())
        self.assertEqual(self.adapter.state.phase, "failed")
        self.adapter.set_enabled_sources(source.id for source in self.adapter.sources())
        self.adapter.load_mock_scenario("duplicate_results")
        self._search("duplicates")
        identities = [track.stable_identity for track in self.adapter.results()]
        self.assertEqual(len(identities), len(set(identities)))
        by_title: dict[str, set[str]] = {}
        for track in self.adapter.results():
            by_title.setdefault(track.title, set()).add(track.source_id)
        self.assertTrue(any(len(sources) > 1 for sources in by_title.values()))
        source_id = self.adapter.sources()[0].id
        self.adapter.set_source_enabled(source_id, False)
        self.assertEqual(next(source for source in self.adapter.sources() if source.id == source_id).status, "disabled")
        self.assertTrue(
            all(
                track.availability == "source_unavailable"
                for track in self.adapter.results()
                if track.source_id == source_id
            )
        )

    def test_favorite_playlist_download_and_mock_play_requests(self) -> None:
        self._search()
        available = next(track for track in self.adapter.results() if track.availability == "not_resolved")
        self.adapter.toggle_favorite(available.id)
        self.assertTrue(next(track for track in self.adapter.results() if track.id == available.id).is_favorite)
        self.assertTrue(self.collection.track_for_id(available.id).is_favorite)
        playlist = self.playlists.create_playlist("在线歌曲")
        self.assertTrue(self.adapter.request_add_to_playlist(available.id, playlist.id))
        self.assertIn(available.id, self.playlists.playlist_for_id(playlist.id).track_ids)
        downloadable = next(
            track
            for track in self.adapter.results()
            if next(source for source in self.adapter.sources() if source.id == track.source_id).supports_download
        )
        self.assertTrue(self.adapter.request_download(downloadable.id))
        self.assertTrue(next(track for track in self.adapter.results() if track.id == downloadable.id).is_downloaded)
        unsupported = next(
            track
            for track in self.adapter.results()
            if not next(source for source in self.adapter.sources() if source.id == track.source_id).supports_download
        )
        self.assertFalse(self.adapter.request_download(unsupported.id))
        requested = []
        self.adapter.play_requested.connect(requested.append)
        self.assertTrue(self.adapter.request_play(available.id))
        self.assertEqual(requested[0].id, available.id)
        unavailable = next(
            track for track in self.adapter.results() if track.availability == "source_unavailable"
        )
        self.assertFalse(self.adapter.request_play(unavailable.id))


class OnlineSearchPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.window.online_adapter._timer_enabled = False

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _search_page(self) -> OnlineSearchPage:
        self.window.navigation_adapter.set_route("online_search")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, OnlineSearchPage)
        return page

    @staticmethod
    def _available_index(page: OnlineSearchPage):
        return next(
            page.result_table.model.index(row, int(OnlineColumn.TITLE))
            for row, track in enumerate(page.result_table.model.tracks())
            if track.availability == "not_resolved"
        )

    def _complete_search(self, page: OnlineSearchPage, query: str = "Paper Moon") -> None:
        page.search_bar.set_text(query)
        page.search_bar.search_requested.emit()
        self.window.online_adapter.complete_for_test()
        self.app.processEvents()

    def test_page_states_model_reuse_history_and_context_menu(self) -> None:
        page = self._search_page()
        model = page.result_table.model
        self._complete_search(page)
        self.assertTrue(page.result_table.isVisible())
        self.assertIs(page.result_table.model, model)
        self.window.navigation_adapter.set_route("library")
        self._search_page()
        self.assertEqual(page.search_bar.line_edit.text(), "Paper Moon")
        self.assertIs(page.result_table.model, model)
        archive_index = next(
            model.index(row, int(OnlineColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if track.source_id == "archive"
        )
        menu = page.result_table.build_context_menu(archive_index)
        self.assertFalse(next(action for action in menu.actions() if action.text() == "下载").isEnabled())
        menu.deleteLater()
        unavailable_index = next(
            model.index(row, int(OnlineColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if track.availability == "source_unavailable"
        )
        menu = page.result_table.build_context_menu(unavailable_index)
        self.assertFalse(next(action for action in menu.actions() if action.text() == "播放").isEnabled())
        menu.deleteLater()

    def test_result_filter_sort_and_source_selector_status(self) -> None:
        page = self._search_page()
        model = page.result_table.model
        self._complete_search(page, "筛选排序")
        source_index = page.result_toolbar.source_filter.findData("archive")
        page.result_toolbar.source_filter.setCurrentIndex(source_index)
        self.assertIs(page.result_table.model, model)
        self.assertTrue(all(track.source_id == "archive" for track in model.tracks()))
        page.result_toolbar.sort_selector.setCurrentIndex(
            page.result_toolbar.sort_selector.findData("title")
        )
        self.assertEqual(
            [track.title.casefold() for track in model.tracks()],
            sorted(track.title.casefold() for track in model.tracks()),
        )
        source_action = next(
            action
            for action in page.source_selector._menu.actions()
            if action.text().startswith("North Catalog")
        )
        self.assertIn("已完成", source_action.text())
        self.assertIn("16 条", source_action.text())
        self.window.online_adapter.load_mock_scenario("slow")
        page.search_bar.set_text("搜索中")
        page.search_bar.search_requested.emit()
        self.app.processEvents()
        self.assertFalse(page.source_selector._menu.actions()[0].isEnabled())

    def test_toolbar_selects_reuse_themed_combo_popup_and_keyboard_contract(self) -> None:
        page = self._search_page()
        self._complete_search(page, "工具栏")
        controls = (page.result_toolbar.source_filter, page.result_toolbar.sort_selector)
        self.assertTrue(all(isinstance(control, ToolbarComboBox) for control in controls))
        self.assertEqual(controls[0].accessibleName(), "来源筛选")
        self.assertEqual(controls[1].accessibleName(), "排序方式")
        self.assertTrue(all(control.native_arrow_suppressed for control in controls))
        self.assertTrue(all(control.height() == self.window.theme.metrics.control_height for control in controls))

        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            theme = self.window.theme
            for control in controls:
                palette = control.view().palette()
                self.assertEqual(
                    palette.color(QPalette.ColorRole.Base),
                    QColor(theme.colors.surface_elevated),
                )
                self.assertEqual(
                    palette.color(QPalette.ColorRole.Highlight),
                    QColor(theme.colors.selected_background),
                )
                self.assertIn("down-arrow", control.styleSheet())
                self.assertIn("image: none", control.styleSheet())

        sort = page.result_toolbar.sort_selector
        sort.setCurrentIndex(0)
        sort.setFocus()
        self.app.processEvents()
        self.assertTrue(sort.property("focusVisible"))
        QTest.keyClick(sort, Qt.Key.Key_Space)
        self.app.processEvents()
        self.assertTrue(sort.popup_open)
        self.assertTrue(sort.property("popupOpen"))
        QTest.keyClick(sort, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(sort.popup_open)
        QTest.keyClick(sort, Qt.Key.Key_Down)
        self.assertEqual(sort.currentData(), "title")
        QTest.keyClick(sort, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertTrue(sort.popup_open)
        sort.hidePopup()

        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertTrue(page.result_toolbar.source_filter.isVisible())
        self.assertTrue(page.result_toolbar.sort_selector.isVisible())
        self.assertEqual(page.result_toolbar.source_filter.width(), 128)
        self.assertEqual(page.result_toolbar.sort_selector.width(), 104)
        self.assertFalse(page.result_table.horizontalScrollBar().isVisible())

    def test_recommended_query_and_return_to_history(self) -> None:
        page = self._search_page()
        self.assertFalse(hasattr(page, "recommendation_buttons"))
        self.assertFalse(hasattr(page, "manage_sources_button"))
        page.search_bar.set_text("夜航")
        page.search_bar.search_requested.emit()
        self.assertEqual(page.search_bar.line_edit.text(), "夜航")
        self.window.online_adapter.complete_for_test()
        self.window.online_adapter.load_mock_scenario("empty")
        self._complete_search(page, "没有结果")
        self.assertTrue(page.state_view.history_button.isVisible())
        page.state_view.history_button.click()
        self.assertTrue(page.history_view.isVisible())

    def test_online_play_favorite_playlist_and_playing_highlight_sync(self) -> None:
        page = self._search_page()
        self._complete_search(page, "夜航")
        index = self._available_index(page)
        track = page.result_table.model.track_at(index.row())
        page.result_table.doubleClicked.emit(index)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, track.id)
        self.assertTrue(page.result_table.model.data(page.result_table.model.index(index.row(), 0), ONLINE_PLAYING_ROLE))
        self.window.online_adapter.toggle_favorite(track.id)
        self.app.processEvents()
        self.assertTrue(self.window.library_collection.track_for_id(track.id).is_favorite)
        self.window.navigation_adapter.set_route("liked")
        self.app.processEvents()
        self.assertIn(track.id, [item.id for item in self.window.router.currentWidget().adapter.tracks()])
        playlist = self.window.playlist_adapter.create_playlist("在线同步")
        self.assertTrue(self.window.online_adapter.request_add_to_playlist(track.id, playlist.id))
        self.window.navigation_adapter.set_route(f"playlist:{playlist.id}")
        self.app.processEvents()
        self.assertIn(track.id, [item.id for item in self.window.router.currentWidget().adapter.tracks()])

    def test_source_page_and_responsive_theme_geometry(self) -> None:
        page = self._search_page()
        self._complete_search(page, "长文本")
        page.source_management_requested.emit()
        self.app.processEvents()
        self.assertIsInstance(self.window.router.currentWidget(), OnlineSourcePage)
        source_page = self.window.router.currentWidget()
        first_row = next(iter(source_page._rows.values()))
        original = first_row._enabled
        first_row.toggle_requested.emit(first_row.source_id, not original)
        self.app.processEvents()
        self.assertEqual(first_row._enabled, not original)
        source_page.back_button.click()
        self.app.processEvents()
        self.assertIs(self.window.router.currentWidget(), page)
        result_model = page.result_table.model
        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            self.assertEqual(self.window.theme.mode, mode)
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertIs(page.result_table.model, result_model)
            self.assertFalse(page.result_table.horizontalScrollBar().isVisible())
            self.assertEqual(page.search_bar.line_edit.text(), "长文本")
        legacy_main = importlib.import_module("main")
        legacy_window = importlib.import_module("app.ui.main_window")
        self.assertTrue(callable(legacy_main.main))
        self.assertTrue(hasattr(legacy_window, "MainWindow"))


if __name__ == "__main__":
    unittest.main()
