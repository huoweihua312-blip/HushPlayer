"""Large SVG covers must be rasterized at their display resolution."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from app.ui_v2.widgets.placeholder_cover import cover_pixmap, placeholder_cover_path


class PlaceholderResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_large_cover_keeps_vector_detail(self):
        for size in (360, 720):
            with self.subTest(size=size):
                expected = QPixmap(size, size)
                expected.fill(Qt.GlobalColor.transparent)
                painter = QPainter(expected)
                QSvgRenderer(str(placeholder_cover_path("resolution-test"))).render(
                    painter, QRectF(0, 0, size, size)
                )
                painter.end()
                self.assertEqual(cover_pixmap("resolution-test", size, size).toImage(), expected.toImage())


if __name__ == "__main__":
    unittest.main()
