from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.pages.immersive_lyrics_page import ImmersiveLyricsPage
from app.ui_v2.shell.immersive_player_shell import ImmersivePlayerShell
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.widgets.lyrics_quick_settings_panel import LyricsQuickSettingsFloatingPanel


class UiV2Q4ImmersiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.tempdir.name) / "settings.json"
        self.window = MainWindow(settings_path=self.settings_path)
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.tempdir.cleanup()

    def _play_track(self) -> None:
        model = self.window.library_page.track_table.model
        index = next(
            model.index(row, int(TrackColumn.TITLE))
            for row, track in enumerate(model.tracks())
            if not track.is_missing and track.duration_ms is not None
        )
        self.window.library_page.track_table.doubleClicked.emit(index)
        self.app.processEvents()

    def _shell(self, route: str = "immersive_now_playing") -> ImmersivePlayerShell:
        self.window.navigation_adapter.set_route(route)
        self.app.processEvents()
        page = self.window.router.currentWidget()
        self.assertIsInstance(page, ImmersivePlayerShell)
        return page

    def test_one_host_shares_playback_and_has_independent_queue_lyrics_entries(self) -> None:
        shell = self._shell()
        self.assertIsInstance(shell, ImmersiveLyricsPage)
        self.assertIs(shell.playback_adapter, self.window.playback_adapter)
        self.assertIs(shell.queue_panel.playback, self.window.playback_adapter)
        self.assertIs(shell.controls.parentWidget(), shell)
        control_id = id(shell.controls)
        shell.header_lyrics.click()
        self.app.processEvents()
        self.assertEqual(shell.mode, "lyrics")
        shell.controls.queue_button.click()
        self.app.processEvents()
        self.assertEqual(shell.mode, "now_playing")
        self.assertTrue(shell.queue_panel.isVisible())
        self.assertEqual(id(shell.controls), control_id)
        shell.controls.lyrics_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "immersive_lyrics")
        self.assertFalse(shell.queue_panel.isVisible())

    def test_floating_panels_do_not_change_content_geometry(self) -> None:
        shell = self._shell()
        for width, height in ((1600, 900), (1200, 800), (900, 600)):
            self.window.resize(width, height)
            self.app.processEvents()
            before = shell.content_stack.geometry()
            shell.show_queue_panel()
            self.app.processEvents()
            self.assertEqual(shell.content_stack.geometry(), before)
            self.assertIs(shell.queue_panel.parentWidget(), shell.overlay_host)
            self.assertGreaterEqual(shell.queue_panel.width(), 310)
            self.assertLessEqual(shell.queue_panel.width(), 410)
            shell.hide_queue_panel()
            shell.show_settings_panel()
            self.app.processEvents()
            self.assertEqual(shell.content_stack.geometry(), before)
            self.assertIs(shell.settings_panel.parentWidget(), shell.overlay_host)
            self.assertFalse(shell.queue_panel.isVisible())
            shell.hide_settings_panel()

    def test_quick_settings_preview_cancel_and_save_use_existing_settings_path(self) -> None:
        shell = self._shell("immersive_lyrics")
        shell.show_settings_panel()
        self.app.processEvents()
        panel = shell.settings_panel
        self.assertIsInstance(panel, LyricsQuickSettingsFloatingPanel)
        self.assertIsNotNone(panel.session)
        original = panel.global_lyric_scale_slider.value()
        panel.global_lyric_scale_slider.setValue(original + 1)
        self.app.processEvents()
        self.assertTrue(panel.is_dirty)
        self.assertIn("未保存", panel.status_label.text())
        self.assertEqual(
            self.window.immersive_lyrics_options.global_font_scale,
            original + 1,
        )
        panel.cancel_button.click()
        self.app.processEvents()
        self.assertFalse(panel.isVisible())
        self.assertFalse(self.settings_path.exists())
        shell.show_settings_panel()
        self.app.processEvents()
        panel.global_lyric_scale_slider.setValue(original + 2)
        panel.save_button.click()
        self.app.processEvents()
        self.assertTrue(panel.isVisible())
        self.assertFalse(panel.is_dirty)
        self.assertEqual(panel.status_label.text(), "已保存")
        document = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(document["immersive_lyrics_font_scale"], original + 2)

    def test_queue_projection_excludes_current_duplicate_and_plays_next_item(self) -> None:
        self._play_track()
        shell = self._shell()
        shell.show_queue_panel()
        self.app.processEvents()
        current_id = self.window.playback_adapter.state.current_track.id
        self.assertTrue(shell.queue_panel.current_row.isVisible())
        self.assertTrue(all(
            shell.queue_panel.list_widget.item(row).data(256).id != current_id
            for row in range(shell.queue_panel.list_widget.count())
        ))
        item = shell.queue_panel.list_widget.item(0)
        target = item.data(256)
        shell.queue_panel.list_widget.itemDoubleClicked.emit(item)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, target.id)

    def test_shutdown_stops_owned_controls_timer_and_hides_panels(self) -> None:
        shell = self._shell()
        shell.show_queue_panel()
        shell.show_settings_panel()
        shell._controls_hide_timer.start()
        shell.shutdown()
        self.assertFalse(shell._controls_hide_timer.isActive())
        self.assertFalse(shell.queue_panel.isVisible())
        self.assertFalse(shell.settings_panel.isVisible())

    def test_overlay_child_buttons_receive_real_mouse_events(self) -> None:
        shell = self._shell()
        shell.show_queue_panel()
        self.app.processEvents()
        QTest.mouseClick(shell.queue_panel.close_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(shell.queue_panel.isVisible())
        shell.show_settings_panel()
        self.app.processEvents()
        QTest.mouseClick(shell.settings_panel.cancel_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(shell.settings_panel.isVisible())


if __name__ == "__main__":
    unittest.main()
