"""Reading-scene presentation must not replace playback or lyric state."""

import os
import tempfile
import unittest
from dataclasses import asdict, replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2


class ImmersiveConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.window = MainWindow(data_mode="mock", settings_path=self.tmp.name + "/settings.json")
        self.window.resize(1450, 900)
        self.window.show()
        playback = self.window.playback_adapter
        playback._timer_enabled = False
        track = replace(self.window.library_page.adapter.collection.tracks()[0],
                        is_missing=False, is_loading=False, duration_ms=200000,
                        local_path=self.tmp.name + "/fixture.wav")
        playback.set_queue([track])
        playback.play_track(track.id)
        playback.pause()
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        self.page = self.window.router.currentWidget()
        self.page.lyrics_adapter.load_mock_scenario("translation")
        playback.seek(12000)
        self.page.canvas.set_reduce_motion(True)
        self.app.processEvents()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_reading_stage_leaves_space_and_keeps_controls_reachable(self):
        p = self.page
        for width, height in ((1080, 900), (1450, 900), (1920, 1080)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertLessEqual(p.canvas.height(), p.content.height() - 64)
            self.assertGreater(p.canvas.y(), 30)
            self.assertGreater(p.canvas.width(), 480)
            self.assertGreaterEqual(p.controls.y(), p.content_stack.geometry().bottom())
            for control in (p.controls.play_button, p.controls.volume_slider, p.controls.more_button):
                origin = control.mapTo(p, QPoint())
                self.assertTrue(p.rect().contains(origin))
                self.assertTrue(p.rect().contains(origin + QPoint(control.width()-1, control.height()-1)))

    def test_scene_switch_preserves_settings_queue_and_slider_hit_area(self):
        p = self.page
        options = asdict(p.options)
        queue = self.window.playback_adapter.queue_tracks
        slider = p.controls.progress_slider
        height = slider.height()
        self.assertEqual(slider._track_height, 2.0)
        p.set_mode("now_playing")
        self.app.processEvents()
        self.assertEqual(slider._track_height, 4.0)
        self.assertFalse(p.background._reading_scene)
        p.set_mode("lyrics")
        self.app.processEvents()
        self.assertGreaterEqual(slider.height(), height)
        self.assertEqual(slider._track_height, 2.0)
        self.assertEqual(asdict(p.options), options)
        self.assertEqual(self.window.playback_adapter.queue_tracks, queue)

    def test_tall_window_expands_reading_area_without_covering_controls(self):
        p = self.page
        for mode in ("dark", "light"):
            self.window.set_theme(mode)
            for width, height in ((1450, 1080), (1920, 1080), (2560, 1440)):
                with self.subTest(theme=mode, size=(width, height)):
                    self.window.resize(width, height)
                    self.app.processEvents()
                    self.assertGreaterEqual(p.canvas.height(), p.content.height() * 0.9)
                    self.assertGreaterEqual(p.canvas.y(), 32)
                    self.assertLessEqual(p.canvas.geometry().bottom(), p.content.height() - 32)
                    bottom = p.canvas.mapTo(p, QPoint(0, p.canvas.height())).y()
                    self.assertLess(bottom, p.controls.y())
                    if height == 1440:
                        p.canvas.repaint()
                        complete_rows = sum(p.canvas.rect().contains(rect)
                                            for rect in p.canvas._line_rects.values())
                        self.assertEqual(complete_rows, 9)

    def test_resize_shows_more_rows_and_restores_small_window(self):
        p = self.page
        playback = self.window.playback_adapter
        state = (playback.state.current_track.id, playback.state.position_ms,
                 playback.state.is_playing, tuple(playback.queue_tracks), asdict(p.options))
        self.window.resize(1200, 800)
        self.app.processEvents()
        p.canvas.repaint()
        small_height = p.canvas.height()
        self.assertEqual(small_height, 384)
        small_rows = sum(p.canvas.rect().contains(rect)
                         for rect in p.canvas._line_rects.values())
        small_geometry = (p.canvas.y(), p.controls.geometry())
        self.window.resize(1920, 1080)
        self.app.processEvents()
        p.canvas.repaint()
        large_rows = sum(p.canvas.rect().contains(rect)
                         for rect in p.canvas._line_rects.values())
        self.assertGreater(large_rows, small_rows)
        self.window.resize(1200, 800)
        self.app.processEvents()
        self.assertEqual(p.canvas.height(), small_height)
        self.assertEqual((p.canvas.y(), p.controls.geometry()), small_geometry)
        self.assertEqual((playback.state.current_track.id, playback.state.position_ms,
                          playback.state.is_playing, tuple(playback.queue_tracks),
                          asdict(p.options)), state)

    def test_paint_profile_preserves_manual_browsing_and_seek_state(self):
        c = self.page.canvas
        c.wheelEvent(QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(),
                                QPoint(0, -120), Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
        self.assertTrue(c.browsing)
        state = (c.current_index, c._browse_anchor, c._browse_offset,
                 self.window.playback_adapter.state.position_ms)
        c.set_immersive_reading_style(False)
        c.set_immersive_reading_style(True)
        self.assertEqual(state, (c.current_index, c._browse_anchor, c._browse_offset,
                                self.window.playback_adapter.state.position_ms))
        c.return_to_current()
        self.assertFalse(c.browsing)

    def test_context_profile_is_opt_in_and_ordinary_lyrics_stay_identical(self):
        c = LyricsCanvasV2(get_theme("dark"))
        c.set_mode("ordinary")
        baseline = (c.effective_font_sizes, c.inactive_alpha_for_distance(1))
        c.set_immersive_reading_style(True)
        self.assertEqual(baseline, (c.effective_font_sizes, c.inactive_alpha_for_distance(1)))
        c.set_mode("immersive")
        self.assertLess(c.inactive_alpha_for_distance(1), 150)
        self.assertLess(c.inactive_alpha_for_distance(2), c.inactive_alpha_for_distance(1))
        self.assertEqual(c.active_text_alpha, 255)
        c.deleteLater()


if __name__ == "__main__":
    unittest.main()
