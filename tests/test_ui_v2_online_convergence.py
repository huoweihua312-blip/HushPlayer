"""B2 online presentation preserves the existing desktop request contracts."""
import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.online_search_page import OnlineSearchPage
from app.ui_v2.pages.online_source_page import SourceRow
from app.ui_v2.pages.pending_imports_page import PendingImportsPage
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.online_recovery_dialog import OnlineRecoveryCandidateDialog


class OnlineConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.collection = LibraryCollectionAdapter(create_mock_tracks(8))
        self.playlists = PlaylistAdapter(self.collection)
        self.adapter = OnlineAdapter(self.collection, self.playlists, timer_enabled=False)
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def page(self):
        page = OnlineSearchPage(self.adapter, self.playlists, get_theme("dark"))
        self.widgets.append(page)
        page.resize(984, 740)
        page.show()
        self.app.processEvents()
        return page

    def candidates(self):
        self.adapter.set_query("Night")
        self.adapter.search()
        self.adapter.complete_for_test()
        return self.adapter.results()[:4]

    def test_two_inputs_share_query_without_duplicate_edit(self):
        page = self.page()
        edits = QSignalSpy(page.search_bar.query_changed)
        queries = QSignalSpy(self.adapter.query_changed)
        self.adapter.set_query("来自标题栏")
        self.assertEqual(page.search_bar.line_edit.text(), "来自标题栏")
        self.assertEqual(edits.count(), 0)
        self.assertEqual(queries.count(), 1)
        page.search_bar.set_text("来自页内")
        self.assertEqual(self.adapter.query, "来自页内")
        self.assertEqual(edits.count(), 1)
        self.assertEqual(queries.count(), 2)
        QTest.keyClick(page.search_bar.line_edit, Qt.Key.Key_Return)
        self.assertEqual(self.adapter.state.phase, "searching")
        self.adapter.complete_for_test()
        self.assertEqual(self.adapter.state.phase, "results")

    def test_scope_checkbox_updates_original_source_and_search_guard(self):
        page = self.page()
        source = self.adapter.sources()[0]
        check = page._scope_checks[source.id]
        QTest.mouseClick(check, Qt.MouseButton.LeftButton, pos=QPoint(7, check.height() // 2))
        self.assertEqual(self.adapter.sources()[0].enabled, not source.enabled)
        self.assertEqual(check.isChecked(), not source.enabled)
        self.adapter.set_query("Night")
        self.adapter.search()
        self.assertFalse(check.isEnabled())
        self.adapter.complete_for_test()
        self.assertTrue(check.isEnabled())

    def test_source_switch_entire_track_and_remove_menu_keep_payload(self):
        source = self.adapter.sources()[0]
        row = SourceRow(source, get_theme("dark"))
        self.widgets.append(row)
        row.resize(800, 115)
        row.show()
        self.app.processEvents()
        toggle = QSignalSpy(row.toggle_requested)
        for x in (3, 36):
            row.set_source(source)
            QTest.mouseClick(row.enabled_button, Qt.MouseButton.LeftButton, pos=QPoint(x, 12))
            self.assertEqual(toggle.at(toggle.count() - 1), [source.id, not source.enabled])
        removed = QSignalSpy(row.remove_requested)
        row.remove_action.trigger()
        self.assertEqual(removed.at(0), [source.id])

    def test_recovery_columns_do_not_overlap_and_keep_selected_object(self):
        candidates = tuple(replace(t, title="很长的候选歌曲 " * 30, source_name="长来源 " * 30) for t in self.candidates())
        original = replace(self.collection.tracks()[0], is_favorite=True)
        for mode in ("dark", "light"):
            dialog = OnlineRecoveryCandidateDialog(candidates, get_theme(mode), original_track=original)
            self.widgets.append(dialog)
            dialog.resize(640, 636)
            dialog.show()
            self.app.processEvents()
            row = dialog.list_widget.itemWidget(dialog.list_widget.item(0))
            self.assertLess(row.source_label.geometry().right(), row.duration_label.geometry().left())
            self.assertLess(row.title_label.geometry().right(), row.source_label.geometry().left())
            self.assertLessEqual(row.duration_label.geometry().right(), row.width())
            self.assertEqual(dialog.original_title.full_text, original.title)
            dialog.list_widget.setCurrentRow(1)
            QTest.keyClick(dialog.list_widget, Qt.Key.Key_Return)
            self.assertIs(dialog.selected_track, candidates[1])
            self.assertTrue(original.is_favorite)

    def test_pending_keyboard_multiselection_and_original_paths(self):
        page = PendingImportsPage(get_theme("light"))
        self.widgets.append(page)
        records = [{"title": "长歌名" * 20, "path": f"F:/Music/{'long/' * 50}{i}.flac"} for i in range(3)]
        page.set_records(records)
        page.resize(984, 700)
        page.show()
        self.app.processEvents()
        page.list_widget.setCurrentRow(0)
        QTest.keyClick(page.list_widget, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
        imported = QSignalSpy(page.import_requested)
        page.import_button.click()
        self.assertEqual(imported.at(0), [[r["path"] for r in records[:2]]])
        self.assertEqual(page.selection_count.text(), "已选择 2 首")
        self.assertFalse(page.list_widget.horizontalScrollBar().isVisible())


if __name__ == "__main__":
    unittest.main()
