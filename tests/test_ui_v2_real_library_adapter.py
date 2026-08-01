from __future__ import annotations

import ast
import hashlib
import json
import os
import tempfile
import threading
import time
import tracemalloc
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.services.library_repository import (
    LibraryRecords,
    LibraryRepository,
    LibrarySnapshot,
    PlaylistRecords,
)
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.adapters.real_library_adapter import (
    RealLibraryAdapter,
    ui_v2_data_mode,
)


def _file_state(paths: tuple[Path, ...]) -> dict[Path, tuple[str, int, int]]:
    return {
        path: (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in paths
    }


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _snapshot_with_title(title: str) -> LibrarySnapshot:
    path = f"C:/fixture/{title}.mp3"
    return LibrarySnapshot(
        LibraryRecords(
            (
                {
                    "path": path,
                    "title": title,
                    "artist": "Fixture Artist",
                    "album": "Fixture Album",
                    "duration": 180,
                    "added_at": 100,
                },
            ),
            "loaded",
            "",
            True,
        ),
        PlaylistRecords(LibraryRepository.default_playlists(), "", False),
        {},
    )


class _MemoryRemoteTrackStore:
    def __init__(self, tracks: dict[str, dict] | None = None) -> None:
        self.tracks = dict(tracks or {})
        self.calls = 0

    def load_tracks(self) -> dict[str, dict]:
        self.calls += 1
        return {key: dict(value) for key, value in self.tracks.items()}


class _CountingRepository:
    def __init__(
        self,
        snapshots: tuple[LibrarySnapshot, ...],
        *,
        release_first: threading.Event | None = None,
    ) -> None:
        self._snapshots = snapshots
        self._release_first = release_first
        self.calls = 0
        self.thread_ids: list[int] = []
        self.first_started = threading.Event()

    def load_snapshot(self) -> LibrarySnapshot:
        self.calls += 1
        self.thread_ids.append(threading.get_ident())
        if self.calls == 1 and self._release_first is not None:
            self.first_started.set()
            self._release_first.wait(5)
        return self._snapshots[min(self.calls - 1, len(self._snapshots) - 1)]


class RealLibraryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data_dir = self.root / "data"
        self.data_dir.mkdir()
        self.alpha = self._create_audio("music/alpha.mp3")
        self.beta = self._create_audio("music/beta.mp3")
        self.library_file = self.data_dir / "library.json"
        self.playlists_file = self.data_dir / "playlists.json"
        self.stats_file = self.data_dir / "stats.json"
        self.remote_file = self.data_dir / "remote_tracks.json"
        self._write_complete_documents()
        self.repository = LibraryRepository(
            self.library_file,
            self.playlists_file,
            self.stats_file,
        )
        self.remote_store = RemoteTrackStore(self.remote_file)
        self.collection = LibraryCollectionAdapter((), read_only=True)
        self.playlists = PlaylistAdapter(
            self.collection,
            seed_mock=False,
            read_only=True,
        )
        self.adapter = RealLibraryAdapter(
            self.collection,
            self.playlists,
            repository=self.repository,
            remote_tracks=self.remote_store,
        )

    def tearDown(self) -> None:
        self.adapter.shutdown()
        self._wait_for(lambda: not self.adapter.is_loading, timeout=2)
        self.temporary_directory.cleanup()

    def _create_audio(self, relative_path: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture audio")
        return path

    def _write_complete_documents(self) -> None:
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
                    "description": "按原始成员顺序展示。",
                    "songs": [str(self.beta), str(self.alpha)],
                    "remoteSongs": ["remote_fixture_001", "remote_missing"],
                    "members": [
                        {"kind": "local", "id": str(self.beta), "added_at": 30},
                        {"kind": "remote", "id": "remote_fixture_001", "added_at": 20},
                        {"kind": "local", "id": str(self.alpha), "added_at": 10},
                        {"kind": "remote", "id": "remote_missing", "added_at": 1},
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
                        "artwork": "https://example.invalid/cover.jpg",
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

    def _load(self) -> None:
        self.assertTrue(self.adapter.load())
        self.assertTrue(
            self._wait_for(lambda: self.adapter.state in {"loaded", "empty", "error"})
        )
        self.assertNotEqual(self.adapter.state, "error", self.adapter.last_error())

    def test_default_mode_is_mock_and_real_requires_explicit_value(self) -> None:
        previous = os.environ.pop("HUSHPLAYER_UI_V2_DATA_MODE", None)
        try:
            self.assertEqual(ui_v2_data_mode(), "mock")
            os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = "REAL"
            self.assertEqual(ui_v2_data_mode(), "real")
            os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = "preview"
            self.assertEqual(ui_v2_data_mode(), "mock")
        finally:
            if previous is not None:
                os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = previous
            else:
                os.environ.pop("HUSHPLAYER_UI_V2_DATA_MODE", None)

    def test_adapter_has_no_json_parser_or_persistent_write_surface(self) -> None:
        source_path = Path(RealLibraryAdapter.__module__.replace(".", "/") + ".py")
        if not source_path.exists():
            source_path = Path(__file__).parents[1] / "app" / "ui_v2" / "adapters" / "real_library_adapter.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        self.assertFalse([name for name in imports if name == "json" or name.startswith("json.")])
        method_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertFalse(
            [
                name
                for name in method_names
                if any(token in name.casefold() for token in ("save", "write", "delete", "rename"))
            ]
        )
        self.assertFalse(hasattr(self.adapter, "save"))
        self.assertFalse(hasattr(self.adapter, "write"))

    def test_worker_load_maps_repository_snapshot_without_file_changes(self) -> None:
        before = _file_state(
            (self.library_file, self.playlists_file, self.stats_file, self.remote_file)
        )
        self._load()

        tracks = self.adapter.tracks()
        self.assertEqual([track.title for track in tracks], ["Alpha", "Beta", "Remote"])
        alpha, beta, remote = tracks
        self.assertEqual(alpha.stable_id, f"local:{str(self.alpha.resolve()).casefold()}")
        self.assertEqual(alpha.local_path, str(self.alpha.resolve()))
        self.assertEqual(alpha.duration_ms, 181_000)
        self.assertEqual(alpha.artwork_key, "cover-alpha")
        self.assertEqual(alpha.play_count, 2)
        self.assertIsNotNone(alpha.last_played_at)
        self.assertEqual(remote.stable_id, "remote_fixture_001")
        self.assertEqual(remote.remote_identity, "remote_fixture_001")
        self.assertEqual(remote.source_type, "online")
        self.assertTrue(remote.is_missing)
        self.assertEqual(remote.availability, "source-unavailable")
        self.assertEqual([track.id for track in self.adapter.favorites()], [remote.id, alpha.id])
        self.assertEqual([track.id for track in self.adapter.recent_tracks()], [beta.id, alpha.id])
        self.assertEqual(
            [track.title for track in self.adapter.playlist_tracks("commute")],
            ["Beta", "Alpha", "Remote"],
        )
        self.assertEqual(len(self.adapter.artists()), 3)
        self.assertEqual(len(self.adapter.albums()), 3)
        artist_a = next(artist for artist in self.adapter.artists() if artist.name == "Artist A")
        album_b = next(album for album in self.adapter.albums() if album.title == "Album B")
        self.assertEqual([track.title for track in self.adapter.artist_tracks(artist_a.id)], ["Alpha"])
        self.assertEqual([track.title for track in self.adapter.album_tracks(album_b.id)], ["Beta"])
        self.assertIs(self.adapter.track_by_id(alpha.id), alpha)
        self.assertIs(self.adapter.repository, self.repository)
        self.assertEqual(
            before,
            _file_state(
                (self.library_file, self.playlists_file, self.stats_file, self.remote_file)
            ),
        )

    def test_load_runs_repository_and_mapping_off_the_ui_thread(self) -> None:
        repository = _CountingRepository((_snapshot_with_title("Background"),))
        remote = _MemoryRemoteTrackStore()
        adapter = RealLibraryAdapter(
            self.collection,
            self.playlists,
            repository=repository,  # type: ignore[arg-type]
            remote_tracks=remote,  # type: ignore[arg-type]
        )
        try:
            self.assertTrue(adapter.load())
            self.assertTrue(self._wait_for(lambda: adapter.state == "loaded"))
            self.assertEqual(repository.calls, 1)
            self.assertEqual(remote.calls, 1)
            self.assertNotEqual(repository.thread_ids, [threading.get_ident()])
            self.assertEqual(adapter.tracks()[0].title, "Background")
        finally:
            adapter.shutdown()

    def test_refresh_generation_discards_stale_result_and_uses_one_worker_at_a_time(self) -> None:
        release = threading.Event()
        repository = _CountingRepository(
            (_snapshot_with_title("Old"), _snapshot_with_title("New")),
            release_first=release,
        )
        adapter = RealLibraryAdapter(
            self.collection,
            self.playlists,
            repository=repository,  # type: ignore[arg-type]
            remote_tracks=_MemoryRemoteTrackStore(),  # type: ignore[arg-type]
        )
        try:
            self.assertTrue(adapter.load())
            self.assertTrue(self._wait_for(repository.first_started.is_set))
            self.assertTrue(adapter.refresh())
            self.assertEqual(repository.calls, 1)
            release.set()
            self.assertTrue(self._wait_for(lambda: adapter.state == "loaded", timeout=8))
            self.assertEqual(repository.calls, 2)
            self.assertEqual([track.title for track in adapter.tracks()], ["New"])
        finally:
            release.set()
            adapter.shutdown()

    def test_shutdown_discards_an_inflight_worker_result(self) -> None:
        release = threading.Event()
        repository = _CountingRepository(
            (_snapshot_with_title("Closing"),),
            release_first=release,
        )
        adapter = RealLibraryAdapter(
            self.collection,
            self.playlists,
            repository=repository,  # type: ignore[arg-type]
            remote_tracks=_MemoryRemoteTrackStore(),  # type: ignore[arg-type]
        )
        self.assertTrue(adapter.load())
        self.assertTrue(self._wait_for(repository.first_started.is_set))
        release_timer = threading.Timer(0.02, release.set)
        release_timer.start()
        adapter.shutdown()
        release_timer.join()
        self.assertTrue(self._wait_for(lambda: not adapter.is_loading))
        self.assertEqual(adapter.tracks(), ())

    def test_empty_and_error_states_do_not_fall_back_to_mock_data(self) -> None:
        empty_repository = _CountingRepository(
            (
                LibrarySnapshot(
                    LibraryRecords((), "missing", "", True),
                    PlaylistRecords(LibraryRepository.default_playlists(), "", False),
                    {},
                ),
            )
        )
        empty = RealLibraryAdapter(
            self.collection,
            self.playlists,
            repository=empty_repository,  # type: ignore[arg-type]
            remote_tracks=_MemoryRemoteTrackStore(),  # type: ignore[arg-type]
        )
        try:
            self.assertTrue(empty.load())
            self.assertTrue(self._wait_for(lambda: empty.state == "empty"))
            self.assertEqual(empty.tracks(), ())
        finally:
            empty.shutdown()

        error_repository = _CountingRepository(
            (
                LibrarySnapshot(
                    LibraryRecords((), "error", "fixture broken library", True),
                    PlaylistRecords(LibraryRepository.default_playlists(), "", False),
                    {},
                ),
            )
        )
        error = RealLibraryAdapter(
            self.collection,
            self.playlists,
            repository=error_repository,  # type: ignore[arg-type]
            remote_tracks=_MemoryRemoteTrackStore(),  # type: ignore[arg-type]
        )
        try:
            self.assertTrue(error.load())
            self.assertTrue(self._wait_for(lambda: error.state == "error"))
            self.assertIn("fixture broken library", error.last_error())
            self.assertEqual(error.tracks(), ())
            self.assertFalse(error.collection.tracks())
        finally:
            error.shutdown()

    def test_read_only_collection_and_playlist_mutations_are_rejected(self) -> None:
        self._load()
        alpha = self.adapter.tracks()[0]
        original_recent = self.collection.recent_entries()
        original_playlists = self.playlists.playlists()
        self.assertFalse(self.collection.set_favorite(alpha.id, not alpha.is_favorite))
        self.collection.record_play(alpha.id)
        self.collection.clear_recent()
        self.assertEqual(self.collection.recent_entries(), original_recent)
        self.assertIsNone(self.playlists.create_playlist("不应创建"))
        self.assertFalse(self.playlists.rename_playlist("commute", "不应修改"))
        self.assertFalse(self.playlists.delete_playlist("commute"))
        self.assertEqual(self.playlists.add_tracks("commute", (alpha.id,)), 0)
        self.assertFalse(self.playlists.remove_track("commute", alpha.id))
        self.assertEqual(self.playlists.playlists(), original_playlists)

    def test_mapping_uses_bulk_indexes_for_ten_thousand_tracks(self) -> None:
        timings: list[tuple[int, float, int]] = []
        for size in (1_000, 5_000, 10_000):
            records = tuple(
                {
                    "path": f"C:/fixture/track-{index}.mp3",
                    "title": f"Track {index}",
                    "artist": f"Artist {index % 47}",
                    "album": f"Album {index % 109}",
                    "duration": 180,
                    "added_at": index + 1,
                }
                for index in range(size)
            )
            snapshot = LibrarySnapshot(
                LibraryRecords(records, "loaded", "", True),
                PlaylistRecords(
                    {
                        "liked": {
                            "members": [
                                {"kind": "local", "id": records[index]["path"], "added_at": index + 1}
                                for index in range(0, size, 97)
                            ]
                        },
                        "fixture": {
                            "name": "Fixture",
                            "members": [
                                {"kind": "local", "id": records[index]["path"], "added_at": index + 1}
                                for index in range(0, size, 101)
                            ],
                        },
                    },
                    "",
                    False,
                ),
                {
                    record["path"]: {"play_count": index % 7, "last_played": index}
                    for index, record in enumerate(records)
                    if index % 5 == 0
                },
            )
            tracemalloc.start()
            started = time.perf_counter()
            data = RealLibraryAdapter.map_snapshot(snapshot, {})
            elapsed = time.perf_counter() - started
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            timings.append((size, elapsed, peak))
            self.assertEqual(len(data.tracks), size)
            self.assertEqual(len(data.playlists), 1)
            self.assertEqual(len(data.recent_tracks), (size - 1) // 5)

        print(
            "RealLibraryAdapter map performance: "
            + ", ".join(
                f"{size} tracks={elapsed:.3f}s peak={peak / 1024 / 1024:.1f}MiB"
                for size, elapsed, peak in timings
            )
        )
        self.assertLess(
            timings[-1][1] / max(timings[0][1], 0.0001),
            18,
            "10,000-track mapping grew like a clear quadratic workload",
        )


if __name__ == "__main__":
    unittest.main()
