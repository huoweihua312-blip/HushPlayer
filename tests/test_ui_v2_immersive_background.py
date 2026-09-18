"""Real image rendering and transactional transparent lyric colors."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.legacy_settings_bridge import load_settings_document
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.artwork_atmosphere import ArtworkAtmosphere
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from tests import test_ui_v2_immersive_convergence as convergence
from tests.test_ui_v2_q5b1_real_interactions import _remote_track


class ArtworkBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.background = ArtworkAtmosphere(get_theme("light"))
        self.background.resize(640, 360)
        self.background.set_reading_scene(True)
        self.background.set_opacity(100)
        self.background.set_overlay_strength(15)
        self.background.set_blur(0)
        self.background.set_transparency(0)

    def tearDown(self):
        self.background.hide()
        self.background.deleteLater()
        self.app.processEvents()

    def test_same_track_with_different_cover_changes_artwork_not_gradient(self):
        for mode in ("dark", "light"):
            self.background.set_theme(get_theme(mode))
            frames = {}
            for background_mode in ("artwork", "gradient"):
                self.background.set_mode(background_mode)
                frames[background_mode] = []
                for color in ("#e82020", "#2040e8"):
                    self.background.set_track(_remote_track("same", QColor(color)))
                    frames[background_mode].append(self.background.grab().toImage())
            self.assertNotEqual(*frames["artwork"], mode)
            self.assertEqual(*frames["gradient"], mode)

    def test_local_cover_pixels_are_used_and_image_opacity_is_respected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cover.png"
            image = QImage(80, 80, QImage.Format.Format_RGB32)
            image.fill(QColor("#e82020"))
            self.assertTrue(image.save(str(path)))
            track = replace(_remote_track("local", QColor("blue")),
                            artwork_data=b"", artwork_path=str(path))
            self.background.set_track(track)
            frame = self.background.grab().toImage()
            color = frame.pixelColor(320, 180)
            self.assertGreater(color.red(), color.blue() + 80)
            self.background.set_opacity(0)
            self.assertNotEqual(frame, self.background.grab().toImage())

    def test_missing_or_corrupt_cover_does_not_retain_previous_image(self):
        self.background.set_track(_remote_track("fallback", QColor("red")))
        before = self.background.grab().toImage()
        self.background.set_track(replace(_remote_track("fallback", QColor("red")),
                                          artwork_data=b"invalid", artwork_path=None))
        fallback = self.background.grab().toImage()
        self.assertNotEqual(before, fallback)
        self.assertFalse(fallback.isNull())
        missing = replace(_remote_track("fallback", QColor("red")),
                          artwork_data=b"", artwork_path=None)
        self.background.set_track(missing)
        self.assertEqual(fallback, self.background.grab().toImage())
        invalid = replace(missing, artwork_path="missing-cover.png")
        self.background.set_track(invalid)
        self.assertEqual(fallback, self.background.grab().toImage())
        self.assertFalse(artwork_pixmap_for_track(invalid, 80, 80).isNull())
        self.background.set_track(None)
        self.assertFalse(self.background.grab().isNull())

    def test_blur_changes_image_detail_and_resizing_keeps_cover_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pattern.png"
            image = QImage(80, 80, QImage.Format.Format_RGB32)
            for y in range(80):
                for x in range(80):
                    image.setPixelColor(x, y, QColor("red" if (x // 4 + y // 4) % 2 else "blue"))
            self.assertTrue(image.save(str(path)))
            self.background.set_track(replace(_remote_track("pattern", QColor("red")),
                                              artwork_data=b"", artwork_path=str(path)))
            sharp = self.background.grab().toImage()
            self.background.set_blur(80)
            self.assertNotEqual(sharp, self.background.grab().toImage())
            generation = self.background.generation
            self.background.resize(900, 600)
            self.background.grab()
            self.assertEqual(self.background.generation, generation)

    def test_cover_veil_keeps_default_theme_text_readable_on_extreme_covers(self):
        self.background.set_overlay_strength(45)
        self.background.set_transparency(38)
        for theme, color in (("light", "black"), ("dark", "white")):
            self.background.set_theme(get_theme(theme))
            self.background.set_track(_remote_track("contrast", QColor(color)))
            background = self.background.grab().toImage().pixelColor(320, 180)
            if theme == "light":
                self.assertGreater(background.lightness(), 140)
            else:
                self.assertLess(background.lightness(), 110)

    def test_cover_background_retains_transparency_and_overlay_controls(self):
        self.background.set_track(_remote_track("controls", QColor("red")))
        self.background.set_overlay_strength(60)
        opaque = self.background.grab().toImage()
        self.background.set_transparency(100)
        transparent = self.background.grab().toImage()
        self.assertNotEqual(opaque, transparent)
        self.background.set_overlay_strength(15)
        self.assertNotEqual(transparent, self.background.grab().toImage())


class TransparentLyricsColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        convergence.ImmersiveConvergenceTests.setUpClass()

    def setUp(self):
        self.case = convergence.ImmersiveConvergenceTests()
        self.case.setUp()
        self.page = self.case.page
        self.page.show_settings_panel()
        self.panel = self.page.settings_panel

    def tearDown(self):
        self.case.tearDown()

    def choose(self, control, value):
        index = control.findData(value)
        self.assertGreaterEqual(index, 0, value)
        control.setCurrentIndex(index)
        self.case.app.processEvents()

    def color_control(self):
        self.assertTrue(hasattr(self.panel, "transparent_lyrics_color_combo"))
        return self.panel.transparent_lyrics_color_combo

    def test_transparent_text_color_previews_without_changing_page_theme(self):
        self.choose(self.panel.theme_combo, "light")
        self.choose(self.panel.background_combo, "transparent")
        playback = self.case.window.playback_adapter
        state = (playback.state.current_track.id, playback.state.position_ms,
                 playback.state.is_playing, tuple(playback.queue_tracks))
        self.choose(self.color_control(), "light")
        self.assertEqual(self.page._theme.mode, "light")
        self.assertGreater(QColor(self.page.canvas._theme.colors.primary_text).lightness(), 220)
        self.choose(self.color_control(), "dark")
        self.assertLess(QColor(self.page.canvas._theme.colors.primary_text).lightness(), 60)
        self.choose(self.color_control(), "theme")
        self.assertEqual(self.page.canvas._theme.mode, "light")
        self.choose(self.color_control(), "light")
        self.choose(self.panel.background_combo, "artwork")
        self.assertEqual(self.page.canvas._theme.mode, "light")
        self.choose(self.panel.background_combo, "transparent")
        self.assertEqual(self.page.canvas._theme.mode, "dark")
        self.assertTrue(self.color_control().isEnabled())
        self.assertEqual(state, (playback.state.current_track.id, playback.state.position_ms,
                                 playback.state.is_playing, tuple(playback.queue_tracks)))

    def test_color_save_reload_and_cancel_preserve_unknown_settings(self):
        path = Path(self.case.tmp.name) / "settings.json"
        document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        document["unrelated_setting"] = {"keep": 17}
        path.write_text(json.dumps(document), encoding="utf-8")
        self.page.hide_settings_panel()
        self.page.show_settings_panel()
        self.choose(self.panel.background_combo, "transparent")
        self.choose(self.color_control(), "light")
        self.panel.save_button.click()
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["immersive_transparent_lyrics_color"], "light")
        self.assertEqual(saved["unrelated_setting"], {"keep": 17})
        self.choose(self.color_control(), "dark")
        self.panel.cancel_button.click()
        self.assertEqual(self.page.canvas._theme.mode, "dark")
        from app.ui_v2.shell.main_window import MainWindow
        reopened = MainWindow(data_mode="mock", settings_path=path)
        try:
            self.assertEqual(reopened.immersive_lyrics_options.transparent_lyrics_color, "light")
        finally:
            reopened.hide()
            reopened.deleteLater()
            self.case.app.processEvents()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)
        self.case.window._apply_settings_values(load_settings_document(path))
        self.page.apply_options(self.case.window.immersive_lyrics_options)
        self.page.show_settings_panel()
        self.assertEqual(self.color_control().currentData(), "light")
        self.assertEqual(self.page.canvas._theme.mode, "dark")

    def test_current_cover_update_reaches_background_without_resetting_playback(self):
        playback = self.case.window.playback_adapter
        track = playback.state.current_track
        frames = []
        position = playback.state.position_ms
        for color in ("red", "blue"):
            artwork = _remote_track("art", QColor(color)).artwork_data
            playback.update_track(replace(track, artwork_data=artwork))
            self.case.app.processEvents()
            frames.append(self.page.background.grab().toImage())
        self.assertNotEqual(*frames)
        self.assertEqual(playback.state.position_ms, position)


class TransparentColorCompatibilityTests(unittest.TestCase):
    def test_old_and_invalid_settings_follow_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for value in ({}, {"immersive_transparent_lyrics_color": "invalid"}):
                path.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(load_settings_document(path).get(
                    "immersive_transparent_lyrics_color"), "theme")
