"""B2 immersive presentation contracts without replacing playback state."""
import os
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton
from app.ui_v2.adapters.legacy_settings_bridge import SettingsBridgeError
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme


class B2ImmersiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.window = MainWindow(data_mode='mock', settings_path=self.tmp.name+'/settings.json')
        self.window.resize(1080, 900)
        self.window.show()
        self.app.processEvents()
        self.playback = self.window.playback_adapter
        self.playback._timer_enabled = False
        self.tracks = [replace(t, is_missing=False, is_loading=False,
                               local_path=self.tmp.name+f'/{i}.wav', duration_ms=200000)
                       for i, t in enumerate(self.window.library_page.adapter.collection.tracks()[:5])]
        self.playback.set_queue(self.tracks)
        self.playback.play_track(self.tracks[0].id)
        self.window.navigation_adapter.set_route('immersive_lyrics')
        self.app.processEvents()
        self.page = self.window.router.currentWidget()
        self.playback.pause()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_compact_identity_and_panels_remain_inside_available_space(self):
        p = self.page
        p.set_cover_scale(130)
        for width, height in ((1080, 900), (1450, 900), (1920, 1080)):
            self.window.resize(width, height)
            self.app.processEvents()
            identity = p.identity
            for widget in (identity.cover, identity.title_label, identity.artist_label):
                origin = widget.mapTo(identity, QPoint())
                self.assertGreaterEqual(origin.x(), 0)
                self.assertGreaterEqual(origin.y(), 0)
                self.assertLessEqual(origin.x()+widget.width(), identity.width())
                self.assertLessEqual(origin.y()+widget.height(), identity.height(), (width, widget.objectName(), identity.sizeHint(), identity._group.sizeHint(), identity.maximumHeight()))
            p.show_settings_panel()
            panel = p.settings_panel
            self.app.processEvents()
            self.assertTrue(p.rect().contains(panel.geometry()))
            self.assertLess(panel.geometry().bottom(), p.controls.geometry().top())
            for button in (panel.reset_button,):
                self.assertTrue(panel.footer_widget.rect().contains(button.geometry()))
            p.hide_settings_panel()

    def test_slider_colors_and_b2_theme_are_valid_for_both_modes(self):
        for mode in ('dark', 'light'):
            self.page.set_theme_mode(mode)
            self.assertEqual(self.page._theme.colors, get_theme(mode, profile='b2').colors)
            for slider in (self.page.controls.progress_slider, self.page.controls.volume_slider):
                for name in ('_track_color', '_fill_color', '_handle_color', '_focus_color'):
                    self.assertTrue(getattr(slider, name).isValid(), name)
                self.assertEqual(slider._track_color.alpha(), 64)

    def test_loaded_setting_labels_match_values_without_creating_edits(self):
        panel = self.page.settings_panel
        self.page.show_settings_panel()
        dirty = panel.is_dirty
        self.page._sync_panel_from_options()
        for slider, label in panel._value_labels.items():
            self.assertEqual(label.text(), f"{slider.value()}{label.property('valueSuffix')}")
        self.assertEqual(panel.is_dirty, dirty)
        self.assertLess(panel.status_label.geometry().bottom(), panel.footer_widget.geometry().bottom())

    def test_settings_footer_has_no_save_or_close_buttons(self):
        self.page.show_settings_panel()
        panel = self.page.settings_panel
        for mode in ('dark', 'light'):
            self.page.set_theme_mode(mode)
            self.app.processEvents()
            buttons = panel.footer_widget.findChildren(QToolButton)
            self.assertFalse(any(button.text() in ('保存', '关闭') for button in buttons))
            self.assertEqual([button.text() for button in buttons if button.isVisible()], ['恢复默认'])
            self.assertTrue(panel.close_button.isVisible())
        panel.close_button.click()
        self.assertFalse(panel.isVisible())

    def test_settings_failed_autosave_can_retry_without_losing_draft(self):
        self.page.show_settings_panel()
        panel = self.page.settings_panel
        original = panel.global_lyric_scale_slider.value()
        with patch.object(self.page.settings_bridge, 'save_snapshot',
                          side_effect=SettingsBridgeError('Cannot save settings')):
            panel.global_lyric_scale_slider.setValue(original + 10)
            self.app.processEvents()
            self.assertTrue(panel.is_dirty)
            self.assertEqual(panel.status_label.property('status'), 'failed')
            retries = [button for button in panel.footer_widget.findChildren(QToolButton)
                       if button.text() == '重试' and button.isVisible()]
            self.assertEqual(len(retries), 1)
            self.assertTrue(retries[0].isEnabled())
            panel.close_button.click()
            self.assertTrue(panel.isVisible())
            self.page.hide_settings_panel()
            self.assertTrue(panel.isVisible())
            self.assertEqual(panel.global_lyric_scale_slider.value(), original + 10)
        retries[0].click()
        self.app.processEvents()
        self.assertFalse(panel.is_dirty)
        self.assertEqual(panel.status_label.text(), '已保存')
        self.assertFalse(retries[0].isVisible())
        saved = self.page.settings_bridge.read_snapshot().to_dict()
        self.assertEqual(saved['immersive_lyrics_font_scale'], original + 10)
        panel.close_button.click()
        self.assertFalse(panel.isVisible())

    def test_reset_auto_saves_and_header_close_only_closes_settings(self):
        from pathlib import Path
        p = self.page
        p.show_settings_panel()
        panel = p.settings_panel
        settings = Path(self.tmp.name)/'settings.json'
        before = settings.read_bytes() if settings.exists() else None
        panel.global_lyric_scale_slider.setValue(123)
        self.app.processEvents()
        panel.reset_button.click()
        self.app.processEvents()
        self.assertEqual(panel.global_lyric_scale_slider.value(), 100)
        self.assertNotEqual(settings.read_bytes() if settings.exists() else None, before)
        panel.close_button.click()
        self.assertFalse(panel.isVisible())
        self.assertNotEqual(settings.read_bytes() if settings.exists() else None, before)

    def test_queue_selection_does_not_play_and_enter_uses_existing_queue(self):
        p = self.page
        p.show_queue_panel()
        q = p.queue_panel
        original = self.playback.state.current_track.id
        index = q.view.model().index(1, 0)
        self.app.processEvents()
        QTest.mouseClick(q.view.viewport(), Qt.MouseButton.LeftButton,
                        pos=q.view.visualRect(index).center())
        selected = q.selected_track_id
        self.assertNotEqual(selected, original)
        self.assertEqual(self.playback.state.current_track.id, original)
        QTest.keyClick(q.view, Qt.Key.Key_Return)
        self.assertEqual(self.playback.state.current_track.id, selected)
        self.assertEqual(tuple(t.id for t in self.playback.queue_tracks), tuple(t.id for t in self.tracks))


if __name__ == '__main__':
    unittest.main()
