from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication

from app.startup_diagnostics import StartupDiagnostics
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.shell.desktop_lyrics_window import (
    DesktopLyricsWindow,
    clamp_desktop_lyrics_position,
    normalize_desktop_lyrics_font,
)
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES, get_theme


class StartupDiagnosticsTests(unittest.TestCase):
    def test_marks_identify_slowest_stage_and_write_failures_are_safe(self) -> None:
        diagnostics = StartupDiagnostics()
        diagnostics.mark("fast")
        time.sleep(0.002)
        diagnostics.mark("slow")
        self.assertEqual([item["name"] for item in diagnostics.marks], ["fast", "slow"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "startup-performance.log"
            self.assertTrue(diagnostics.write(directory))
            text = path.read_text(encoding="utf-8")
            self.assertIn("slowest_stage=slow", text)
        self.assertFalse(diagnostics.write(None))


class DesktopLyricsHelpersTests(unittest.TestCase):
    def test_font_normalization_only_allows_bundled_open_fonts(self) -> None:
        self.assertEqual(normalize_desktop_lyrics_font(OPEN_FONT_FAMILIES[1]), OPEN_FONT_FAMILIES[1])
        self.assertEqual(normalize_desktop_lyrics_font("Segoe UI"), OPEN_FONT_FAMILIES[0])

    def test_position_is_clamped_to_available_work_area(self) -> None:
        position = clamp_desktop_lyrics_position(
            QPoint(-20, 5000),
            QSize(300, 120),
            QRect(10, 20, 1000, 700),
        )
        self.assertEqual(position, QPoint(10, 600))


class DesktopLyricsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.playback = PlaybackAdapter(timer_enabled=False)
        self.lyrics = LyricsAdapter()
        self.window = DesktopLyricsWindow(
            self.playback,
            self.lyrics,
            get_theme("dark"),
        )

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_defaults_to_transparent_input_and_reuses_lyric_adapter(self) -> None:
        self.assertTrue(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )
        self.assertIs(self.window._lyrics_adapter, self.lyrics)
        self.window.apply_settings(
            {
                "floating_lyrics_font_family": "Segoe UI",
                "floating_lyrics_width": 600,
                "floating_lyrics_height": 140,
                "floating_lyrics_passthrough": False,
            }
        )
        self.assertEqual(self.window.width(), 600)
        self.assertEqual(self.window.height(), 140)
        self.assertEqual(
            self.window._settings["floating_lyrics_font_family"], OPEN_FONT_FAMILIES[0]
        )
        self.assertFalse(
            bool(self.window.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        )

    def test_reset_position_emits_only_a_position_update(self) -> None:
        changes: list[tuple[int, int]] = []
        self.window.position_changed.connect(lambda x, y: changes.append((x, y)))
        self.window.reset_position()
        self.assertEqual(len(changes), 1)
        self.assertGreaterEqual(changes[0][0], 0)
        self.assertGreaterEqual(changes[0][1], 0)


class DesktopLyricsMainWindowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_player_bar_exposes_desktop_lyrics_without_changing_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(settings_path=Path(directory) / "settings.json")
            try:
                self.assertEqual(window.navigation_adapter.route, "browse")
                self.assertEqual(window.player_bar.desktop_lyrics_button.toolTip(), "桌面歌词")
                window._on_player_bar_action("desktop_lyrics")
                self.app.processEvents()
                self.assertIsNotNone(window.desktop_lyrics_window)
                self.assertTrue(window.desktop_lyrics_window.isVisible())
                self.assertEqual(window.navigation_adapter.route, "browse")
            finally:
                window.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
