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
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QBoxLayout

from app.ui_v2.experiments.immersive_lyrics_preview import (
    CHINESE_LINES,
    ENGLISH_LINES,
    MOCK_ARTWORKS,
    ImmersiveLyricsPreview,
)


class ImmersiveLyricsPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = ImmersiveLyricsPreview()
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_preview_is_independent_from_formal_shell_and_adapters(self) -> None:
        preview_module = sys.modules[ImmersiveLyricsPreview.__module__]
        self.assertNotIn("MainWindow", preview_module.__dict__)
        self.assertNotIn("ContentRouter", preview_module.__dict__)
        self.assertNotIn("PlaybackAdapter", preview_module.__dict__)
        self.assertFalse(hasattr(self.window, "lyrics_adapter"))
        self.assertFalse(hasattr(self.window, "playback_adapter"))
        self.assertIsNotNone(self.window.background)
        self.assertIsNotNone(self.window.readability_overlay)
        self.assertIsNotNone(self.window.lyric_protection)
        self.assertIsNotNone(self.window.lyrics_view.canvas)

    def test_theme_artwork_language_and_display_options(self) -> None:
        self.window.set_theme_mode("light")
        self.assertEqual(self.window._theme.mode, "light")
        self.assertEqual(self.window.overlay_strength, 25)
        for artwork in MOCK_ARTWORKS:
            self.window.set_artwork_key(artwork.key)
            self.assertEqual(self.window.background.artwork_key, artwork.key)
        self.window.set_language("英文")
        self.assertEqual(self.window.lyrics_view.canvas.language, "英文")
        self.assertEqual(len(ENGLISH_LINES), 7)
        self.window.set_translation_visible(False)
        self.window.set_romanization_visible(False)
        self.assertFalse(self.window.lyrics_view.canvas._show_translation)
        self.assertFalse(self.window.lyrics_view.canvas._show_romanization)
        self.window.set_language("中文")
        self.assertEqual(len(CHINESE_LINES), 7)

    def test_continuous_background_overlay_and_control_opacity_isolated_from_content(self) -> None:
        core_ids = self._core_ids()
        self.window.set_background_mode("transparent")
        self.app.processEvents()
        if not self.window.transparency_supported:
            self.assertEqual(self.window.background_mode, "artwork")
            return
        self.assertTrue(self.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertEqual(self.window.root_background_alpha, 0)
        self.assertEqual(self.window.content_layer_alpha, 255)
        self.assertEqual(self.window.lyrics_view.canvas.text_alpha, 255)
        self.assertIsNone(self.window.content.graphicsEffect())
        self.assertIsNone(self.window.lyrics_view.canvas.graphicsEffect())
        self.window.set_background_opacity(37)
        self.assertEqual(self.window.background_opacity_percent, 37)
        self.assertEqual(self.window.background.surface_alpha, round(255 * 0.37))
        self.assertEqual(self.window.lyrics_view.canvas.text_alpha, 255)
        self.window.set_background_opacity(63)
        self.assertEqual(self.window.background_opacity_percent, 63)
        self.window.set_overlay_strength(78)
        self.assertEqual(self.window.readability_overlay.strength, 78)
        self.window.set_control_surface_opacity(37)
        self.assertEqual(self.window.controls.surface_opacity, 37)
        self.assertIn("rgba", self.window.controls.styleSheet())
        self.assertEqual(self._core_ids(), core_ids)
        self.window.set_background_mode("gradient")
        self.assertTrue(self.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertEqual(self.window.root_background_alpha, 255)

    def test_background_modes_reuse_one_window_and_preserve_settings(self) -> None:
        self.window.resize(1400, 850)
        self.window.show_settings_panel()
        self.window.set_theme_mode("light")
        self.window.set_background_opacity(63)
        self.window.set_overlay_strength(37)
        self.window.set_control_surface_opacity(78)
        self.window.set_lyric_font_sizes(52, 34, 18, 17)
        self.window.set_global_lyric_scale(125)
        self.app.processEvents()
        before = self.window.instance_snapshot()
        stable_keys = (
            "window_id",
            "top_level_widget_count",
            "preview_top_level_count",
            "lyrics_canvas_id",
            "floating_controls_id",
            "settings_panel_id",
            "geometry",
            "theme",
            "background_opacity",
            "overlay_strength",
            "control_surface_opacity",
            "global_lyric_scale",
            "font_sizes",
            "settings_visible",
        )
        for mode in ("transparent", "artwork", "gradient", "solid"):
            self.window.set_background_mode(mode)
            self.app.processEvents()
            snapshot = self.window.instance_snapshot()
            self.assertEqual(self.window.background_mode, mode)
            for key in stable_keys:
                self.assertEqual(snapshot[key], before[key], key)
        self.assertEqual(self.window.background.surface_alpha, 255)

    def test_font_ranges_weight_inactive_opacity_and_text_protection(self) -> None:
        canvas = self.window.lyrics_view.canvas
        self.window.set_lyric_font_sizes(36, 22, 14, 12)
        self.assertEqual((canvas.active_font_size, canvas.inactive_font_size, canvas.translation_font_size, canvas.romanization_font_size), (36, 22, 14, 12))
        self.window.set_lyric_font_sizes(64, 44, 30, 24)
        self.assertEqual((canvas.active_font_size, canvas.inactive_font_size, canvas.translation_font_size, canvas.romanization_font_size), (64, 44, 30, 24))
        self.window.set_lyric_weight("Bold")
        self.assertEqual(canvas._weight_name, "Bold")
        self.window.set_inactive_lyric_opacity(37)
        self.assertEqual(canvas.inactive_opacity, 37)
        for mode in ("无", "轻微阴影", "描边", "描边 + 阴影"):
            self.window.set_text_protection(mode)
            self.assertEqual(canvas.text_protection, mode)
        self.window.set_background_mode("transparent")
        self.window.set_background_opacity(78)
        self.assertEqual(canvas.text_alpha, 255)
        panel = self.window.settings_panel
        self.assertEqual((panel.active_font_slider.minimum(), panel.active_font_slider.maximum()), (32, 72))
        self.assertEqual((panel.inactive_font_slider.minimum(), panel.inactive_font_slider.maximum()), (22, 48))
        self.assertEqual((panel.translation_font_slider.minimum(), panel.translation_font_slider.maximum()), (14, 32))
        self.assertEqual((panel.romanization_font_slider.minimum(), panel.romanization_font_slider.maximum()), (12, 26))

    def test_global_lyric_scale_preserves_role_proportions_and_canvas_instance(self) -> None:
        canvas = self.window.lyrics_view.canvas
        canvas_id = id(canvas)
        base_sizes = (46, 30, 14, 15)
        self.window.set_lyric_font_sizes(*base_sizes)
        for scale in (75, 100, 125, 160):
            self.window.set_global_lyric_scale(scale)
            self.assertEqual(canvas.global_scale, scale)
            self.assertEqual(canvas.effective_font_sizes, tuple(round(size * scale / 100) for size in base_sizes))
            self.assertEqual(id(self.window.lyrics_view.canvas), canvas_id)
        self.window.set_global_lyric_scale(160)
        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertEqual(canvas.global_scale, 160)
        self.assertFalse(self.window.lyrics_view.horizontalScrollBar().isVisible())
        self.window.set_global_lyric_scale(100)
        self.assertEqual(canvas.effective_font_sizes, base_sizes)

    def test_settings_panel_uses_sliders_and_updates_live_values(self) -> None:
        self.assertFalse(self.window.settings_panel.isVisible())
        self.window.show_settings_panel()
        self.app.processEvents()
        panel = self.window.settings_panel
        self.assertTrue(panel.isVisible())
        self.assertIs(panel.scroll.widget(), panel.body)
        self.assertTrue(panel.title_label.isVisible())
        self.assertTrue(panel.close_button.isVisible())
        self.assertEqual((panel.background_opacity_slider.minimum(), panel.background_opacity_slider.maximum()), (0, 100))
        self.assertEqual((panel.overlay_strength_slider.minimum(), panel.overlay_strength_slider.maximum()), (0, 90))
        self.assertEqual((panel.control_surface_opacity_slider.minimum(), panel.control_surface_opacity_slider.maximum()), (0, 100))
        self.assertEqual((panel.global_lyric_scale_slider.minimum(), panel.global_lyric_scale_slider.maximum()), (75, 160))
        panel.background_opacity_slider.setValue(37)
        panel.overlay_strength_slider.setValue(63)
        panel.control_surface_opacity_slider.setValue(78)
        panel.global_lyric_scale_slider.setValue(125)
        panel.active_font_slider.setValue(64)
        panel.inactive_opacity_slider.setValue(53)
        self.app.processEvents()
        self.assertEqual(self.window.background_opacity_percent, 37)
        self.assertEqual(self.window.overlay_strength, 63)
        self.assertEqual(self.window.control_surface_opacity, 78)
        self.assertEqual(self.window.global_lyric_scale, 125)
        self.assertEqual(self.window.lyrics_view.canvas.active_font_size, 64)
        self.assertEqual(self.window.lyrics_view.canvas.inactive_opacity, 53)
        self.assertFalse(panel.advanced_sizes_container.isVisible())
        panel.advanced_sizes_toggle.setChecked(True)
        self.assertTrue(panel.advanced_sizes_container.isVisible())
        panel.reset_lyric_sizes_button.click()
        self.assertEqual(self.window.global_lyric_scale, 100)
        self.assertEqual(self.window.lyrics_view.canvas.effective_font_sizes, (46, 30, 14, 15))
        self.window.hide_settings_panel()
        self.assertFalse(panel.isVisible())

    def test_combo_popups_are_opaque_elevated_surfaces_in_every_theme(self) -> None:
        panel = self.window.settings_panel
        self.window.show_settings_panel()
        for mode in ("dark", "light"):
            self.window.set_theme_mode(mode)
            self.window.set_background_mode("transparent")
            self.app.processEvents()
            for combo in panel._combos:
                view = combo.view()
                palette = view.palette()
                base = palette.color(QPalette.ColorRole.Base)
                text = palette.color(QPalette.ColorRole.Text)
                highlight = palette.color(QPalette.ColorRole.Highlight)
                self.assertEqual(base.alpha(), 255)
                self.assertEqual(text.alpha(), 255)
                self.assertGreater(abs(base.lightness() - text.lightness()), 60)
                self.assertNotEqual(QColor(self.window._theme.colors.hover_background), highlight)
                self.assertFalse(view.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
                self.assertFalse(view.viewport().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
                self.assertIn("::item:hover", view.styleSheet())
                self.assertIn("::item:selected", view.styleSheet())
                self.assertIn("background:", view.window().styleSheet())
                combo.showPopup()
                self.app.processEvents()
                self.assertTrue(view.isVisible())
                self.assertEqual(view.window().palette().color(QPalette.ColorRole.Base).alpha(), 255)
                self.assertEqual(view.window().palette().color(QPalette.ColorRole.Window).alpha(), 255)
                self.assertTrue(panel.close_open_popup())

    def test_escape_closes_settings_before_exiting_fullscreen(self) -> None:
        self.window.enter_fullscreen()
        self.app.processEvents()
        self.window.show_settings_panel()
        self.assertTrue(self.window.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        self.window.settings_panel.theme_combo.showPopup()
        self.app.processEvents()
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertTrue(self.window.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        self.assertFalse(self.window.settings_panel.theme_combo.view().isVisible())
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.window.settings_panel.isVisible())
        self.assertTrue(self.window.isFullScreen())
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.window.isFullScreen())

    def test_auto_hide_controls_and_open_settings_keeps_controls_visible(self) -> None:
        self.window.set_auto_hide_controls(True)
        self.window.hide_controls_preview()
        QTest.qWait(240)
        self.assertFalse(self.window.controls_visible)
        self.window.wake_controls()
        QTest.qWait(240)
        self.assertTrue(self.window.controls_visible)
        self.window.show_settings_panel()
        QTest.qWait(240)
        self.window.hide_controls_preview()
        QTest.qWait(240)
        self.assertTrue(self.window.controls_visible)

    def test_geometry_reflows_without_scrollbars_or_recreating_layers(self) -> None:
        generation = self.window.background.generation
        cache = self.window.background._cache
        core_ids = self._core_ids()
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertEqual(self.window.size(), QSize(width, height))
            self.assertFalse(self.window.lyrics_view.horizontalScrollBar().isVisible())
            self.assertEqual(self.window.background.generation, generation)
            self.assertIs(self.window.background._cache, cache)
            self.assertEqual(self._core_ids(), core_ids)
        self.window.resize(1920, 1080)
        self.app.processEvents()
        self.assertEqual(self.window.content.width(), 1640)
        self.assertGreater(self.window.content.x(), 0)

    def test_five_responsive_bands_and_settings_panel_bounds(self) -> None:
        expected = ((780, "small"), (900, "compact"), (1100, "standard"), (1400, "wide"), (1700, "ultra"))
        for width, band in expected:
            self.window.resize(width, 700)
            self.app.processEvents()
            self.assertEqual(self.window._layout_band, band)
            expected_direction = QBoxLayout.Direction.TopToBottom if band == "small" else QBoxLayout.Direction.LeftToRight
            self.assertEqual(self.window._content_layout.direction(), expected_direction)
            self.assertLessEqual(self.window.settings_panel.width(), round(width * 0.88) if width < 900 else 420)

    def test_fullscreen_keyboard_double_click_and_geometry_restore(self) -> None:
        self.window.setGeometry(111, 123, 1400, 850)
        self.app.processEvents()
        original = self.window.geometry()
        core_ids = self._core_ids()
        self.window.enter_fullscreen()
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.assertEqual(self.window.normal_geometry, original)
        self.window.exit_fullscreen()
        self.app.processEvents()
        self.assertEqual(self.window.geometry(), original)
        QTest.keyClick(self.window, Qt.Key.Key_F11)
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.window.isFullScreen())
        QTest.mouseDClick(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(8, 8))
        self.app.processEvents()
        self.assertTrue(self.window.isFullScreen())
        self.window.exit_fullscreen()
        self.assertEqual(self._core_ids(), core_ids)

    def test_fullscreen_switch_keeps_same_preview_window(self) -> None:
        self.window.setGeometry(92, 104, 1400, 850)
        self.app.processEvents()
        before = self.window.instance_snapshot()
        self.window.enter_fullscreen()
        self.app.processEvents()
        during = self.window.instance_snapshot()
        self.assertEqual(during["window_id"], before["window_id"])
        self.assertEqual(during["top_level_widget_count"], before["top_level_widget_count"])
        self.assertEqual(during["preview_top_level_count"], before["preview_top_level_count"])
        self.assertEqual(during["lyrics_canvas_id"], before["lyrics_canvas_id"])
        self.window.exit_fullscreen()
        self.app.processEvents()
        after = self.window.instance_snapshot()
        self.assertEqual(after["window_id"], before["window_id"])
        self.assertEqual(after["top_level_widget_count"], before["top_level_widget_count"])
        self.assertEqual(after["preview_top_level_count"], before["preview_top_level_count"])
        self.assertEqual(after["geometry"], before["geometry"])

    def _core_ids(self) -> tuple[int, ...]:
        return tuple(
            id(widget)
            for widget in (
                self.window.background,
                self.window.readability_overlay,
                self.window.lyric_protection,
                self.window.content,
                self.window.track_info,
                self.window.lyrics_view,
                self.window.lyrics_view.canvas,
                self.window.controls,
                self.window.settings_panel,
            )
        )


if __name__ == "__main__":
    unittest.main()
