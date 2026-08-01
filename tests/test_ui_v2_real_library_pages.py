from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track_table_model import TrackColumn
from app.ui_v2.shell.main_window import MainWindow


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_state(paths: tuple[Path, ...]) -> dict[Path, tuple[str, int, int]]:
    return {
        path: (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in paths
    }


class RealLibraryPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.app_data = self.root / "application-data"
        self.data_dir = self.app_data / "data"
        self.data_dir.mkdir(parents=True)
        self.alpha = self._create_audio("music/alpha.mp3")
        self.beta = self._create_audio("music/beta.mp3")
        self.library_file = self.data_dir / "library.json"
        self.playlists_file = self.data_dir / "playlists.json"
        self.stats_file = self.data_dir / "stats.json"
        self.remote_file = self.data_dir / "remote_tracks.json"
        self._write_documents()
        self.document_paths = (
            self.library_file,
            self.playlists_file,
            self.stats_file,
            self.remote_file,
        )
        self.before_state = _file_state(self.document_paths)
        self.environment = patch.dict(
            os.environ,
            {
                "HUSHPLAYER_UI_V2_DATA_MODE": "real",
                "HUSHPLAYER_APP_DATA_DIR": str(self.app_data),
                "HUSHPLAYER_CACHE_DIR": str(self.root / "cache"),
                "HUSHPLAYER_LOG_DIR": str(self.root / "logs"),
            },
            clear=False,
        )
        self.environment.start()
        self.window = MainWindow()
        self.assertTrue(
            self._wait_for(
                lambda: self.window.real_library_adapter is not None
                and self.window.real_library_adapter.state in {"loaded", "empty", "error"}
            )
        )
        self.assertEqual(self.window.real_library_adapter.state, "loaded")

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        self.environment.stop()
        self.temporary_directory.cleanup()

    def _create_audio(self, relative_path: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture audio")
        return path

    def _write_documents(self) -> None:
        _write_json(
            self.library_file,
            [
                {
                    "path": str(self.alpha),
                    "title": "Alpha",
                    "artist": "Artist A",
                    "album": "Album A",
                    "duration": 181,
                    "added_at": 100,
                    "local_cover_path": "cover-alpha",
                },
                {
                    "path": str(self.beta),
                    "title": "Beta",
                    "artist": "Artist B",
                    "album": "Album B",
                    "duration": 202,
                    "added_at": 200,
                },
            ],
        )
        _write_json(
            self.playlists_file,
            {
                "liked": {
                    "name": "我喜欢",
                    "songs": [str(self.alpha)],
                    "remoteSongs": ["remote_fixture_001"],
                    "members": [
                        {"kind": "local", "id": str(self.alpha), "added_at": 2000},
                        {"kind": "remote", "id": "remote_fixture_001", "added_at": 3000},
                    ],
                },
                "commute": {
                    "name": "通勤",
                    "description": "保留成员顺序。",
                    "songs": [str(self.beta), str(self.alpha)],
                    "remoteSongs": ["remote_fixture_001"],
                    "members": [
                        {"kind": "local", "id": str(self.beta), "added_at": 30},
                        {"kind": "remote", "id": "remote_fixture_001", "added_at": 20},
                        {"kind": "local", "id": str(self.alpha), "added_at": 10},
                    ],
                },
            },
        )
        _write_json(
            self.stats_file,
            {
                str(self.alpha): {"play_count": 2, "last_played": 1100},
                str(self.beta): {"play_count": 5, "last_played": 2200},
            },
        )
        _write_json(
            self.remote_file,
            {
                "version": 1,
                "tracks": {
                    "remote_fixture_001": {
                        "source_id": "fixture-catalog",
                        "remote_id": "song-1",
                        "title": "Remote",
                        "artist": "Artist C",
                        "album": "Album C",
                        "duration": 203,
                        "added_at": 300,
                        "local_path": "",
                    }
                },
            },
        )

    def _wait_for(self, predicate, *, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return bool(predicate())

    def test_real_pages_reuse_the_shared_collection_and_cached_route_pages(self) -> None:
        adapter = self.window.real_library_adapter
        self.assertIsNotNone(adapter)
        self.assertEqual(self.window.data_mode, "real")
        self.assertTrue(self.window.library_collection.read_only)
        self.assertTrue(self.window.playlist_adapter.read_only)
        self.assertEqual(self.window.library_page.track_table.model.rowCount(), 3)
        self.assertEqual(len(adapter.tracks()), 3)

        favorites = self.window.router.page_for_route("liked")
        self.assertEqual([track.title for track in favorites.adapter.tracks()], ["Remote", "Alpha"])
        self.assertIs(favorites, self.window.router.page_for_route("favorites"))

        recent = self.window.router.page_for_route("recent")
        self.assertEqual([track.title for track in recent.adapter.tracks()], ["Beta", "Alpha"])
        self.assertIs(recent, self.window.router.page_for_route("recent"))

        artists = self.window.router.page_for_route("artists")
        self.assertEqual([artist.name for artist in artists.adapter.artists()], ["Artist A", "Artist B", "Artist C"])
        artist_detail = self.window.router.page_for_route("artist_detail:artist:artist a")
        self.assertEqual([track.title for track in artist_detail.adapter.tracks()], ["Alpha"])

        albums = self.window.router.page_for_route("albums")
        self.assertEqual([album.title for album in albums.adapter.albums()], ["Album A", "Album B", "Album C"])
        album_detail = self.window.router.page_for_route("album_detail:album:artist b::album b")
        self.assertEqual([track.title for track in album_detail.adapter.tracks()], ["Beta"])

        playlist_page = self.window.router.page_for_route("playlist:commute")
        self.assertEqual([track.title for track in playlist_page.adapter.tracks()], ["Beta", "Alpha", "Remote"])
        self.assertIs(playlist_page, self.window.router.page_for_route("playlist:commute"))
        self.assertTrue(playlist_page.playlist_header.more_button.isHidden())

    def test_search_and_sort_reuse_mapped_tracks_without_refreshing_repository(self) -> None:
        adapter = self.window.real_library_adapter
        self.assertIsNotNone(adapter)
        original = tuple(track.id for track in adapter.tracks())
        self.window.library_adapter.set_query("beta")
        self.assertEqual([track.title for track in self.window.library_adapter.tracks()], ["Beta"])
        self.window.library_adapter.set_query("")
        self.window.library_adapter.set_sort(
            TrackColumn.TITLE,
            Qt.SortOrder.AscendingOrder,
        )
        self.assertEqual(
            [track.title for track in self.window.library_adapter.tracks()],
            ["Alpha", "Beta", "Remote"],
        )
        self.assertEqual(tuple(track.id for track in adapter.tracks()), original)
        self.assertEqual(adapter.state, "loaded")

    def test_real_mode_hides_or_rejects_every_library_write_entry(self) -> None:
        library_table = self.window.library_page.track_table
        menu = library_table.build_context_menu(library_table.model.index(0, 0))
        self.assertIsNotNone(menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            ["播放", "查看歌曲信息"],
        )
        menu.deleteLater()
        self.assertTrue(self.window.player_bar.favorite_button.isHidden())
        self.assertTrue(self.window.sidebar.new_playlist_button.isHidden())
        self.assertNotIn("online_search", self.window.sidebar._items)
        first = self.window.library_collection.tracks()[0]
        self.assertFalse(self.window.library_collection.set_favorite(first.id, not first.is_favorite))
        self.assertIsNone(self.window.playlist_adapter.create_playlist("不可写"))
        self.assertFalse(self.window.playlist_adapter.rename_playlist("commute", "不可写"))
        self.assertFalse(self.window.playlist_adapter.delete_playlist("commute"))
        self.assertEqual(self.window.playlist_adapter.add_tracks("commute", (first.id,)), 0)
        self.assertFalse(self.window.playlist_adapter.remove_track("commute", first.id))

    def test_real_window_does_not_change_any_isolated_user_document(self) -> None:
        self.window.router.page_for_route("liked")
        self.window.router.page_for_route("recent")
        self.window.router.page_for_route("artists")
        self.window.router.page_for_route("albums")
        self.window.router.page_for_route("playlist:commute")
        self.assertEqual(self.before_state, _file_state(self.document_paths))

    def test_error_view_shows_retry_instead_of_mock_fallback(self) -> None:
        self.window.close()
        self.app.processEvents()
        self.library_file.write_text("[", encoding="utf-8")
        self.window = MainWindow()
        self.assertTrue(
            self._wait_for(lambda: self.window.real_library_adapter.state == "error")
        )
        self.assertEqual(self.window.library_collection.tracks(), ())
        self.assertEqual(self.window.library_page.current_view_state, "error")
        self.assertEqual(self.window.library_page.empty_state.action_button.text(), "重试")
        self.window.library_page.empty_state.action_button.click()
        self.assertTrue(
            self._wait_for(lambda: self.window.real_library_adapter.state == "error")
        )

    def test_mock_mode_remains_the_default_interactive_preview(self) -> None:
        self.window.close()
        self.app.processEvents()
        os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = "mock"
        self.window = MainWindow()
        self.assertEqual(self.window.data_mode, "mock")
        self.assertIsNone(self.window.real_library_adapter)
        self.assertEqual(len(self.window.library_collection.tracks()), 1000)
        self.assertIn("online_search", self.window.sidebar._items)
        self.assertFalse(self.window.sidebar.new_playlist_button.isHidden())


if __name__ == "__main__":
    unittest.main()
