"""B2 online UI contracts without real network or user data."""
import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.pages.online_search_page import OnlineSearchPage
from app.ui_v2.models.online_track_model import OnlineColumn
from app.ui_v2.widgets.online_recovery_dialog import OnlineRecoveryCandidateDialog
from app.ui_v2.widgets.source_import_dialog import SourceImportDialog


class Importer(QObject):
    status_changed = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    busy_changed = Signal(bool)
    busy = False

    def import_urls(self, text, policy):
        self.received = (text, policy)

    def cancel(self):
        self.busy = False


class OnlineImportVisualContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.collection = LibraryCollectionAdapter(create_mock_tracks(10))
        self.playlists = PlaylistAdapter(self.collection)
        self.adapter = OnlineAdapter(self.collection, self.playlists, timer_enabled=False)
        self.adapter.set_query("夜航")
        self.adapter.search()
        self.adapter.complete_for_test()

    def test_compact_keeps_source_status_and_title_space(self):
        page = OnlineSearchPage(self.adapter, self.playlists, get_theme("dark"))
        page.resize(984, 700)
        page.set_responsive_reference_width(1080)
        page.show()
        self.app.processEvents()
        table = page.result_table
        self.assertTrue(table.isColumnHidden(int(OnlineColumn.ALBUM)))
        self.assertFalse(table.isColumnHidden(int(OnlineColumn.STATUS)))
        self.assertGreater(table.columnWidth(int(OnlineColumn.TITLE)), 260)
        self.assertTrue(page.search_bar.isVisible())
        page.close()
        page.deleteLater()

    def test_selected_recovery_preserves_original_identity_and_membership(self):
        original = replace(self.collection.tracks()[0], is_favorite=True, is_missing=True)
        playlist = self.playlists.create_playlist("恢复验证")
        self.playlists.add_tracks(playlist.id, [original.id])
        membership = tuple(t.id for t in self.playlists.tracks_for_playlist(playlist.id))
        dialog = OnlineRecoveryCandidateDialog(self.adapter.results()[:3], get_theme("dark"))
        dialog.list_widget.setCurrentRow(1)
        dialog._accept_selected()
        restored = self.adapter.build_playback_source_track(original, dialog.selected_track)
        self.assertIsNotNone(restored)
        self.assertEqual((restored.id, restored.stable_identity, restored.is_favorite),
                         (original.id, original.stable_identity, True))
        self.assertIn("playback_source", restored.remote_payload)
        self.assertEqual(membership, tuple(t.id for t in self.playlists.tracks_for_playlist(playlist.id)))
        dialog.deleteLater()

    def test_url_dialog_delivers_original_text_and_policy(self):
        importer = Importer()
        dialog = SourceImportDialog(importer, get_theme("light"))
        value = "https://example.invalid/" + "long/" * 50 + "source.json"
        dialog.url_input.setPlainText(value)
        dialog.confirm_toggle.setChecked(True)
        dialog._start_import()
        self.assertEqual(importer.received, (value, "open"))
        dialog._set_busy(True)
        self.assertFalse(dialog.import_button.isEnabled())
        dialog._set_busy(False)
        self.assertTrue(dialog.import_button.isEnabled())
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
