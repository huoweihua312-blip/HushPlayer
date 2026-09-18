"""Wheel routing for shared settings controls, using native Qt input delivery."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.settings_control_factory import SettingsControlFactory, ThemedComboBox


class SettingsInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.layout = QVBoxLayout(self.content)
        self.combo = ThemedComboBox(get_theme("dark"), self.content)
        SettingsControlFactory.style_combo(self.combo, get_theme("dark"))
        self.combo.addItems([f"Option {index}" for index in range(30)])
        self.combo.setCurrentIndex(10)
        self.layout.addWidget(self.combo)
        self.layout.addSpacing(1000)
        self.scroll.setWidget(self.content)
        self.scroll.resize(380, 280)
        self.scroll.show()
        self.app.processEvents()

    def tearDown(self):
        self.combo.hidePopup()
        self.scroll.close()
        self.scroll.deleteLater()
        self.app.processEvents()

    def wheel_over(self, widget):
        window = widget.window()
        position = widget.mapTo(window, widget.rect().center())
        QTest.wheelEvent(window.windowHandle(), position, QPoint(0, -120))
        self.app.processEvents()

    def test_closed_combo_scrolls_page_without_editing_with_or_without_focus(self):
        changed = QSignalSpy(self.combo.currentIndexChanged)
        for focused in (False, True):
            with self.subTest(focused=focused):
                self.scroll.verticalScrollBar().setValue(0)
                if focused:
                    self.combo.setFocus()
                else:
                    self.combo.clearFocus()
                self.app.processEvents()
                self.wheel_over(self.combo)
                self.assertEqual(self.combo.currentIndex(), 10)
                self.assertEqual(changed.count(), 0)
                self.assertGreater(self.scroll.verticalScrollBar().value(), 0)

    def test_keyboard_and_open_popup_selection_still_work(self):
        self.combo.setFocus()
        QTest.keyClick(self.combo, Qt.Key.Key_Down)
        self.assertEqual(self.combo.currentIndex(), 11)
        QTest.mouseClick(self.combo, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        view = self.combo.view()
        self.assertTrue(view.isVisible())
        index = view.model().index(12, 0)
        view.scrollTo(index)
        self.app.processEvents()
        QTest.mouseMove(view.viewport(), view.visualRect(index).center())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=view.visualRect(index).center())
        self.app.processEvents()
        self.assertEqual(self.combo.currentIndex(), 12)

    def test_open_popup_wheel_does_not_scroll_settings_page(self):
        self.combo.addItems([f"Extra {index}" for index in range(100)])
        self.combo.showPopup()
        self.app.processEvents()
        view = self.combo.view()
        bar = view.verticalScrollBar()
        bar.setValue(0)
        self.app.processEvents()
        self.assertGreater(bar.maximum(), 0)
        self.wheel_over(view.viewport())
        self.assertGreater(bar.value(), 0)
        self.assertEqual(self.scroll.verticalScrollBar().value(), 0)
        self.assertTrue(view.isVisible())

    def test_toolbar_keeps_existing_wheel_selection(self):
        toolbar_combo = ThemedComboBox(get_theme("dark"), self.content, variant="toolbar")
        toolbar_combo.addItems(["First", "Second", "Third"])
        self.layout.insertWidget(0, toolbar_combo)
        self.app.processEvents()
        self.wheel_over(toolbar_combo)
        self.assertEqual(toolbar_combo.currentIndex(), 1)


if __name__ == "__main__":
    unittest.main()
