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
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.settings_adapter import SettingsAdapter
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage
from app.ui_v2.pages.settings_page import SettingsPage
from app.ui_v2.shell.main_window import MainWindow


class SettingsStateAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lyrics = LyricsAdapter()
        self.options = ImmersiveLyricsOptions()
        self.adapter = SettingsAdapter(self.lyrics, self.options)

    def test_defaults_draft_dirty_save_cancel_and_validation(self) -> None:
        persisted = self.adapter.state()
        self.assertFalse(self.adapter.is_dirty())
        self.adapter.set_value("general.restore_last_session", False)
        self.assertTrue(self.adapter.is_dirty())
        self.assertIn("general.restore_last_session", self.adapter.dirty_fields())
        self.assertTrue(persisted.general.restore_last_session)
        self.adapter.cancel()
        self.assertFalse(self.adapter.is_dirty())
        self.assertTrue(self.adapter.get_value("general.restore_last_session"))
        self.adapter.set_value("playback.crossfade_enabled", True)
        self.adapter.set_value("playback.crossfade_seconds", 18)
        valid, errors = self.adapter.validate()
        self.assertFalse(valid)
        self.assertIn("playback.crossfade_seconds", errors)
        self.assertFalse(self.adapter.save())
        self.adapter.set_value("playback.crossfade_seconds", 5)
        self.assertTrue(self.adapter.save())
        self.assertFalse(self.adapter.is_dirty())
        self.assertEqual(self.adapter.state().playback.crossfade_seconds, 5)

    def test_category_and_all_defaults_do_not_persist_until_save(self) -> None:
        self.adapter.set_value("appearance.theme_mode", "light")
        self.adapter.set_value("playback.default_volume", 42)
        self.assertTrue(self.adapter.save())
        self.adapter.restore_category_defaults("appearance")
        self.assertEqual(self.adapter.get_value("appearance.theme_mode"), "dark")
        self.assertEqual(self.adapter.get_value("playback.default_volume"), 42)
        self.assertTrue(self.adapter.is_dirty())
        self.adapter.restore_defaults()
        self.assertEqual(self.adapter.get_value("playback.default_volume"), 70)
        self.assertTrue(self.adapter.is_dirty())
        self.adapter.cancel()
        self.assertEqual(self.adapter.get_value("playback.default_volume"), 42)
        self.assertFalse(self.adapter.is_dirty())
        self.adapter.restore_category_defaults("about")
        self.assertFalse(self.adapter.is_dirty())

    def test_lyrics_preview_and_immersive_options_are_shared_in_memory(self) -> None:
        self.adapter.set_value("lyrics.show_translation", False)
        self.adapter.set_value("lyrics.show_romanization", True)
        self.adapter.set_value("lyrics.lyrics_font_scale", 1.25)
        self.adapter.set_value("lyrics.lyrics_offset_ms", -180)
        self.assertFalse(self.lyrics.display_options["translation"])
        self.assertTrue(self.lyrics.display_options["romanization"])
        self.assertEqual(self.lyrics.display_options["font_scale"], 1.25)
        self.adapter.set_value("immersive.global_font_scale", 125)
        self.adapter.set_value("immersive.active_font_size", 58)
        self.assertIs(self.options, self.adapter._immersive_options)
        self.assertEqual(self.options.global_font_scale, 125)
        self.assertEqual(self.options.active_font_size, 58)
        self.adapter.cancel()
        self.assertEqual(self.options.global_font_scale, 100)
        self.assertEqual(self.options.active_font_size, 46)

    def test_search_mock_folders_cache_and_update_scenarios(self) -> None:
        self.assertTrue(any(item.path == "appearance.theme_mode" for item in self.adapter.search("theme")))
        self.assertTrue(any(item.path == "lyrics.show_translation" for item in self.adapter.search("歌词")))
        self.assertTrue(self.adapter.add_mock_folder("E:\\Music\\Preview"))
        self.assertFalse(self.adapter.add_mock_folder("E:\\Music\\Preview"))
        self.assertTrue(self.adapter.remove_mock_folder("E:\\Music\\Preview"))
        before = self.adapter.cache_stats()
        self.adapter.clear_mock_incomplete_cache()
        self.assertEqual(self.adapter.cache_stats()["incomplete"], 0)
        self.adapter.refresh_mock_cache_stats()
        self.assertGreaterEqual(self.adapter.cache_stats()["total"], before["artwork"])
        phases = [self.adapter.check_mock_updates()["phase"] for _ in range(3)]
        self.assertEqual(phases, ["latest", "available", "failed"])


class SettingsPageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1400, 850)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _settings_page(self) -> SettingsPage:
        self.window.navigation_adapter.set_route("settings")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, SettingsPage)
        return page

    def _immersive_page(self) -> ImmersiveLyricsPage:
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, ImmersiveLyricsPage)
        return page

    def test_nine_categories_route_reuse_and_responsive_draft_preservation(self) -> None:
        page = self._settings_page()
        self.assertEqual(tuple(page.sidebar._buttons), ("general", "appearance", "playback", "lyrics", "immersive", "library", "cache", "updates", "about"))
        page.adapter.set_value("general.restore_last_session", False)
        page.set_category("cache")
        page.scroll.verticalScrollBar().setValue(18)
        page_id = id(page)
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertIs(self.window.router.currentWidget(), page)
            self.assertEqual(id(page), page_id)
            self.assertEqual(page.current_category, "cache")
            self.assertFalse(page.scroll.horizontalScrollBar().isVisible())
            self.assertEqual(page.sidebar._compact, width < 1100)
        self.assertFalse(page.adapter.get_value("general.restore_last_session"))
        page.set_category("about")
        self.assertFalse(page.footer.category_defaults_button.isEnabled())

    def test_category_sidebar_keeps_draft_while_switching_between_text_and_icon_modes(self) -> None:
        page = self._settings_page()
        page.adapter.set_value("playback.autoplay_on_start", True)
        page_id = id(page)

        self.window.resize(1200, 800)
        self.app.processEvents()
        self.assertFalse(page.sidebar._compact)
        self.assertEqual(page.sidebar.minimumWidth(), 176)
        for button in page.sidebar._buttons.values():
            self.assertEqual(button.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.assertTrue(button.text())

        page.set_category("playback")
        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertTrue(page.sidebar._compact)
        self.assertEqual(page.sidebar.minimumWidth(), 56)
        for button in page.sidebar._buttons.values():
            self.assertEqual(button.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.assertTrue(button.toolTip())

        page.set_category("lyrics")
        self.assertEqual(id(page), page_id)
        self.assertTrue(page.adapter.get_value("playback.autoplay_on_start"))

    def test_theme_preview_cancel_and_popup_palette_are_readable(self) -> None:
        page = self._settings_page()
        page.adapter.set_value("appearance.theme_mode", "light")
        self.app.processEvents()
        self.assertEqual(self.window.theme.mode, "light")
        theme_combo = page._controls["appearance.theme_mode"]
        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            self.app.processEvents()
            view = theme_combo.view()
            self.assertEqual(view.palette().color(QPalette.ColorRole.Base).alpha(), 255)
            self.assertEqual(view.palette().color(QPalette.ColorRole.Window).alpha(), 255)
            self.assertNotEqual(
                view.palette().color(QPalette.ColorRole.Text).name(),
                view.palette().color(QPalette.ColorRole.Base).name(),
            )
        page.adapter.cancel()
        self.app.processEvents()
        self.assertEqual(self.window.theme.mode, "dark")

    def test_playback_dependencies_lyrics_preview_and_immersive_two_way_sync(self) -> None:
        page = self._settings_page()
        crossfade = page._controls["playback.crossfade_seconds"]
        self.assertFalse(crossfade.isEnabled())
        page.adapter.set_value("playback.crossfade_enabled", True)
        self.assertTrue(crossfade.isEnabled())
        page.adapter.set_value("lyrics.show_translation", False)
        page.adapter.set_value("lyrics.show_romanization", True)
        page.adapter.set_value("lyrics.lyrics_offset_ms", 420)
        self.assertFalse(self.window.lyrics_adapter.display_options["translation"])
        self.assertTrue(self.window.lyrics_adapter.display_options["romanization"])
        page.adapter.set_value("immersive.global_font_scale", 125)
        page.adapter.set_value("immersive.active_font_size", 58)
        page.immersive_preview_requested.emit()
        self.app.processEvents()
        immersive = self.window.router.currentWidget()
        self.assertIsInstance(immersive, ImmersiveLyricsPage)
        self.assertIs(immersive.options, self.window.immersive_lyrics_options)
        # V4 keeps the approved immersive hierarchy within its 54-64px readable range.
        self.assertEqual(immersive.lyrics_view.canvas.effective_font_sizes[0], min(64, round(58 * 1.25)))
        immersive.set_background_mode("gradient")
        self.app.processEvents()
        self.assertEqual(page.adapter.get_value("immersive.background_mode"), "gradient")
        immersive.controls.back_button.click()
        self.app.processEvents()
        self.assertIs(self.window.router.currentWidget(), page)

    def test_search_jump_empty_mock_actions_and_dirty_leave_confirmation(self) -> None:
        page = self._settings_page()
        page.search_box.input.setText("theme")
        self.app.processEvents()
        self.assertIs(page.content_stack.currentWidget(), page.search_page)
        buttons = page.search_page.findChildren(QPushButton)
        result_button = next(item for item in buttons if item.text().endswith("主题"))
        result_button.click()
        self.app.processEvents()
        self.assertEqual(page.current_category, "appearance")
        page.search_box.input.setText("not-a-setting")
        self.app.processEvents()
        self.assertTrue(page.search_empty.isVisible())
        page.adapter.add_mock_folder("E:\\Music\\Temporary")
        self.assertTrue(any(page.folder_list.item(row).text() == "E:\\Music\\Temporary" for row in range(page.folder_list.count())))
        page.adapter.clear_mock_incomplete_cache()
        self.assertIn("未完成 0 MB", page.cache_stats_label.text())
        page.adapter.set_value("general.restore_last_session", False)
        self.window.navigation_adapter.set_route("library")
        self.app.processEvents()
        self.assertIs(self.window.router.currentWidget(), page)
        self.assertTrue(page.confirmation_bar.isVisible())
        page.confirm_cancel.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "settings")
        self.window.navigation_adapter.set_route("library")
        self.app.processEvents()
        page.confirm_secondary.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "library")
        self.assertIs(self.window.router.currentWidget(), self.window.library_page)


if __name__ == "__main__":
    unittest.main()
