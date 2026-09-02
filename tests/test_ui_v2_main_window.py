from __future__ import annotations

import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QAbstractAnimation
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track import format_duration
from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.shell.content_router import ComingSoonPage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.widgets.custom_title_bar import _QUIET_ORBIT_LOGO, _QUIET_ORBIT_LOGO_LIGHT


class UiV2MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        settings_path = (
            Path(tempfile.gettempdir())
            / "HushPlayer-ui-v2-tests"
            / f"main-window-{os.getpid()}-{id(self)}.json"
        )
        self.window = MainWindow(settings_path=settings_path)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _available_index(self):
        model = self.window.library_page.track_table.model
        return next(
            model.index(row, int(TrackColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if not track.is_missing
        )

    def test_main_window_constructs_and_reuses_all_route_pages(self) -> None:
        library = self.window.library_page
        for item in self.window.navigation_adapter.items():
            if item.route_id == "settings":
                continue
            self.window.navigation_adapter.set_route(item.route_id)
            self.app.processEvents()
            first_page = self.window.router.currentWidget()
            self.window.navigation_adapter.set_route("library")
            self.window.navigation_adapter.set_route(item.route_id)
            self.assertIs(self.window.router.currentWidget(), first_page)
        self.window.navigation_adapter.set_route("library")
        self.assertIs(self.window.router.currentWidget(), library)
        self.assertEqual(
            self.window.router.cached_page_count,
            len(self.window.navigation_adapter.items()) - 1,
        )

    def test_browse_is_the_default_cached_page(self) -> None:
        self.assertEqual(self.window.navigation_adapter.route, "browse")
        self.assertIs(self.window.router.currentWidget(), self.window.router.browse_page)

    def test_library_page_state_survives_route_switching(self) -> None:
        page = self.window.library_page
        model = page.track_table.model
        self.window.navigation_adapter.set_route("library")
        self.app.processEvents()
        self.window.title_bar.search_input.setText("Paper Moon")
        self.app.processEvents()
        selected_row = next(
            row for row, track in enumerate(model.tracks()) if not track.is_missing
        )
        page.track_table.selectRow(selected_row)
        self.window.open_settings_overlay()
        self.window.navigation_adapter.set_route("library")
        self.app.processEvents()
        self.assertIs(page.track_table.model, model)
        self.assertEqual(page.adapter.query, "Paper Moon")
        self.assertTrue(page.track_table.selectionModel().hasSelection())

    def test_table_play_request_updates_player_bar_and_playing_row(self) -> None:
        index = self._available_index()
        table = self.window.library_page.track_table
        track = table.model.track_at(index.row())
        table.doubleClicked.emit(index)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, track.id)
        self.assertEqual(self.window.library_adapter.playing_track_id, track.id)
        self.assertEqual(self.window.player_bar.title_label.full_text, track.title)
        self.window.playback_adapter.advance_for_test(1_000)
        self.assertEqual(
            self.window.player_bar.progress_slider.value(),
            self.window.playback_adapter.state.position_ms,
        )
        self.assertEqual(
            self.window.player_bar.current_time_label.text(),
            format_duration(self.window.playback_adapter.state.position_ms),
        )

    def test_favorite_syncs_between_player_and_library(self) -> None:
        index = self._available_index()
        table = self.window.library_page.track_table
        table.doubleClicked.emit(index)
        self.app.processEvents()
        track_id = self.window.playback_adapter.state.current_track.id
        original = self.window.library_adapter.track_for_id(track_id).is_favorite
        self.window.player_bar.favorite_button.click()
        self.app.processEvents()
        self.assertEqual(
            self.window.library_adapter.track_for_id(track_id).is_favorite,
            self.window.playback_adapter.state.is_favorite,
        )
        self.assertNotEqual(self.window.playback_adapter.state.is_favorite, original)
        self.window.library_adapter.set_favorite(track_id, original)
        self.assertEqual(self.window.playback_adapter.state.is_favorite, original)

    def test_confirmed_library_failure_starts_one_automatic_recovery(self) -> None:
        source = next(
            track for track in self.window.library_collection.tracks() if track.is_online
        )
        failed = replace(source, availability="playback_error", is_missing=True)
        self.window.library_collection.update_runtime_track(failed)
        self.window.playback_adapter.set_queue((failed,))
        self.window.playback_adapter.play_track(failed.id)
        self.app.processEvents()

        original_online_adapter = self.window.online_adapter
        try:
            apply_remote_state = Mock(return_value=failed)
            self.window.online_adapter = SimpleNamespace(
                is_formal=True,
                apply_remote_state=apply_remote_state,
            )
            request_recovery = Mock()
            self.window._request_online_recovery = request_recovery

            self.window._on_remote_track_state_changed(
                failed.stable_identity,
                "playback_error",
                "媒体无效",
                {},
            )
            self.window._on_remote_track_state_changed(
                failed.stable_identity,
                "playback_error",
                "媒体无效",
                {},
            )

            self.assertEqual(apply_remote_state.call_count, 2)
            request_recovery.assert_called_once_with(failed)
        finally:
            self.window.online_adapter = original_online_adapter

    def test_unresolved_library_track_does_not_start_automatic_recovery(self) -> None:
        source = next(
            track for track in self.window.library_collection.tracks() if track.is_online
        )
        current = replace(source, availability="not_resolved", is_missing=False)
        self.window.library_collection.update_runtime_track(current)
        self.window.playback_adapter.set_queue((current,))
        self.window.playback_adapter.play_track(current.id)
        self.app.processEvents()

        original_online_adapter = self.window.online_adapter
        try:
            self.window.online_adapter = SimpleNamespace(
                is_formal=True,
                apply_remote_state=Mock(return_value=current),
            )
            request_recovery = Mock()
            self.window._request_online_recovery = request_recovery
            self.window._on_remote_track_state_changed(
                current.stable_identity,
                "not_resolved",
                "",
                {},
            )
            request_recovery.assert_not_called()
        finally:
            self.window.online_adapter = original_online_adapter

    def test_responsive_modes_keep_navigation_and_model_instances(self) -> None:
        self.window.navigation_adapter.set_route("library")
        self.app.processEvents()
        table = self.window.library_page.track_table
        model = table.model
        navigation_item_count = self.window.sidebar.item_count
        expected = {
            900: (True, "narrow"),
            1100: (False, "standard"),
            1400: (False, "wide"),
            1600: (False, "wide"),
        }
        for width, (compact, profile) in expected.items():
            self.window.resize(width, 600 if width == 900 else 700)
            self.app.processEvents()
            self.assertEqual(self.window.sidebar.compact, compact)
            self.assertEqual(self.window.player_bar.compact, compact)
            self.assertEqual(table.column_profile, profile)
            self.assertIs(table.model, model)
            self.assertEqual(self.window.sidebar.item_count, navigation_item_count)
            self.assertFalse(table.horizontalScrollBar().isVisible())
            self.assertLessEqual(table.horizontalHeader().length(), table.viewport().width())
            self.assertEqual(self.window.player_bar.height(), 102)

    def test_sidebar_surfaces_follow_dark_and_light_theme_tokens(self) -> None:
        sidebar = self.window.sidebar
        surfaces = (
            sidebar,
            sidebar.scroll_area,
            sidebar.scroll_area.viewport(),
            sidebar.content,
            sidebar.playlist_container,
        )
        light_navigation = "#e4e4e2"
        for mode in ("dark", "light"):
            self.window.set_theme(mode)
            expected = self.window.theme.colors.navigation_background
            expected_color = QColor(expected).name().lower()
            for surface in surfaces:
                self.assertEqual(
                    surface.palette().color(QPalette.ColorRole.Window).name().lower(),
                    expected_color,
                )
                self.assertEqual(
                    surface.palette().color(QPalette.ColorRole.Base).name().lower(),
                    expected_color,
                )
            self.assertIn(expected, sidebar.styleSheet())
            if mode == "dark":
                self.assertNotIn(light_navigation, sidebar.styleSheet())

    def test_top_bar_exposes_one_settings_entry_and_persists_theme_without_rebuilding_shell(self) -> None:
        title_bar = self.window.title_bar
        sidebar = self.window.sidebar
        player_bar = self.window.player_bar
        playback_adapter = self.window.playback_adapter
        route = "library"
        self.window.navigation_adapter.set_route(route)
        self.app.processEvents()

        self.assertEqual(title_bar.settings_button.accessibleName(), "设置")
        self.assertEqual(title_bar.theme_button.accessibleName(), "主题切换")
        self.assertEqual(title_bar.view_options_button.accessibleName(), "视图选项")
        self.assertFalse(title_bar.view_options_button.isEnabled())
        self.assertFalse(sidebar.settings_box.isVisible())
        self.assertEqual(self.window.settings_shortcut.key().toString(), "Ctrl+,")

        self.window.settings_shortcut.activated.emit()
        self.app.processEvents()
        self.assertTrue(self.window.settings_overlay.isVisible())
        self.window.settings_overlay.cancel_and_close()

        self.window.toggle_theme()
        QTest.qWait(self.window._THEME_REVEAL_APPLY_DELAY_MS + 40)
        self.app.processEvents()
        self.assertEqual(self.window.theme.mode, "light")
        self.assertIs(self.window.player_bar, player_bar)
        self.assertIs(self.window.playback_adapter, playback_adapter)
        self.assertEqual(self.window.navigation_adapter.route, route)
        self.assertEqual(
            self.window.settings_bridge.value(self.window._settings_snapshot, "appearance_mode"),
            "light",
        )

    def test_theme_transition_keeps_shell_updates_and_uses_light_logo(self) -> None:
        title_bar = self.window.title_bar
        library_page = self.window.library_page
        player_bar = self.window.player_bar

        self.window.set_theme("dark")
        self.assertFalse(title_bar.brand_mark.pixmap().isNull())
        self.assertEqual(Path(title_bar.brand_mark.property("hushLogoAsset")), _QUIET_ORBIT_LOGO)
        self.window.set_theme("light")
        self.app.processEvents()

        self.assertTrue(self.window.updatesEnabled())
        self.assertTrue(self.window.root.updatesEnabled())
        self.assertIs(self.window.library_page, library_page)
        self.assertIs(self.window.player_bar, player_bar)
        self.assertEqual(Path(title_bar.brand_mark.property("hushLogoAsset")), _QUIET_ORBIT_LOGO_LIGHT)
        self.assertTrue(_QUIET_ORBIT_LOGO_LIGHT.is_file())

    def test_mouse_focus_is_hidden_but_keyboard_focus_can_be_marked(self) -> None:
        button = self.window.title_bar.theme_button

        self.window._set_button_keyboard_focus(button, False)
        self.assertEqual(button.property("hushKeyboardFocus"), "false")
        self.window._set_button_keyboard_focus(button, True)
        self.assertEqual(button.property("hushKeyboardFocus"), "true")

    def test_theme_reveal_is_enabled_and_cleans_up_after_animation(self) -> None:
        self.window._animate_next_theme_change = True
        target = "light" if self.window.theme.mode == "dark" else "dark"

        self.window.set_theme(target)
        self.app.processEvents()
        self.assertIsNotNone(self.window._theme_reveal_overlay)
        overlay = self.window._theme_reveal_overlay
        expected_origin = overlay.mapFromGlobal(
            self.window.title_bar.theme_button.mapToGlobal(
                self.window.title_bar.theme_button.rect().center()
            )
        )
        self.assertEqual(overlay._origin, expected_origin)
        QTest.qWait(overlay._DURATION_MS + 80)
        self.app.processEvents()
        self.assertIsNone(self.window._theme_reveal_overlay)

    def test_theme_reveal_starts_before_theme_persistence(self) -> None:
        original_mode = self.window.theme.mode

        self.window.toggle_theme()
        overlay = self.window._theme_reveal_overlay
        self.assertIsNotNone(overlay)
        self.assertEqual(self.window.theme.mode, original_mode)
        self.assertEqual(overlay._radius, 0.0)
        self.assertEqual(overlay._animation.state(), QAbstractAnimation.State.Running)

        QTest.qWait(self.window._THEME_REVEAL_APPLY_DELAY_MS + 20)
        self.app.processEvents()
        self.assertNotEqual(self.window.theme.mode, original_mode)
        QTest.qWait(40)
        self.app.processEvents()
        self.assertGreater(overlay._radius, 0.0)

        QTest.qWait(overlay._DURATION_MS + 80)
        self.app.processEvents()
        self.assertIsNone(self.window._theme_reveal_overlay)

    def test_all_navigation_entries_are_clickable_and_route_to_cached_pages(self) -> None:
        sidebar = self.window.sidebar
        long_playlist_name = "一个用于验证提示文本的超长自定义歌单名称"
        long_playlist_id = sidebar.create_mock_playlist(long_playlist_name)
        self.app.processEvents()
        for route_id, item in sidebar._items.items():
            self.assertTrue(item.isEnabled(), route_id)
            before_route = self.window.navigation_adapter.route
            item.click()
            self.app.processEvents()
            if route_id == "settings":
                self.assertEqual(self.window.navigation_adapter.route, before_route)
                self.assertTrue(self.window.settings_overlay.isVisible())
                self.window.settings_overlay.cancel_and_close()
                self.app.processEvents()
                continue
            self.assertEqual(self.window.navigation_adapter.route, route_id)
            if route_id == "browse":
                self.assertIs(self.window.router.currentWidget(), self.window.router.browse_page)
            elif route_id == "library":
                self.assertIs(self.window.router.currentWidget(), self.window.library_page)
            elif route_id in {"liked", "online_search"}:
                self.assertNotIsInstance(self.window.router.currentWidget(), ComingSoonPage)
            else:
                self.assertIsInstance(self.window.router.currentWidget(), ComingSoonPage)

        for playlist_id, item in sidebar._playlist_items.items():
            self.assertTrue(item.isEnabled(), playlist_id)
            if playlist_id == long_playlist_id:
                self.assertEqual(item.toolTip(), long_playlist_name)
            item.click()
            self.app.processEvents()
            self.assertEqual(
                self.window.navigation_adapter.route, f"playlist:{playlist_id}"
            )
            self.assertNotIsInstance(self.window.router.currentWidget(), ComingSoonPage)

    def test_player_bar_empty_state_recovers_without_recreation(self) -> None:
        player_bar = self.window.player_bar
        self.window.playback_adapter.clear()
        self.app.processEvents()
        for button in (
            player_bar.favorite_button,
            player_bar.shuffle_button,
            player_bar.previous_button,
            player_bar.play_button,
            player_bar.next_button,
            player_bar.repeat_button,
            player_bar.lyrics_button,
            player_bar.queue_button,
            player_bar.more_button,
        ):
            self.assertFalse(button.isEnabled(), button.toolTip())
        self.assertFalse(player_bar.progress_slider.isEnabled())
        self.assertTrue(player_bar.volume_button.isEnabled())
        self.assertTrue(player_bar.volume_slider.isEnabled())

        self.window.library_page.track_table.doubleClicked.emit(self._available_index())
        self.app.processEvents()
        self.assertIs(self.window.player_bar, player_bar)
        for button in (
            player_bar.favorite_button,
            player_bar.shuffle_button,
            player_bar.previous_button,
            player_bar.play_button,
            player_bar.next_button,
            player_bar.repeat_button,
            player_bar.lyrics_button,
            player_bar.queue_button,
            player_bar.more_button,
        ):
            self.assertTrue(button.isEnabled(), button.toolTip())
        self.assertTrue(player_bar.progress_slider.isEnabled())

        self.window.playback_adapter.clear()
        self.app.processEvents()
        self.assertIs(self.window.player_bar, player_bar)
        self.assertFalse(player_bar.play_button.isEnabled())
        self.assertFalse(player_bar.progress_slider.isEnabled())
        self.assertTrue(player_bar.volume_slider.isEnabled())

    def test_light_dark_theme_preserves_library_model(self) -> None:
        model = self.window.library_page.track_table.model
        self.window.set_theme("light")
        self.assertEqual(self.window.theme.mode, "light")
        self.window.set_theme("dark")
        self.assertEqual(self.window.theme.mode, "dark")
        self.assertIs(self.window.library_page.track_table.model, model)


if __name__ == "__main__":
    unittest.main()
