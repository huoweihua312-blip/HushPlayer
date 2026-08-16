from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.ui_v2.pages.pending_imports_page import PendingImportsPage
from app.ui_v2.theme.tokens import get_theme


class PendingImportsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = PendingImportsPage(get_theme("dark"))
        self.records = [
            {
                "title": "待导入歌曲",
                "artist": "测试歌手",
                "album": "测试专辑",
                "path": str(Path("C:/Music/pending.mp3")),
            },
            {
                "title": "第二首",
                "artist": "测试歌手",
                "album": "测试专辑",
                "path": str(Path("C:/Music/second.flac")),
            },
        ]
        self.page.set_records(self.records)
        self.page.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()

    def test_records_and_selection_actions_use_paths(self) -> None:
        self.assertEqual(self.page.list_widget.count(), 2)
        self.assertEqual(self.page.header.count_label.text(), "2 首歌曲")
        self.page.list_widget.selectAll()
        self.assertTrue(self.page.import_button.isEnabled())
        imported: list[list[str]] = []
        self.page.import_requested.connect(imported.append)
        self.page.import_button.click()
        self.assertEqual(
            imported,
            [[record["path"] for record in self.records]],
        )

    def test_ignore_and_open_folder_actions_use_selected_record(self) -> None:
        self.page.list_widget.item(0).setSelected(True)
        ignored: list[list[str]] = []
        folders: list[str] = []
        self.page.ignore_requested.connect(ignored.append)
        self.page.open_folder_requested.connect(folders.append)
        self.page.ignore_button.click()
        self.page.open_folder_button.click()
        self.assertEqual(ignored, [[self.records[0]["path"]]])
        self.assertEqual(folders, [self.records[0]["path"]])

    def test_empty_state_hides_list_and_actions(self) -> None:
        self.page.set_records(())
        self.assertTrue(self.page.empty_label.isVisible())
        self.assertFalse(self.page.list_widget.isVisible())
        self.assertFalse(self.page.import_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
