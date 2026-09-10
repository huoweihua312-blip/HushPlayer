"""Opt-in B2 presets must not change legacy consumers or control contracts."""
import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget

from app.ui_v2.theme.tokens import DARK_THEME, LIGHT_THEME, get_theme
from app.ui_v2.theme.styles import input_qss, surface_qss, divider_qss
from app.ui_v2.theme.button_styles import button_qss
from app.ui_v2.theme.icons import icon_sizing


class B2FoundationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_default_profile_and_typography_stay_legacy(self):
        for mode, legacy in (("dark", DARK_THEME), ("light", LIGHT_THEME)):
            self.assertIs(get_theme(mode), legacy)
            target = get_theme(mode, profile="b2")
            self.assertIs(target.fonts, legacy.fonts)
            self.assertEqual(legacy.metrics.radius_control, 8)
            self.assertEqual(legacy.fonts.family, "MiSans")
        self.assertEqual(DARK_THEME.colors.content_background, "#1b1b1b")
        self.assertEqual(LIGHT_THEME.colors.content_background, "#f8f8f6")
        with self.assertRaises(ValueError):
            get_theme("dark", profile="typo")

    def test_complete_semantics_and_derived_aliases(self):
        for mode in ("dark", "light"):
            c = get_theme(mode, profile="b2").colors
            for role in ("background", "content_background", "sidebar", "surface",
                         "surface_elevated", "primary_text", "secondary_text", "text_muted",
                         "accent", "divider", "hover_background", "selected_background",
                         "playing_background", "disabled_text", "error", "warning",
                         "success", "focus_ring", "primary_button_fill", "text_on_accent"):
                self.assertTrue(QColor(getattr(c, role)).isValid(), (mode, role))
            self.assertEqual(c.primary_text, c.text_primary)
            self.assertEqual(c.selected_background, c.surface_selected)
            self.assertEqual(c.sidebar_background, c.navigation_background)
            self.assertNotEqual(c.playing_background, c.selected_background)
        customized = replace(DARK_THEME.colors, accent="#abcdef", danger="#123456")
        self.assertEqual(customized.primary_button_fill, "#abcdef")
        self.assertEqual(customized.error, "#123456")
        self.assertEqual(customized.content_error, "#123456")

    def test_css_alpha_is_converted_to_qt_argb(self):
        dark = QColor(get_theme("dark", profile="b2").colors.playing_background)
        light = QColor(get_theme("light", profile="b2").colors.playing_background)
        self.assertEqual(dark.getRgb(), (201, 168, 106, 6))
        self.assertEqual(light.getRgb(), (152, 118, 46, 8))

    def test_helpers_render_and_keep_focus_and_disabled_geometry(self):
        messages = []
        previous = qInstallMessageHandler(lambda _kind, _ctx, text: messages.append(text))
        host = QWidget()
        try:
            host.resize(700, 320)
            for mode in ("dark", "light"):
                theme = get_theme(mode, profile="b2")
                for role in ("primary", "secondary", "ghost", "icon", "destructive"):
                    button = QPushButton("中文按钮", host)
                    button.setGeometry(10, 10, 200, 48)
                    button.setStyleSheet(button_qss(theme, role=role, selector="QPushButton"))
                    calls = []
                    button.clicked.connect(lambda: calls.append(True))
                    host.show(); button.show(); self.app.processEvents()
                    initial = button.geometry()
                    button.setProperty("hushKeyboardFocus", True)
                    button.setFocus(Qt.FocusReason.TabFocusReason)
                    button.style().unpolish(button); button.style().polish(button)
                    self.app.processEvents()
                    self.assertEqual(button.geometry(), initial)
                    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                    self.assertEqual(len(calls), 1)
                    button.setEnabled(False)
                    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(button.geometry(), initial)
                    self.assertFalse(button.grab().isNull())
                    button.hide(); button.deleteLater()
                editor = QLineEdit(host)
                editor.setStyleSheet(input_qss(theme)); editor.show()
                editor.setText("音乐库 中文 MiSans")
                self.assertFalse(editor.grab().isNull())
                editor.hide(); editor.deleteLater()
        finally:
            host.close(); host.deleteLater()
            qInstallMessageHandler(previous)
        self.assertFalse([m for m in messages if "stylesheet" in m.lower() or "unknown property" in m.lower()], messages)

    def test_surface_helper_does_not_change_geometry_or_child_style(self):
        surface = QWidget(); surface.setObjectName("surfaceProbe"); surface.resize(200, 100)
        child = QLineEdit("保留子控件", surface); child.setGeometry(5, 5, 180, 40)
        child.setStyleSheet("QLineEdit {color: #123456;}")
        before = child.geometry(), child.styleSheet()
        surface.setStyleSheet(surface_qss(get_theme("dark", profile="b2"), selector="QWidget#surfaceProbe"))
        surface.show(); self.app.processEvents()
        self.assertEqual((child.geometry(), child.styleSheet()), before)
        self.assertIn("#292925", divider_qss(get_theme("dark", profile="b2"), selector="QFrame#divider"))
        surface.close(); surface.deleteLater()

    def test_icon_roles_are_guidance_without_changing_existing_sizes(self):
        theme = get_theme("dark", profile="b2")
        for role in ("small", "normal", "playback", "primary_playback"):
            sizes = icon_sizing(theme, role)
            self.assertGreater(sizes.hit_area, sizes.visual_size)
        custom = replace(theme, metrics=replace(theme.metrics, icon_hit_area=48))
        self.assertEqual(icon_sizing(custom).hit_area, 48)
        self.assertEqual(icon_sizing(custom).visual_size, theme.metrics.icon_md)

    def test_real_library_surface_consumes_b2_without_migrating_page(self):
        from app.ui_v2.adapters.library_adapter import LibraryAdapter
        from app.ui_v2.pages.library_page import LibraryPage

        page = LibraryPage(LibraryAdapter([]), get_theme("dark"))
        try:
            page.resize(900, 600)
            page.show()
            for mode in ("dark", "light"):
                legacy = get_theme(mode)
                page.set_theme(legacy)
                self.app.processEvents()
                self.assertIs(page.theme, legacy)
                self.assertEqual(
                    page.view_host.palette().window().color(),
                    QColor(get_theme(mode, profile="b2").colors.content_background),
                )
                self.assertEqual(
                    page.palette().window().color(),
                    QColor(legacy.colors.content_background),
                )
        finally:
            page.close()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main()
