from __future__ import annotations

import inspect
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.services.library_repository import LibraryRepository, LibrarySnapshot
from app.ui.main_window import MainWindow


class _SongList:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def blockSignals(self, _blocked: bool) -> bool:
        return False

    def setUpdatesEnabled(self, _enabled: bool) -> None:
        return None

    def clear(self) -> None:
        self.items.clear()

    def addItem(self, item: dict) -> None:
        self.items.append(item)


class _LegacyReadHarness:
    def __init__(
        self,
        repository,
        snapshot: LibrarySnapshot | None = None,
    ) -> None:
        self.library_repository = repository
        self.library_file = repository.library_file
        if snapshot is not None:
            self.library_snapshot = snapshot
        self.song_list = _SongList()
        self.song_identity_to_item: dict = {}
        self.invalidated = False
        self.demo_requests: list[bool] = []
        self.playlist_membership_snapshots: dict = {}

    def invalidate_local_song_match_index(self) -> None:
        self.invalidated = True

    @staticmethod
    def create_song_list_item(song_data: dict) -> dict:
        return dict(song_data)

    def add_demo_songs(self, refresh_view: bool = True) -> None:
        self.demo_requests.append(refresh_view)

    @staticmethod
    def finish_music_library_load(_valid_count: int) -> None:
        return None


class _CountingRepository:
    def __init__(self, delegate: LibraryRepository) -> None:
        self.delegate = delegate
        self.library_file = delegate.library_file
        self.load_snapshot_calls = 0

    def load_snapshot(self) -> LibrarySnapshot:
        self.load_snapshot_calls += 1
        return self.delegate.load_snapshot()


class LegacyLibraryRepositoryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.audio = self.root / "music" / "fixture.mp3"
        self.audio.parent.mkdir()
        self.audio.write_bytes(b"fixture")
        self.library_file = self.root / "library.json"
        self.playlists_file = self.root / "playlists.json"
        self.stats_file = self.root / "stats.json"
        self.repository = LibraryRepository(
            self.library_file,
            self.playlists_file,
            self.stats_file,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_json(self, path: Path, value) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def write_fixture(self) -> None:
        self.write_json(
            self.library_file,
            [
                {"path": str(self.audio), "title": "第一首", "added_at": 1},
                {"path": str(self.audio), "title": "第二首", "added_at": 2},
            ],
        )
        self.write_json(
            self.playlists_file,
            {
                "liked": {"songs": [str(self.audio)]},
                "custom": {"name": "自建", "songs": [str(self.audio)]},
            },
        )
        self.write_json(
            self.stats_file,
            {str(self.audio): {"play_count": 4, "last_played": 12}},
        )

    def test_legacy_readers_reuse_one_existing_snapshot_without_file_reload(self) -> None:
        self.write_fixture()
        snapshot = self.repository.load_snapshot()
        counting_repository = _CountingRepository(self.repository)
        harness = _LegacyReadHarness(counting_repository, snapshot)

        with redirect_stdout(io.StringIO()):
            count, local_only = MainWindow.load_music_library(
                harness,
                refresh_view=False,
            )
            playlists = MainWindow.load_playlists(harness)
            stats = MainWindow.load_song_stats(harness)

        self.assertTrue(harness.invalidated)
        self.assertEqual(count, 2)
        self.assertTrue(local_only)
        self.assertEqual([item["title"] for item in harness.song_list.items], ["第一首", "第二首"])
        self.assertEqual(playlists["custom"]["name"], "自建")
        self.assertEqual(stats[str(self.audio.resolve())]["play_count"], 4)
        self.assertEqual(counting_repository.load_snapshot_calls, 0)

    def test_legacy_reader_bootstraps_one_snapshot_then_reuses_it(self) -> None:
        self.write_fixture()
        counting_repository = _CountingRepository(self.repository)
        harness = _LegacyReadHarness(counting_repository)

        with redirect_stdout(io.StringIO()):
            playlists = MainWindow.load_playlists(harness)
            stats = MainWindow.load_song_stats(harness)
            count, _local_only = MainWindow.load_music_library(
                harness,
                refresh_view=False,
            )

        self.assertEqual(counting_repository.load_snapshot_calls, 1)
        self.assertIsInstance(harness.library_snapshot, LibrarySnapshot)
        self.assertEqual(playlists["liked"]["name"], "我喜欢")
        self.assertEqual(stats[str(self.audio.resolve())]["last_played"], 12)
        self.assertEqual(count, 2)

    def test_legacy_demo_fallback_and_read_failure_compatibility(self) -> None:
        missing_snapshot = self.repository.load_snapshot()
        missing_harness = _LegacyReadHarness(self.repository, missing_snapshot)
        with redirect_stdout(io.StringIO()):
            result = MainWindow.load_music_library(missing_harness, refresh_view=False)
        self.assertEqual(result, (0, True))
        self.assertEqual(missing_harness.demo_requests, [False])

        self.library_file.write_text("[", encoding="utf-8")
        self.playlists_file.write_text("[", encoding="utf-8")
        self.stats_file.write_text("[", encoding="utf-8")
        failed_snapshot = self.repository.load_snapshot()
        failed_harness = _LegacyReadHarness(self.repository, failed_snapshot)
        with redirect_stdout(io.StringIO()):
            result = MainWindow.load_music_library(failed_harness, refresh_view=True)
            playlists = MainWindow.load_playlists(failed_harness)
            stats = MainWindow.load_song_stats(failed_harness)
        self.assertEqual(result, (0, True))
        self.assertEqual(failed_harness.demo_requests, [True])
        self.assertEqual(playlists, self.repository.default_playlists())
        self.assertTrue(failed_harness.playlists_load_error.startswith("读取歌单失败"))
        self.assertEqual(stats, {})

    def test_legacy_write_function_signatures_and_default_shapes_are_unchanged(self) -> None:
        expected_signatures = {
            "save_playlists": ("self",),
            "save_song_stats": ("self",),
            "set_media_item_liked": ("self", "value", "liked"),
            "add_local_path_to_playlist": ("self", "path", "playlist_id"),
            "remove_local_path_from_playlist": ("self", "path", "playlist_id"),
            "add_remote_id_to_playlist": ("self", "stable_id", "playlist_id"),
            "remove_remote_id_from_playlist": ("self", "stable_id", "playlist_id"),
        }
        for method_name, parameters in expected_signatures.items():
            with self.subTest(method=method_name):
                signature = inspect.signature(getattr(MainWindow, method_name))
                self.assertEqual(tuple(signature.parameters), parameters)
        defaults = self.repository.default_playlists()
        self.assertIsInstance(defaults, dict)
        self.assertIsInstance(defaults["liked"], dict)
        self.assertIsInstance(defaults["liked"]["songs"], list)
        self.assertIsInstance(defaults["liked"]["remoteSongs"], list)
        self.assertIsInstance(defaults["liked"]["members"], list)

    def test_main_window_constructs_one_repository_and_startup_passes_its_snapshot(self) -> None:
        init_source = inspect.getsource(MainWindow.__init__)
        self.assertEqual(init_source.count("LibraryRepository("), 1)
        self.assertEqual(init_source.count("self.library_repository.load_snapshot"), 1)
        self.assertIn("snapshot=self.library_snapshot", init_source)


if __name__ == "__main__":
    unittest.main()
