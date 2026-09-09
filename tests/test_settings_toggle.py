import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.settings_control_factory import SettingsToggle


class SettingsToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_entire_track_toggles_once_in_both_states(self):
        toggle = SettingsToggle(False, get_theme("light"))
        events = []
        toggle.toggled.connect(events.append)
        toggle.show()
        self.app.processEvents()
        try:
            for checked in (False, True):
                for x in (2, 11, 20, 29, 38):
                    with self.subTest(checked=checked, x=x):
                        toggle.setChecked(checked)
                        events.clear()
                        QTest.mouseClick(toggle, Qt.MouseButton.LeftButton, pos=QPoint(x, 12))
                        self.assertEqual(toggle.isChecked(), not checked)
                        self.assertEqual(events, [not checked])
            toggle.setEnabled(False)
            events.clear()
            QTest.mouseClick(toggle, Qt.MouseButton.LeftButton, pos=QPoint(29, 12))
            self.assertEqual(events, [])
            toggle.setEnabled(True)
            toggle.setChecked(False)
            toggle.setFocus()
            QTest.keyClick(toggle, Qt.Key.Key_Space)
            self.assertTrue(toggle.isChecked())
        finally:
            toggle.close()
            toggle.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
