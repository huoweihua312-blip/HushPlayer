"""Every visible caption X must use the same production close decision."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.shell.close_behavior_controller import CloseBehaviorController


class ImmersiveCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_caption_close_decisions(self):
        for mode in ("shell", "lyrics", "now_playing", "fullscreen"):
            for choice in (None, ("tray", False), ("exit", False)):
                with self.subTest(mode=mode, choice=choice), tempfile.TemporaryDirectory() as tmp:
                    calls = []
                    def decide(host):
                        calls.append(host)
                        return choice
                    controller = CloseBehaviorController(self.app, Path(tmp)/"settings.json", tray_available=True, decision_provider=decide)
                    window = MainWindow(data_mode="mock", settings_path=Path(tmp)/"settings.json", close_behavior_controller=controller)
                    try:
                        window.show()
                        if mode != "shell":
                            window.navigation_adapter.set_route("immersive_lyrics")
                            page = window.router.currentWidget()
                            page.set_mode("now_playing" if mode == "now_playing" else "lyrics")
                            if mode == "fullscreen":
                                page.enter_fullscreen()
                            button = page._window_buttons[2]
                        else:
                            button = window.title_bar.close_button
                        self.app.processEvents()
                        with patch.object(self.app, "quit"):
                            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                            self.app.processEvents()
                        self.assertEqual(calls, [window])
                        self.assertEqual(window._close_finalized, choice == ("exit", False))
                        self.assertEqual(window.isVisible(), choice is None)
                        if choice == ("tray", False):
                            controller.open_action.trigger()
                            self.assertTrue(window.isVisible())
                            self.assertFalse(window._close_finalized)
                            with patch.object(self.app, "quit") as quit_app:
                                controller.exit_action.trigger()
                                self.app.processEvents()
                                quit_app.assert_called()
                            self.assertTrue(window._close_finalized)
                    finally:
                        window.close()
                        window.deleteLater()
                        controller.tray_icon.hide()
                        controller.tray_menu.deleteLater()
                        controller.deleteLater()
                        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                        self.app.processEvents()
