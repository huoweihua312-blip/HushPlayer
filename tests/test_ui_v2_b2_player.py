"""PlayerBar presentation keeps the existing adapter and input contracts."""
import os
import unittest
from dataclasses import replace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.shell.player_bar import PlayerBar
from app.ui_v2.theme.tokens import get_theme


class B2PlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.adapter = PlaybackAdapter(timer_enabled=False)
        self.tracks = [t for t in create_mock_tracks(40) if not t.is_missing and t.duration_ms][:4]
        self.adapter.set_queue(self.tracks)
        self.bar = PlayerBar(self.adapter, get_theme('dark'))
        self.bar.resize(1080, 102)
        self.bar.show()
        self.app.processEvents()

    def tearDown(self):
        self.bar.close()
        self.bar.deleteLater()
        self.app.processEvents()

    def test_favorite_does_not_open_identity_or_move_transport(self):
        self.adapter.play_track(self.tracks[0].id)
        opened = []
        self.bar.track_open_requested.connect(lambda: opened.append(True))
        before = self.bar.play_button.geometry()
        favorite = self.adapter.state.is_favorite
        QTest.mouseClick(self.bar.favorite_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.adapter.state.is_favorite, not favorite)
        self.assertFalse(opened)
        self.assertEqual(before, self.bar.play_button.geometry())
        QTest.mouseClick(self.bar.artwork, Qt.MouseButton.LeftButton)
        self.assertEqual(opened, [True])

    def test_playback_and_auxiliary_buttons_keep_their_actions(self):
        b, a = self.bar, self.adapter
        a.play_track(self.tracks[0].id)
        b.play_button.click()
        self.assertFalse(a.state.is_playing)
        self.assertEqual(b.play_button.icon_name, 'play')
        b.play_button.click()
        self.assertTrue(a.state.is_playing)
        b.next_button.click()
        self.assertEqual(a.state.current_track.id, self.tracks[1].id)
        b.previous_button.click()
        self.assertEqual(a.state.current_track.id, self.tracks[0].id)
        b.shuffle_button.click()
        self.assertEqual(b.shuffle_button.active, a.state.shuffle_enabled)
        mode = a.state.repeat_mode
        b.repeat_button.click()
        self.assertNotEqual(mode, a.state.repeat_mode)
        actions = []
        b.mock_action_requested.connect(actions.append)
        for button in (b.queue_button, b.lyrics_button, b.desktop_lyrics_button):
            button.click()
        self.assertEqual(actions, ['queue', 'lyrics', 'desktop_lyrics'])

    def test_seeking_and_volume_state_synchronization(self):
        b, a = self.bar, self.adapter
        a.play_track(self.tracks[0].id)
        b.progress_slider.sliderPressed.emit()
        b.progress_slider.setValue(10000)
        b.progress_slider.sliderMoved.emit(10000)
        a.seek(5000)
        self.assertEqual(b.progress_slider.value(), 10000)
        b.progress_slider.sliderReleased.emit()
        self.assertEqual(a.state.position_ms, 10000)
        b.volume_slider.setValue(37)
        self.assertEqual(a.state.volume, 37)
        b.volume_button.click()
        self.assertTrue(a.state.is_muted)
        self.assertEqual(b.volume_button.icon_name, 'volume_mute')
        b.volume_button.click()
        self.assertFalse(a.state.is_muted)

    def test_long_identity_keeps_controls_inside_bar(self):
        b = self.bar
        b._on_track_changed(replace(self.tracks[0], title='Long track title ' * 30))
        for width in (1450, 1080, 900):
            b.set_compact(width < 1100)
            b.resize(width, 102)
            for _ in range(3):
                self.app.processEvents()
            for button in b._buttons:
                if button.isVisible():
                    origin = button.mapTo(b, QPoint())
                    self.assertGreaterEqual(origin.x(), 0)
                    self.assertLessEqual(origin.x() + button.width(), width)
            center = b.play_button.mapTo(b, b.play_button.rect().center()).x()
            self.assertLessEqual(abs(center - b.rect().center().x()), 2)

    def test_theme_keeps_geometry_and_disabled_controls(self):
        b = self.bar
        for mode in ('dark', 'light'):
            b.set_theme(get_theme(mode))
            self.assertFalse(b.play_button.isEnabled())
            self.assertFalse(b.progress_slider.isEnabled())
            self.assertEqual(b.height(), 102)
            self.assertEqual(b.artwork.width(), 56)
            self.assertIs(b._theme, get_theme(mode, profile='b2'))
        self.adapter.play_track(self.tracks[0].id)
        b.progress_slider.setFocus(Qt.FocusReason.TabFocusReason)
        self.app.processEvents()
        self.assertTrue(b.progress_slider.hasFocus())
        b.set_read_only(True)
        self.assertFalse(b.play_button.isEnabled())
