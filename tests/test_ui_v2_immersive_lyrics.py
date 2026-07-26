from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage
from app.ui_v2.pages.lyrics_page import LyricsPage
from app.ui_v2.shell.main_window import MainWindow


class UiV2ImmersiveLyricsTests(unittest.TestCase):
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

    def _play_track(self) -> None:
        model = self.window.library_page.track_table.model
        index = next(
            model.index(row, int(TrackColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if not track.is_missing and track.duration_ms is not None
        )
        self.window.library_page.track_table.doubleClicked.emit(index)
        self.app.processEvents()

    def _ordinary_page(self) -> LyricsPage:
        self.window.navigation_adapter.set_route("lyrics")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, LyricsPage)
        return page

    def _immersive_page(self) -> ImmersiveLyricsPage:
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, ImmersiveLyricsPage)
        return page

    def test_routes_are_distinct_cached_pages_and_shell_hides_then_restores(self) -> None:
        ordinary = self._ordinary_page()
        ordinary.header.immersive_button.click()
        self.app.processEvents()
        immersive = self.window.router.currentWidget()
        self.assertIsInstance(immersive, ImmersiveLyricsPage)
        self.assertIsNot(ordinary, immersive)
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertFalse(self.window.player_bar.isVisible())
        immersive.controls.back_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "lyrics")
        self.assertIs(self.window.router.currentWidget(), ordinary)
        self.assertTrue(self.window.sidebar.isVisible())
        self.assertTrue(self.window.player_bar.isVisible())
        self.assertIs(self._immersive_page(), immersive)
        immersive.show_settings_panel()
        immersive.settings_panel.exit_immersive_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "lyrics")
        self.assertIs(self._immersive_page(), immersive)

    def test_shared_document_line_segment_and_display_state(self) -> None:
        self._play_track()
        ordinary = self._ordinary_page()
        document = self.window.lyrics_adapter.document
        immersive = self._immersive_page()
        self.assertIs(immersive.lyrics_adapter, ordinary.adapter)
        self.assertIs(immersive.document, document)
        self.assertIs(immersive.lyrics_view.canvas.document, document)
        self.window.playback_adapter.seek(3_000)
        self.app.processEvents()
        self.assertEqual(
            immersive.lyrics_view.canvas.current_index,
            next(index for index, line in enumerate(document.lines) if line.id == ordinary.adapter.active_line.id),
        )
        self.assertGreaterEqual(immersive.lyrics_view.canvas._active_segment_index, 0)
        ordinary.header.translation_button.click()
        ordinary.header.romanization_button.click()
        self.app.processEvents()
        self.assertFalse(immersive.lyrics_view.canvas._show_translation)
        self.assertTrue(immersive.lyrics_view.canvas._show_romanization)
        immersive.set_translation_visible(True)
        immersive.set_romanization_visible(False)
        self.app.processEvents()
        self.assertTrue(self.window.lyrics_adapter.display_options["translation"])
        self.assertFalse(self.window.lyrics_adapter.display_options["romanization"])
        self.assertTrue(ordinary.header.translation_button.isChecked())
        self.assertFalse(ordinary.header.romanization_button.isChecked())

    def test_shared_playback_controls_seek_volume_and_track_updates(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        controls = immersive.controls
        self.assertIs(controls._adapter, self.window.playback_adapter)
        controls.play_button.click()
        self.app.processEvents()
        self.assertFalse(self.window.playback_adapter.state.is_playing)
        controls.play_button.click()
        controls.progress_slider.setValue(5_000)
        controls.progress_slider.sliderReleased.emit()
        controls.volume_slider.setValue(42)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.position_ms, 5_000)
        self.assertEqual(self.window.playback_adapter.state.volume, 42)
        first_track_id = self.window.playback_adapter.state.current_track.id
        controls.next_button.click()
        self.app.processEvents()
        self.assertNotEqual(self.window.playback_adapter.state.current_track.id, first_track_id)
        self.assertEqual(immersive.document.track_id, self.window.playback_adapter.state.current_track.id)
        self.assertEqual(controls.progress_slider.value(), self.window.playback_adapter.state.position_ms)
        controls.previous_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, first_track_id)

    def test_options_survive_route_track_resize_and_reuse_core_widgets(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        panel = immersive.settings_panel
        core_ids = (id(immersive.lyrics_view.canvas), id(immersive.controls), id(panel))
        panel.background_combo.setCurrentIndex(panel.background_combo.findData("gradient"))
        panel.global_lyric_scale_slider.setValue(125)
        panel.active_font_slider.setValue(58)
        panel.auto_hide_check.setChecked(False)
        self.app.processEvents()
        self.assertEqual(immersive.options.background_mode, "gradient")
        self.assertEqual(immersive.options.global_font_scale, 125)
        self.assertEqual(immersive.options.active_font_size, 58)
        self.assertFalse(immersive.options.controls_auto_hide)
        self.assertEqual(immersive.lyrics_view.canvas.effective_font_sizes[0], round(58 * 1.25))
        document = immersive.document
        background_generation = immersive.background.generation
        background_cache = immersive.background._cache
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertIs(immersive.document, document)
            self.assertEqual((id(immersive.lyrics_view.canvas), id(immersive.controls), id(panel)), core_ids)
            self.assertFalse(immersive.lyrics_view.horizontalScrollBar().isVisible())
            self.assertEqual(immersive.background.generation, background_generation)
            self.assertIs(immersive.background._cache, background_cache)
        self.window.playback_adapter.play_next()
        self.app.processEvents()
        self.assertEqual(immersive.options.global_font_scale, 125)
        self.assertEqual(immersive.options.active_font_size, 58)
        self.window.navigation_adapter.set_route("lyrics")
        self._immersive_page()
        self.assertEqual(immersive.options.global_font_scale, 125)
        self.assertEqual(immersive.options.active_font_size, 58)

    def test_fullscreen_escape_transparency_and_same_main_window(self) -> None:
        immersive = self._immersive_page()
        main_id = id(self.window)
        geometry = self.window.geometry()
        immersive.enter_fullscreen()
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.assertTrue(immersive.is_fullscreen)
        self.assertEqual(id(self.window), main_id)
        immersive.show_settings_panel()
        immersive.settings_panel.theme_combo.showPopup()
        self.app.processEvents()
        immersive._handle_escape()
        self.assertTrue(immersive.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        immersive._handle_escape()
        self.assertFalse(immersive.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        immersive._handle_escape()
        self.app.processEvents()
        self.assertFalse(self.window.isFullScreen())
        self.assertEqual(self.window.geometry(), geometry)
        immersive.setFocus()
        QTest.keyClick(immersive, Qt.Key.Key_F11)
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        QTest.keyClick(immersive, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.window.isFullScreen())
        immersive.set_background_mode("transparent")
        self.app.processEvents()
        self.assertEqual(id(self.window), main_id)
        self.assertTrue(self.window._immersive_transparency_enabled)
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertFalse(self.window.player_bar.isVisible())
        immersive.controls.back_button.click()
        self.app.processEvents()
        self.assertFalse(self.window._immersive_transparency_enabled)

    def test_auto_hide_and_all_five_geometry_bands(self) -> None:
        self._play_track()
        immersive = self._immersive_page()
        immersive.set_auto_hide_controls(True)
        immersive.hide_controls_preview()
        QTest.qWait(240)
        self.assertFalse(immersive.controls_visible)
        self.window.playback_adapter.pause()
        QTest.qWait(240)
        self.assertTrue(immersive.controls_visible)
        immersive.show_settings_panel()
        immersive.hide_controls_preview()
        QTest.qWait(240)
        self.assertTrue(immersive.controls_visible)
        immersive.hide_settings_panel()
        expected = ((900, 600, "compact"), (1100, 700, "standard"), (1400, 850, "wide"), (1600, 900, "wide"), (1920, 1080, "ultra"))
        for width, height, band in expected:
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertEqual(immersive._layout_band, band)
            self.assertEqual(self.window.size(), QSize(width, height))
        immersive.enter_fullscreen()
        self.app.processEvents()
        self.assertTrue(immersive.is_fullscreen)
        immersive.exit_fullscreen()
        immersive.wake_controls()
        self.window.navigation_adapter.set_route("lyrics")
        self.app.processEvents()
        self.assertFalse(immersive._controls_hide_timer.isActive())

    def test_formal_page_accepts_dark_and_light_theme_without_rebuild(self) -> None:
        immersive = self._immersive_page()
        core_ids = (id(immersive.lyrics_view.canvas), id(immersive.controls), id(immersive.settings_panel))
        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            self.app.processEvents()
            self.assertEqual(immersive.options.theme, mode)
            self.assertEqual(immersive._theme.mode, mode)
            self.assertEqual((id(immersive.lyrics_view.canvas), id(immersive.controls), id(immersive.settings_panel)), core_ids)


if __name__ == "__main__":
    unittest.main()
