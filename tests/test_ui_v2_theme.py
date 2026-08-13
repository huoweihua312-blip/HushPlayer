from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.ui_v2.theme.icons import favorite, icon, online, search
from app.ui_v2.theme.styles import build_dialog_stylesheet, build_stylesheet
from app.ui_v2.theme.tokens import (
    ThemeColors,
    ThemeFonts,
    ThemeMetrics,
    font_family_qss,
    get_theme,
    resolve_font_family,
)


class UiV2ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_light_and_dark_have_complete_distinct_color_tokens(self) -> None:
        required = {
            "app_background", "window_background", "content_background", "sidebar_background",
            "titlebar_background", "playerbar_background", "surface_primary", "surface_secondary",
            "surface_elevated", "surface_hover", "surface_selected", "surface_pressed",
            "divider", "text_primary", "text_secondary", "text_tertiary", "text_disabled",
            "icon_default", "icon_hover", "icon_active", "progress_track", "progress_fill",
            "focus_ring", "shadow", "overlay",
            "window_background", "navigation_background", "content_background",
            "elevated_background", "player_background", "input_background",
            "primary_text", "secondary_text", "subtle_text", "disabled_text",
            "border", "border_strong", "accent", "accent_hover", "accent_pressed",
            "selected_background", "playing_background", "hover_background", "danger",
            "warning", "success",
        }
        self.assertTrue(required.issubset(ThemeColors.__dataclass_fields__))
        light = get_theme("light")
        dark = get_theme("dark")
        self.assertNotEqual(light.colors.window_background, dark.colors.window_background)
        self.assertNotEqual(light.colors.primary_text, dark.colors.primary_text)
        self.assertNotEqual(light.colors.icon_default, light.colors.text_disabled)
        self.assertNotEqual(dark.colors.icon_default, dark.colors.text_disabled)

    def test_metrics_fonts_styles_and_icons_are_complete(self) -> None:
        self.assertTrue({"spacing_xs", "spacing_xl", "radius_lg", "page_margin", "control_height", "icon_lg"}.issubset(ThemeMetrics.__dataclass_fields__))
        self.assertTrue({"page_title", "section_title", "body", "secondary", "caption"}.issubset(ThemeFonts.__dataclass_fields__))
        theme = get_theme("dark")
        stylesheet = build_stylesheet(theme)
        self.assertIn(theme.colors.accent, stylesheet)
        self.assertIn("QWidget#libraryWorkSurface", stylesheet)
        self.assertIn("QWidget#trackListWorkSurface", stylesheet)
        self.assertIn("QWidget#collectionActionRow", stylesheet)
        self.assertIn("QWidget#onlineSourcePage", stylesheet)
        self.assertIn(f"font-size: {theme.fonts.body}px", stylesheet)
        self.assertGreaterEqual(theme.fonts.body, 15)
        self.assertGreaterEqual(theme.fonts.caption, 13)
        dialog_stylesheet = build_dialog_stylesheet(theme)
        self.assertIn('QDialog QPushButton[role="primary"]', dialog_stylesheet)
        self.assertIn("QDialog QFrame#settingsCard", dialog_stylesheet)
        self.assertIn("QDialog QProgressBar::chunk", dialog_stylesheet)
        self.assertFalse(favorite(theme).isNull())
        self.assertFalse(online(theme, "hover").isNull())
        self.assertFalse(search(theme, "disabled").isNull())
        self.assertFalse(icon("moon", get_theme("dark")).isNull())
        self.assertFalse(icon("sun", get_theme("light")).isNull())

    def test_bundled_chinese_font_is_available_to_source_and_packaged_builds(self) -> None:
        font_root = PROJECT_ROOT / "app" / "ui_v2" / "assets" / "fonts"
        regular_path = font_root / "SourceHanSansSC-Regular.otf"
        medium_path = font_root / "SourceHanSansSC-Medium.otf"
        bold_path = font_root / "SourceHanSansSC-Bold.otf"
        license_path = font_root / "SourceHanSansSC-OFL.txt"
        self.assertTrue(regular_path.is_file())
        self.assertTrue(medium_path.is_file())
        self.assertTrue(bold_path.is_file())
        self.assertGreater(regular_path.stat().st_size, 1_000_000)
        self.assertGreater(medium_path.stat().st_size, 1_000_000)
        self.assertGreater(bold_path.stat().st_size, 1_000_000)
        self.assertTrue(license_path.is_file())
        self.assertIn("SIL OPEN FONT LICENSE", license_path.read_text(encoding="utf-8"))
        self.assertIn('"Source Han Sans SC"', font_family_qss())
        self.assertEqual(resolve_font_family(), "Source Han Sans SC")

    def test_light_and_dark_row_state_colors_are_distinct_and_restrained(self) -> None:
        for mode in ("light", "dark"):
            colors = get_theme(mode).colors
            self.assertNotEqual(colors.hover_background, colors.selected_background)
            self.assertNotEqual(colors.selected_background, colors.playing_background)
        dark = get_theme("dark").colors
        self.assertLess(
            QColor(dark.selected_background).saturation(),
            QColor(dark.accent).saturation(),
        )
        self.assertLessEqual(QColor(dark.app_background).saturation(), 5)
        self.assertLessEqual(QColor(dark.content_background).saturation(), 5)
        self.assertGreater(
            QColor(dark.content_background).lightness(),
            QColor(dark.app_background).lightness(),
        )


if __name__ == "__main__":
    unittest.main()
