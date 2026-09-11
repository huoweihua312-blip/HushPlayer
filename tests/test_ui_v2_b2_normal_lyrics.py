"""Normal lyrics B2 opt-in, action routing and readable layout contracts."""
import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt, QPoint, QPointF, QAbstractAnimation
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.lyrics_page import LyricsPage
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2


class B2NormalLyricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.adapter = LyricsAdapter()
        self.adapter.set_track(next(t for t in create_mock_tracks(20) if not t.is_missing))
        self.page = LyricsPage(self.adapter, get_theme('dark'))
        self.page.resize(1230, 740)
        self.page.show()
        self.app.processEvents()

    def tearDown(self):
        self.page.hide()
        self.page.deleteLater()
        self.app.processEvents()

    def test_theme_is_scoped_and_switch_does_not_replace_document_or_canvas(self):
        p = self.page
        canvas, document = p.canvas, self.adapter.document
        shared = LyricsCanvasV2(get_theme('dark'))
        original = shared.return_button.styleSheet()
        for mode in ('light', 'dark'):
            p.set_theme(get_theme(mode))
            self.assertEqual(p._theme.colors, get_theme(mode, profile='b2').colors)
            self.assertIs(p.canvas, canvas)
            self.assertIs(p.canvas.document, document)
            self.assertEqual(shared.return_button.styleSheet(), original)
        shared.deleteLater()

    def test_reading_width_and_toolbar_fit_without_scaling_or_rebuilding(self):
        p = self.page
        for width in (1230, 1004, 824):
            p.resize(width, 740)
            self.app.processEvents()
            self.assertLessEqual(p.canvas.width(), 820)
            self.assertLessEqual(p.canvas.width(), p.width())
            self.assertGreater(p.canvas.effective_font_sizes[0], p.canvas.effective_font_sizes[1])
            for button in (p.toolbar.translation_button, p.toolbar.more_button, p.toolbar.immersive_button):
                self.assertTrue(p.toolbar.rect().contains(button.geometry()))

    def test_existing_actions_and_manual_return_remain_live(self):
        p = self.page
        self.adapter.load_mock_scenario('translation')
        before = self.adapter.display_options['translation']
        QTest.mouseClick(p.toolbar.translation_button, Qt.MouseButton.LeftButton)
        self.assertNotEqual(before, self.adapter.display_options['translation'])
        immersive, source = [], []
        p.immersive_requested.connect(lambda: immersive.append(True))
        p.source_requested.connect(lambda: source.append(True))
        QTest.mouseClick(p.toolbar.immersive_button, Qt.MouseButton.LeftButton)
        self.assertEqual(immersive, [True])
        p.canvas.wheelEvent(QWheelEvent(QPointF(200,200), QPointF(200,200), QPoint(), QPoint(0,-120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False))
        self.assertTrue(p.canvas.return_button.isVisible())
        p.toolbar.more_menu.actions()[0].trigger()
        self.assertFalse(p.canvas.return_button.isVisible())
        self.adapter.load_mock_scenario('failed')
        QTest.mouseClick(p.state_view.source_button, Qt.MouseButton.LeftButton)
        self.assertEqual(source, [True])
        self.adapter.retry()
        self.assertEqual(self.adapter.state.phase, 'failed')

    def test_long_current_line_and_mouse_seek_at_both_widths(self):
        p = self.page
        for width in (1230, 1004):
            p.resize(width, 740)
            self.adapter.load_mock_scenario('long_song')
            self.adapter.set_position(28800)
            self.app.processEvents()
            p.canvas.repaint()
            line = self.adapter.active_line
            rect = p.canvas._line_rects[line.id]
            self.assertGreater(rect.height(), p.canvas.effective_font_sizes[0])
            self.assertTrue(p.canvas.rect().contains(rect.center()))
            seeks = []
            self.adapter.seek_requested.connect(seeks.append)
            QTest.mouseClick(p.canvas, Qt.MouseButton.LeftButton, pos=rect.center())
            self.assertEqual(seeks[-1], line.start_ms)

    def test_state_visibility_and_reduce_motion(self):
        p = self.page
        for state in ('loading', 'empty', 'failed', 'instrumental'):
            self.adapter.load_mock_scenario(state)
            self.assertIs(p.content_stack.currentWidget(), p.state_view)
            self.assertEqual(p.state_view.retry_button.isVisible(), state in ('empty', 'failed'))
        self.adapter.set_playback_status('unavailable')
        self.assertEqual(self.adapter.state.phase, 'playback_unavailable')
        self.assertIs(p.content_stack.currentWidget(), p.state_view)
        self.adapter.load_mock_scenario('translation')
        p.canvas.set_reduce_motion(True)
        self.adapter.set_position(12000)
        self.assertEqual(p.canvas._active_line, self.adapter.active_line)
        self.assertEqual(p.canvas._line_transition.state(), QAbstractAnimation.State.Stopped)


if __name__ == '__main__':
    unittest.main()
