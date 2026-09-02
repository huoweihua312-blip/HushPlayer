from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.experiments.immersive_lyrics_preview import ImmersiveLyricsPreview
from app.ui_v2.shell.player_bar import PlayerBar
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.immersive_controls import ImmersiveControls
from app.ui_v2.widgets.immersive_settings_panel import ImmersiveSettingsPanel
from app.ui_v2.widgets.lyrics_quick_settings_drawer import LyricsQuickSettingsContent
from app.ui_v2.widgets.lyrics_timeline import LyricsTimeline
from app.ui_v2.widgets.settings_control_factory import SettingsControlFactory


class SliderSurfaceStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_all_slider_surfaces_are_transparent_but_keep_their_tracks(self) -> None:
        theme = get_theme("dark")
        self.assertIn("QSlider", build_stylesheet(theme))
        self.assertIn("background: transparent", build_stylesheet(theme))

        playback = PlaybackAdapter(timer_enabled=False)
        player_bar = PlayerBar(playback, theme)
        controls = ImmersiveControls(theme)
        settings_panel = ImmersiveSettingsPanel(theme)
        timeline = LyricsTimeline(theme)
        slider_control = SettingsControlFactory.slider_spin(0, 100, 50, "%", theme)
        quick_settings = LyricsQuickSettingsContent(theme)
        preview = ImmersiveLyricsPreview()
        try:
            direct_styles = (
                controls.progress_slider.styleSheet(),
                controls.volume_slider.styleSheet(),
                timeline.styleSheet(),
                slider_control.slider.styleSheet(),
            )
            for style in direct_styles:
                self.assertIn("QSlider", style)
                self.assertIn("background: transparent", style)
                self.assertIn("border: 0", style)
                self.assertIn("groove:horizontal", style)
                self.assertIn("background: transparent", style.split("groove:horizontal", 1)[1])

            self.assertIn("QSlider", settings_panel.styleSheet())
            self.assertIn("background: transparent", settings_panel.styleSheet())
            self.assertIn("groove:horizontal", settings_panel.styleSheet())
            self.assertIn("background: transparent", settings_panel.styleSheet().split("groove:horizontal", 1)[1])
            quick_slider_styles = [
                control.slider.styleSheet()
                for control in quick_settings.controls.values()
                if hasattr(control, "slider")
            ]
            self.assertTrue(quick_slider_styles)
            for style in quick_slider_styles:
                self.assertIn("QSlider", style)
                self.assertIn("background: transparent", style)
            self.assertIn("QSlider#playerProgress", player_bar.styleSheet())
            self.assertIn("background: transparent", player_bar.styleSheet())
            self.assertIn("groove:horizontal", player_bar.styleSheet())
            self.assertIn("border: 0", player_bar.styleSheet())
            self.assertIn("QSlider", preview.controls.styleSheet())
            self.assertIn("background: transparent", preview.controls.styleSheet())
            self.assertIn("border: 0", preview.controls.styleSheet())
            self.assertIn("QSlider", preview.settings_panel.styleSheet())
            self.assertIn("background: transparent", preview.settings_panel.styleSheet())
            self.assertIn("border: 0", preview.settings_panel.styleSheet())
        finally:
            preview.close()
            preview.deleteLater()
            for widget in (
                player_bar,
                controls,
                settings_panel,
                timeline,
                slider_control,
                quick_settings,
            ):
                widget.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
