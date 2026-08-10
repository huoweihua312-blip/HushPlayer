"""Focused coverage for real action surfaces and playlist persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog

from app.services.library_repository import LibraryRepository
from app.services.online_discovery_bridge import OnlineDiscoveryBridge
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.playlist import Playlist
from app.ui_v2.models.track import Track
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.playlist_dialogs import PlaylistConfirmDialog, PlaylistNameDialog


class QuietOrbitActionSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow(data_mode="mock")
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_visible_shell_actions_have_real_destinations(self) -> None:
        title_bar = self.window.title_bar
        player_bar = self.window.player_bar
        sidebar = self.window.sidebar

        self.assertFalse(title_bar.view_options_button.isVisible())
        self.assertFalse(player_bar.more_button.isVisible())
        self.assertFalse(sidebar.more_playlists_button.isVisible())
        self.assertTrue(sidebar.new_playlist_button.isVisible())
        self.assertEqual(sidebar.new_playlist_button.toolTip(), "新建歌单")
        self.assertEqual(sidebar.new_playlist_button.accessibleName(), "新建歌单")
        self.assertEqual(len(sidebar._playlist_items), len(sidebar.adapter.playlists()))
        self.assertTrue(all(
            not section.see_all_button.isVisible()
            for section in self.window.router.browse_page.sections.values()
        ))

        favorites = self.window.router.page_for_route("liked")
        self.assertFalse(favorites.collection_hero.more_button.isVisible())

    def test_playlist_create_delete_preserves_playback_and_route_safety(self) -> None:
        track = next(track for track in self.window.library_collection.tracks() if not track.is_missing)
        self.window.playback_adapter.play_track(track.id)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, track.id)

        playlist = self.window.playlist_adapter.create_playlist("验收歌单")
        self.assertIsNotNone(playlist)
        assert playlist is not None
        self.window.navigation_adapter.set_route(f"playlist:{playlist.id}")
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.current_playlist_id, playlist.id)
        self.assertTrue(self.window.playlist_adapter.rename_playlist(playlist.id, "已重命名"))
        self.app.processEvents()
        self.assertEqual(self.window.playlist_adapter.playlist_for_id(playlist.id).name, "已重命名")

        self.assertTrue(self.window.playlist_adapter.delete_playlist(playlist.id))
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "library")
        self.assertEqual(self.window.playback_adapter.state.current_track.id, track.id)

    def test_fixed_liked_route_has_no_playlist_mutation(self) -> None:
        self.assertFalse(self.window.playlist_adapter.rename_playlist("liked", "新的名字"))
        self.assertFalse(self.window.playlist_adapter.delete_playlist("liked"))


class PlaylistDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_empty_name_is_rejected_and_valid_name_is_accepted(self) -> None:
        dialog = PlaylistNameDialog(get_theme("light"), "新建歌单")
        dialog.name_input.clear()
        dialog.accept()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog.error_label.isHidden())
        dialog.name_input.setText("  安静夜行  ")
        dialog.accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.name, "安静夜行")

    def test_delete_confirmation_copy_is_explicit(self) -> None:
        dialog = PlaylistConfirmDialog(
            get_theme("dark"),
            "删除歌单",
            "删除歌单不会删除音乐库中的歌曲。",
        )
        self.assertEqual(dialog.message_label.text(), "删除歌单不会删除音乐库中的歌曲。")
        self.assertEqual(dialog.confirm_button.accessibleName(), "删除歌单")


class RealPlaylistPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_real_playlist_operations_preserve_unknown_fields_and_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_file = root / "library.json"
            playlists_file = root / "playlists.json"
            stats_file = root / "stats.json"
            remote_file = root / "remote_tracks.json"
            library_file.write_text("[]", encoding="utf-8")
            stats_file.write_text("{}", encoding="utf-8")
            playlists_file.write_text(
                json.dumps(
                    {
                        "liked": {
                            "name": "我喜欢",
                            "songs": [],
                            "remoteSongs": [],
                            "members": [],
                            "membershipVersion": 1,
                            "fixed": True,
                        },
                        "road": {
                            "name": "通勤",
                            "songs": [],
                            "remoteSongs": [],
                            "members": [],
                            "membershipVersion": 1,
                            "fixed": False,
                            "vendorExtension": {"keep": True},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            repository = LibraryRepository(library_file, playlists_file, stats_file)
            bridge = OnlineDiscoveryBridge(repository, RemoteTrackStore(remote_file))
            track = Track(
                id="local:alpha",
                title="Alpha",
                artist="Artist",
                album="Album",
                duration_ms=180_000,
                source_id="local",
                source_name="本地音乐",
                source_type="local",
                added_at=datetime(2026, 1, 1, 12, 0),
                is_favorite=False,
                is_missing=False,
                is_loading=False,
                artwork_path=None,
                stable_identity="local:alpha",
                local_path=str(root / "music" / "alpha.mp3"),
            )
            collection = LibraryCollectionAdapter((track,), read_only=True)
            playlists = PlaylistAdapter(collection, seed_mock=False, read_only=True)
            playlists.set_mutation_backend(bridge)
            playlists.set_playlists(
                (
                    Playlist(
                        id="road",
                        name="通勤",
                        created_at=datetime(2026, 1, 1, 12, 0),
                    ),
                ),
                read_only=True,
                can_mutate=True,
            )

            created = playlists.create_playlist("夜行")
            self.assertIsNotNone(created)
            self.assertTrue(playlists.rename_playlist("road", "通勤重命名"))
            self.assertEqual(playlists.add_tracks("road", (track.id,)), 1)
            self.assertTrue(playlists.remove_track("road", track.id))
            self.assertTrue(playlists.delete_playlist(created.id))
            self.assertFalse(bridge.rename_playlist("liked", "不应修改"))
            self.assertFalse(bridge.delete_playlist("liked"))

            stored = json.loads(playlists_file.read_text(encoding="utf-8"))
            self.assertEqual(stored["road"]["name"], "通勤重命名")
            self.assertEqual(stored["road"]["songs"], [])
            self.assertEqual(stored["road"]["vendorExtension"], {"keep": True})
            self.assertIn("liked", stored)
            self.assertNotIn(created.id, stored)


if __name__ == "__main__":
    unittest.main()
