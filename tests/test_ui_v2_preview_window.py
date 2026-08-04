from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.ui_v2.shell.preview_window import PreviewWindow
from app.ui_v2.models.track_table_model import TrackColumn


class UiV2PreviewWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_preview_construct_show_process_and_close(self) -> None:
        window = PreviewWindow()
        self.assertEqual(window.adapter.tracks().__len__(), 1000)
        window.show()
        self.app.processEvents()
        self.assertTrue(window.isVisible())
        window.close()
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        window.deleteLater()

    def test_responsive_geometries_keep_model_and_apply_column_priorities(self) -> None:
        window = PreviewWindow()
        table = window.library_page.track_table
        model = table.model
        window.show()
        window.resize(900, 600)
        self.app.processEvents()
        self.assertIs(table.model, model)
        self.assertEqual(table.column_profile, "narrow")
        # The final narrow profile keeps the trailing action column visible;
        # it is rendered as the lightweight "more" affordance by the delegate.
        self.assertFalse(table.isColumnHidden(int(TrackColumn.ADDED_AT)))
        self.assertLessEqual(table.columnWidth(int(TrackColumn.SOURCE)), 36)
        self.assertGreater(
            table.columnWidth(int(TrackColumn.TITLE)),
            table.columnWidth(int(TrackColumn.ALBUM)),
        )
        self.assertIsNotNone(window.library_page.search_box)
        self.assertGreaterEqual(window.library_page.search_box.width(), 180)
        self.assertFalse(window.library_page.theme_toggle.isVisible())
        self.assertFalse(window.library_page.state_toggle.isVisible())
        self.assertTrue(window.library_page.header.title_label.isVisible())
        self.assertTrue(window.library_page.header.count_label.isVisible())
        for width, height, expected_profile in ((1100, 700, "standard"), (1400, 850, "wide")):
            window.resize(width, height)
            self.app.processEvents()
            self.assertIs(table.model, model)
            self.assertEqual(table.column_profile, expected_profile)
            self.assertFalse(table.isColumnHidden(int(TrackColumn.ADDED_AT)))
            self.assertEqual(table.horizontalScrollBar().maximum(), 0)
            self.assertGreater(table.viewport().height(), 0)
            self.assertGreater(window.library_page.search_box.width(), 150)
        self.assertTrue(window.library_page.theme_toggle.isVisible())
        self.assertFalse(window.library_page.state_toggle.isVisible())
        self.assertGreaterEqual(table.columnWidth(int(TrackColumn.SOURCE)), 140)
        self.assertGreaterEqual(table.columnWidth(int(TrackColumn.ALBUM)), 240)
        window.close()
        window.deleteLater()

    def test_header_tracks_hover_and_sort_without_default_cell_selection(self) -> None:
        window = PreviewWindow()
        table = window.library_page.track_table
        window.show()
        self.app.processEvents()
        title_column = int(TrackColumn.TITLE)
        table.header._set_hovered_section(title_column)
        self.assertEqual(table.header.hovered_section, title_column)
        table._on_header_clicked(title_column)
        self.assertEqual(table.header.sortIndicatorSection(), title_column)
        window.close()
        window.deleteLater()

    def test_legacy_main_and_main_window_remain_importable(self) -> None:
        legacy_main = importlib.import_module("main")
        legacy_window_module = importlib.import_module("app.ui.main_window")
        self.assertTrue(callable(legacy_main.main))
        self.assertTrue(hasattr(legacy_window_module, "MainWindow"))


if __name__ == "__main__":
    unittest.main()
