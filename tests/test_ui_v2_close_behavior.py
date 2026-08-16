from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QWidget

from app.ui_v2.adapters.legacy_settings_bridge import (
    LegacySettingsBridge,
    load_settings_document,
    write_settings_document,
)
from app.ui_v2.shell.close_behavior_controller import (
    CLOSE_BEHAVIOR_ASK,
    CLOSE_BEHAVIOR_EXIT,
    CLOSE_BEHAVIOR_TRAY,
    CloseBehaviorController,
)
from app.ui_v2.shell.main_window import MainWindow


class CloseBehaviorControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="hushplayer_close_behavior_")
        self.settings_path = Path(self.temp_dir.name) / "settings.json"
        self.window = QWidget()
        self.window.show()
        self.controller = CloseBehaviorController(
            self.app,
            self.settings_path,
            tray_available=True,
            parent=self.app,
        )
        self.controller.register_window(self.window)
        self.app.processEvents()

    def tearDown(self) -> None:
        self.controller.tray_icon.hide()
        self.window.close()
        self.temp_dir.cleanup()
        self.app.processEvents()

    def _write_preferences(self, *, behavior: str, remember: bool) -> None:
        write_settings_document(
            self.settings_path,
            {
                "close_behavior": behavior,
                "remember_close_choice": remember,
            },
        )

    def test_missing_settings_default_to_asking_without_memory(self) -> None:
        preferences = load_settings_document(self.settings_path)
        self.assertEqual(preferences["close_behavior"], CLOSE_BEHAVIOR_ASK)
        self.assertFalse(preferences["remember_close_choice"])

    def test_remembered_exit_accepts_close_without_decision_dialog(self) -> None:
        self._write_preferences(behavior=CLOSE_BEHAVIOR_EXIT, remember=True)
        controller = CloseBehaviorController(
            self.app,
            self.settings_path,
            tray_available=True,
            decision_provider=lambda _window: self.fail("decision dialog was unexpected"),
            parent=self.app,
        )
        event = QCloseEvent()
        self.assertTrue(controller.handle_close(self.window, event))
        self.assertTrue(event.isAccepted())
        controller.tray_icon.hide()

    def test_remembered_tray_hides_without_shutdown_and_can_restore(self) -> None:
        self._write_preferences(behavior=CLOSE_BEHAVIOR_TRAY, remember=True)
        event = QCloseEvent()
        self.assertFalse(self.controller.handle_close(self.window, event))
        self.assertFalse(event.isAccepted())
        self.assertFalse(self.window.isVisible())
        self.controller.restore_window()
        self.app.processEvents()
        self.assertTrue(self.window.isVisible())

    def test_unremembered_decision_clears_the_previous_action(self) -> None:
        self._write_preferences(behavior=CLOSE_BEHAVIOR_TRAY, remember=False)
        controller = CloseBehaviorController(
            self.app,
            self.settings_path,
            tray_available=True,
            decision_provider=lambda _window: (CLOSE_BEHAVIOR_EXIT, False),
            parent=self.app,
        )
        event = QCloseEvent()
        self.assertTrue(controller.handle_close(self.window, event))
        preferences = load_settings_document(self.settings_path)
        self.assertEqual(preferences["close_behavior"], CLOSE_BEHAVIOR_ASK)
        self.assertFalse(preferences["remember_close_choice"])
        controller.tray_icon.hide()

    def test_tray_exit_closes_window_and_quits_application(self) -> None:
        with patch.object(self.app, "quit") as quit_app:
            self.controller.request_exit()
            self.app.processEvents()
            quit_app.assert_called()

    def test_settings_bridge_persists_and_clears_close_memory(self) -> None:
        bridge = LegacySettingsBridge(self.settings_path)
        saved = bridge.save_snapshot(
            bridge.read_snapshot().with_updates(
                {
                    "close_behavior": CLOSE_BEHAVIOR_TRAY,
                    "remember_close_choice": True,
                }
            )
        )
        self.assertEqual(saved.get("close_behavior"), CLOSE_BEHAVIOR_TRAY)
        self.assertTrue(saved.get("remember_close_choice"))

        bridge.save_snapshot(
            saved.with_updates(
                {
                    "close_behavior": CLOSE_BEHAVIOR_EXIT,
                    "remember_close_choice": False,
                }
            )
        )
        preferences = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(preferences["close_behavior"], CLOSE_BEHAVIOR_ASK)
        self.assertFalse(preferences["remember_close_choice"])


class MainWindowCloseBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_title_bar_close_can_hide_without_running_window_shutdown(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer_main_close_") as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            controller = CloseBehaviorController(
                self.app,
                settings_path,
                tray_available=True,
                decision_provider=lambda _window: (CLOSE_BEHAVIOR_TRAY, False),
                parent=self.app,
            )
            window = MainWindow(
                data_mode="mock",
                settings_path=settings_path,
                close_behavior_controller=controller,
            )
            window.show()
            self.app.processEvents()
            window.title_bar.close_button.click()
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertFalse(window._close_finalized)
            controller.restore_window()
            window.close()
            self.assertTrue(window._close_finalized)
            controller.tray_icon.hide()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
