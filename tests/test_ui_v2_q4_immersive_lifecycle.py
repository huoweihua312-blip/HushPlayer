from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.shell.immersive_player_shell import ImmersivePlayerShell
from app.ui_v2.shell.main_window import MainWindow


class UiV2Q4ImmersiveLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.window = MainWindow(settings_path=Path(self.tempdir.name) / "settings.json")
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.tempdir.cleanup()

    def _shell(self) -> ImmersivePlayerShell:
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        shell = self.window.router.currentWidget()
        self.assertIsInstance(shell, ImmersivePlayerShell)
        return shell

    def _track_ids(self) -> tuple[str, str]:
        tracks = [
            track
            for track in self.window.library_page.track_table.model.tracks()
            if not track.is_missing and track.duration_ms is not None
        ]
        return tracks[0].id, tracks[1].id

    def test_enter_exit_immersive_100_cycles(self) -> None:
        for _ in range(100):
            self.window.navigation_adapter.set_route("immersive_lyrics")
            self.app.processEvents()
            self.window.navigation_adapter.set_route("browse")
            self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "browse")

    def test_now_playing_lyrics_100_cycles_reuses_core_widgets(self) -> None:
        shell = self._shell()
        core_ids = (id(shell.canvas), id(shell.controls), id(shell.queue_panel), id(shell.settings_panel))
        for _ in range(100):
            shell.set_mode("now_playing")
            shell.set_mode("lyrics")
            self.app.processEvents()
        self.assertEqual(core_ids, (id(shell.canvas), id(shell.controls), id(shell.queue_panel), id(shell.settings_panel)))

    def test_queue_open_close_100_cycles(self) -> None:
        shell = self._shell()
        for _ in range(100):
            shell.show_queue_panel()
            self.app.processEvents()
            shell.hide_queue_panel()
        self.assertFalse(shell.queue_panel.isVisible())

    def test_quick_settings_open_cancel_100_cycles(self) -> None:
        shell = self._shell()
        for _ in range(100):
            shell.show_settings_panel()
            self.app.processEvents()
            shell.settings_panel.cancel_button.click()
            self.app.processEvents()
        self.assertFalse(shell.settings_panel.isVisible())

    def test_resize_1600_1200_900_50_cycles_without_panel_rebuild(self) -> None:
        shell = self._shell()
        ids = (id(shell.queue_panel), id(shell.settings_panel), id(shell.canvas))
        for _ in range(50):
            for width, height in ((1600, 900), (1200, 800), (900, 600), (1600, 900)):
                self.window.resize(width, height)
                self.app.processEvents()
        self.assertEqual(ids, (id(shell.queue_panel), id(shell.settings_panel), id(shell.canvas)))

    def test_short_long_short_track_transition_100_cycles(self) -> None:
        first, second = self._track_ids()
        shell = self._shell()
        for _ in range(100):
            self.window.playback_adapter.play_track(first)
            self.window.playback_adapter.play_track(second)
            self.window.playback_adapter.play_track(first)
            self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, first)
        self.assertEqual(
            shell.now_playing_page.title_label.toolTip(),
            self.window.playback_adapter.state.current_track.title,
        )

    def test_application_shutdown_with_panels_open_20_cycles(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        for _ in range(20):
            window = MainWindow(settings_path=Path(self.tempdir.name) / "shutdown.json")
            window.playback_adapter._timer_enabled = False
            window.resize(900, 600)
            window.show()
            self.app.processEvents()
            window.navigation_adapter.set_route("immersive_lyrics")
            self.app.processEvents()
            shell = window.router.currentWidget()
            shell.show_queue_panel()
            shell.show_settings_panel()
            self.app.processEvents()
            window.close()
            window.deleteLater()
            self.app.processEvents()
        self.window = MainWindow(settings_path=Path(self.tempdir.name) / "final.json")
        self.window.playback_adapter._timer_enabled = False
        self.window.show()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
