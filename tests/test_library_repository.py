from __future__ import annotations

import ast
import hashlib
import inspect
import json
import tempfile
import time
import tracemalloc
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import app.services.library_repository as library_repository_module
from app.models.media_item import MediaItem
from app.services.library_repository import LibraryRepository
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore


class LibraryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.audio_a = self.create_audio("music/alpha.mp3")
        self.audio_b = self.create_audio("music/beta.mp3")
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

    def create_audio(self, relative_path: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture audio")
        return path

    def write_json(self, path: Path, value) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def file_state(paths: tuple[Path, ...]) -> dict[Path, tuple[str, int, int]]:
        return {
            path: (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in paths
        }

    def write_complete_documents(self) -> None:
        self.write_json(
            self.library_file,
            [
                {
                    "path": str(self.audio_a),
                    "title": "Alpha",
                    "artist": "Artist A",
                    "album": "Album A",
                    "duration": 180,
                    "added_at": 11,
                    "format": "mp3",
                },
                {
                    "path": str(self.audio_b),
                    "title": "Beta",
                    "artist": "Artist B",
                    "album": "Album B",
                    "duration": 240,
                    "added_at": 12,
                },
            ],
        )
        self.write_json(
            self.playlists_file,
            {
                "liked": {
                    "name": "我喜欢",
                    "songs": [str(self.audio_a), str(self.audio_b)],
                    "remoteSongs": ["remote_catalog_track-7"],
                    "members": [
                        {
                            "kind": "local",
                            "id": str(self.audio_a),
                            "added_at": 30,
                        },
                        {
                            "kind": "local",
                            "id": str(self.audio_b),
                            "added_at": 20,
                        },
                        {
                            "kind": "remote",
                            "id": "remote_catalog_track-7",
                            "added_at": 10,
                        },
                    ],
                },
                "commute": {
                    "name": "通勤",
                    "songs": [str(self.audio_b), str(self.audio_a)],
                    "remoteSongs": ["missing-remote"],
                },
            },
        )
        self.write_json(
            self.stats_file,
            {
                str(self.audio_a): {
                    "play_count": 2,
                    "total_listen_time": 50,
                    "last_played": 100,
                },
                str(self.audio_b): {
                    "play_count": 3,
                    "total_listen_time": 60,
                    "last_played": 200,
                },
            },
        )

    def test_dependency_and_write_surface_audit(self) -> None:
        source_path = Path(library_repository_module.__file__)
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
        self.assertFalse(
            [name for name in imports if name.startswith(("app.ui", "PySide6.QtWidgets"))]
        )
        method_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        self.assertFalse(
            [
                name
                for name in method_names
                if any(token in name.casefold() for token in ("save", "write", "delete", "update"))
            ]
        )
        forbidden_file_calls = {
            "write_text",
            "write_bytes",
            "mkdir",
            "replace",
            "rename",
            "unlink",
            "touch",
        }
        self.assertFalse(
            [
                node.func.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_file_calls
            ]
        )
        self.assertFalse(hasattr(self.repository, "current_snapshot"))

    def test_all_missing_documents_keep_legacy_empty_states_without_creation(self) -> None:
        snapshot = self.repository.load_snapshot()

        self.assertEqual(snapshot.library.status, "missing")
        self.assertEqual(snapshot.library.tracks, ())
        self.assertEqual(snapshot.playlists.playlists, self.repository.default_playlists())
        self.assertEqual(snapshot.song_stats, {})
        self.assertFalse(any(path.exists() for path in (
            self.library_file,
            self.playlists_file,
            self.stats_file,
        )))

    def test_each_missing_document_is_independent(self) -> None:
        self.write_complete_documents()
        for missing_path, expected in (
            (self.library_file, "library"),
            (self.playlists_file, "playlists"),
            (self.stats_file, "stats"),
        ):
            with self.subTest(missing=missing_path.name):
                content = {
                    path: path.read_bytes()
                    for path in (self.library_file, self.playlists_file, self.stats_file)
                    if path.exists()
                }
                missing_path.unlink()
                snapshot = self.repository.load_snapshot()
                if expected == "library":
                    self.assertEqual(snapshot.library.status, "missing")
                elif expected == "playlists":
                    self.assertEqual(
                        snapshot.playlists.playlists,
                        self.repository.default_playlists(),
                    )
                else:
                    self.assertEqual(snapshot.song_stats, {})
                for path, bytes_value in content.items():
                    if path != missing_path:
                        self.assertEqual(path.read_bytes(), bytes_value)
                self.write_complete_documents()

    def test_empty_objects_and_empty_files_follow_compatibility_fallbacks(self) -> None:
        self.write_json(self.library_file, {})
        self.write_json(self.playlists_file, {})
        self.write_json(self.stats_file, {})
        snapshot = self.repository.load_snapshot()
        self.assertEqual(snapshot.library.status, "empty")
        self.assertIn("liked", snapshot.playlists.playlists)
        self.assertEqual(snapshot.song_stats, {})

        for path in (self.library_file, self.playlists_file, self.stats_file):
            path.write_text("", encoding="utf-8")
        empty_file_state = self.file_state(
            (self.library_file, self.playlists_file, self.stats_file)
        )
        snapshot = self.repository.load_snapshot()
        self.assertEqual(snapshot.library.status, "error")
        self.assertTrue(snapshot.library.error)
        self.assertTrue(snapshot.playlists.load_error.startswith("读取歌单失败"))
        self.assertEqual(snapshot.song_stats, {})
        self.assertEqual(
            empty_file_state,
            self.file_state((self.library_file, self.playlists_file, self.stats_file)),
        )

    def test_corrupt_documents_report_existing_compatibility_errors(self) -> None:
        self.library_file.write_text("[", encoding="utf-8")
        self.playlists_file.write_text("[", encoding="utf-8")
        self.stats_file.write_text("[", encoding="utf-8")
        before = self.file_state((self.library_file, self.playlists_file, self.stats_file))

        snapshot = self.repository.load_snapshot()

        self.assertEqual(snapshot.library.status, "error")
        self.assertTrue(snapshot.library.error)
        self.assertTrue(snapshot.playlists.load_error.startswith("读取歌单失败"))
        self.assertEqual(snapshot.song_stats, {})
        self.assertEqual(before, self.file_state((self.library_file, self.playlists_file, self.stats_file)))

    def test_local_song_full_and_missing_fields_preserve_legacy_defaults(self) -> None:
        self.write_json(
            self.library_file,
            [
                {
                    "path": str(self.audio_a),
                    "title": "完整歌曲",
                    "artist": "完整艺人",
                    "album": "完整专辑",
                    "duration": 321,
                    "added_at": "44",
                },
                {"path": str(self.audio_b)},
            ],
        )
        snapshot = self.repository.load_snapshot()

        full, missing = snapshot.library.tracks
        self.assertEqual(full["duration"], 321)
        self.assertEqual(full["added_at"], 44)
        self.assertEqual(missing["title"], "未知歌曲")
        self.assertEqual(missing["artist"], "未知艺术家")
        self.assertEqual(missing["album"], "未知专辑")
        self.assertEqual(missing["added_at"], 0)
        self.assertEqual(missing.get("duration", 0), 0)
        self.assertFalse(missing["demo"])

    def test_windows_path_normalization_matches_legacy_path_resolution(self) -> None:
        redundant_path = str(self.root / "music" / ".." / "music" / self.audio_a.name)
        windows_separator_path = redundant_path.replace("/", "\\")
        self.write_json(
            self.library_file,
            [{"path": windows_separator_path, "title": "路径"}],
        )

        snapshot = self.repository.load_snapshot()

        self.assertEqual(snapshot.library.tracks[0]["path"], str(self.audio_a.resolve()))
        uppercase_path = windows_separator_path.upper()
        self.assertEqual(
            self.repository.normalize_song_path(uppercase_path),
            str(Path(uppercase_path).resolve()),
        )

    def test_missing_local_file_is_skipped_not_marked_available(self) -> None:
        missing_path = self.root / "music" / "gone.mp3"
        self.write_json(
            self.library_file,
            [{"path": str(missing_path), "title": "已失效"}],
        )

        snapshot = self.repository.load_snapshot()

        self.assertEqual(snapshot.library.status, "loaded")
        self.assertEqual(snapshot.library.tracks, ())
        self.assertTrue(snapshot.library.song_list_is_local_only)

    def test_local_duplicates_keep_legacy_order(self) -> None:
        self.write_json(
            self.library_file,
            [
                {"path": str(self.audio_a), "title": "第一个"},
                {"path": str(self.audio_a), "title": "第二个"},
            ],
        )

        tracks = self.repository.load_snapshot().library.tracks

        self.assertEqual([track["title"] for track in tracks], ["第一个", "第二个"])
        self.assertEqual([track["path"] for track in tracks], [str(self.audio_a.resolve())] * 2)

    def test_liked_membership_added_at_and_custom_playlist_order_are_preserved(self) -> None:
        self.write_complete_documents()

        playlists = self.repository.load_snapshot().playlists.playlists
        liked = playlists["liked"]
        member_keys = [
            (member["kind"], member["id"], member["added_at"])
            for member in liked["members"]
        ]
        self.assertEqual(
            member_keys,
            [
                (PlaylistMembership.LOCAL, str(self.audio_a.resolve()), 30),
                (PlaylistMembership.LOCAL, str(self.audio_b.resolve()), 20),
                (PlaylistMembership.REMOTE, "remote_catalog_track-7", 10),
            ],
        )
        self.assertEqual(
            playlists["commute"]["songs"],
            [str(self.audio_b), str(self.audio_a)],
        )
        self.assertEqual(playlists["commute"]["remoteSongs"], ["missing-remote"])
        self.assertEqual(
            [member["id"] for member in playlists["commute"]["members"]],
            [
                str(self.audio_b.resolve()),
                str(self.audio_a.resolve()),
                "missing-remote",
            ],
        )

    def test_stats_and_recent_order_do_not_fabricate_last_played(self) -> None:
        self.write_json(
            self.stats_file,
            {
                str(self.audio_a): {"play_count": 2, "last_played": 100},
                str(self.audio_b): {"play_count": 3, "last_played": 200},
                str(self.root / "music" / "never.mp3"): {"play_count": 1},
            },
        )
        stats = self.repository.load_snapshot().song_stats
        recent_paths = [
            path
            for path, _stats in sorted(
                stats.items(),
                key=lambda item: item[1]["last_played"],
                reverse=True,
            )
        ]

        self.assertEqual(stats[str(self.audio_a.resolve())]["play_count"], 2)
        self.assertEqual(stats[str(self.audio_b.resolve())]["last_played"], 200)
        self.assertEqual(stats[str((self.root / "music" / "never.mp3").resolve())]["last_played"], 0)
        self.assertEqual(recent_paths[:2], [str(self.audio_b.resolve()), str(self.audio_a.resolve())])

    def test_snapshot_is_deeply_independent_and_repository_keeps_no_current_snapshot(self) -> None:
        self.write_complete_documents()
        first_snapshot = self.repository.load_snapshot()
        first_snapshot.library.tracks[0]["title"] = "仅内存"
        first_snapshot.playlists.playlists["liked"]["songs"].append("memory-only")
        first_snapshot.song_stats[str(self.audio_a.resolve())]["play_count"] = 999

        second_snapshot = self.repository.load_snapshot()

        self.assertEqual(second_snapshot.library.tracks[0]["title"], "Alpha")
        self.assertNotIn("memory-only", second_snapshot.playlists.playlists["liked"]["songs"])
        self.assertEqual(second_snapshot.song_stats[str(self.audio_a.resolve())]["play_count"], 2)
        self.assertFalse(hasattr(self.repository, "current_snapshot"))

    def test_snapshot_read_preserves_hash_size_and_last_write_time(self) -> None:
        self.write_complete_documents()
        paths = (self.library_file, self.playlists_file, self.stats_file)
        before = self.file_state(paths)

        self.repository.load_snapshot()

        self.assertEqual(before, self.file_state(paths))

    def test_single_snapshot_opens_each_existing_document_once_and_caches_paths(self) -> None:
        self.write_json(
            self.library_file,
            [
                {"path": str(self.audio_a), "title": "重复一"},
                {"path": str(self.audio_a), "title": "重复二"},
            ],
        )
        self.write_json(
            self.playlists_file,
            {"liked": {"songs": [str(self.audio_a), str(self.audio_a)]}},
        )
        self.write_json(
            self.stats_file,
            {str(self.audio_a): {"play_count": 1}},
        )
        opened: list[Path] = []
        original_open = Path.open

        def record_open(path: Path, *args, **kwargs):
            opened.append(Path(path))
            return original_open(path, *args, **kwargs)

        with patch(
            "app.services.library_repository.Path.open",
            new=record_open,
        ), patch.object(
            LibraryRepository,
            "normalize_song_path",
            wraps=LibraryRepository.normalize_song_path,
        ) as normalize_path:
            self.repository.load_snapshot()

        self.assertEqual(
            Counter(opened),
            Counter({
                self.library_file: 1,
                self.playlists_file: 1,
                self.stats_file: 1,
            }),
        )
        self.assertEqual(normalize_path.call_count, 1)

    def test_remote_track_store_merge_and_stable_identity(self) -> None:
        remote_track = {
            "sourceId": "Catalog-A",
            "id": "track-7",
            "title": "远程歌曲",
            "artist": "远程艺人",
            "album": "远程专辑",
            "duration": 123,
        }
        stable_id = RemoteTrackStore.stable_id_for_track(remote_track)
        existing = {
            "source_id": "Catalog-A",
            "remote_id": "track-7",
            "local_path": str(self.audio_a),
            "downloaded_at": 55,
            "added_at": 44,
        }
        merged_id, merged = RemoteTrackStore.build_record(remote_track, existing=existing)
        online = RemoteTrackStore.to_online_track(merged_id, merged)
        media = MediaItem.from_online(online)

        self.assertEqual(merged_id, stable_id)
        self.assertEqual(merged["local_path"], str(self.audio_a))
        self.assertEqual(merged["downloaded_at"], 55)
        self.assertEqual(merged["added_at"], 44)
        self.assertEqual(media.stable_identity, "remote:catalog-a:track-7")
        self.assertEqual(
            RemoteTrackStore.to_song_data(merged_id, merged, source_available=False)["onlineStatus"],
            "已下载",
        )
        unavailable = dict(merged, local_path="")
        self.assertEqual(
            RemoteTrackStore.to_song_data(
                merged_id,
                unavailable,
                source_available=False,
            )["onlineStatus"],
            "来源不可用",
        )

    def test_remote_duplicates_share_one_stable_store_key(self) -> None:
        duplicate = {
            "sourceId": "catalog",
            "id": "same-track",
            "title": "重复远程歌曲",
        }
        first_id, first = RemoteTrackStore.build_record(duplicate)
        second_id, second = RemoteTrackStore.build_record(duplicate, existing=first)
        remote_file = self.root / "remote_tracks.json"
        self.write_json(
            remote_file,
            {"version": 1, "tracks": {first_id: first, second_id: second}},
        )

        loaded = RemoteTrackStore(remote_file).load_tracks()

        self.assertEqual(first_id, second_id)
        self.assertEqual(list(loaded), [first_id])
        self.assertEqual(len(loaded), 1)

    def test_performance_growth_is_recorded_for_large_deterministic_fixtures(self) -> None:
        measurements = [self.measure_snapshot(count) for count in (100, 1_000, 5_000, 10_000)]
        for measurement in measurements:
            print(
                "[library-repository-perf] "
                f"tracks={measurement['tracks']} playlists={measurement['playlists']} "
                f"json={measurement['json_seconds'] * 1000:.1f}ms "
                f"mapping={measurement['mapping_seconds'] * 1000:.1f}ms "
                f"total={measurement['total_seconds'] * 1000:.1f}ms "
                f"peak={measurement['peak_bytes']}"
            )
        self.assertEqual([item["tracks"] for item in measurements], [100, 1_000, 5_000, 10_000])
        self.assertEqual([item["playlists"] for item in measurements], [5, 5, 5, 5])
        total_1000 = measurements[1]["total_seconds"]
        total_10000 = measurements[3]["total_seconds"]
        # This intentionally loose trend guard catches a clear quadratic regression
        # without turning normal workstation variance into a test failure.
        self.assertLess(total_10000, max(total_1000, 0.001) * 30)

    def measure_snapshot(self, count: int) -> dict[str, float | int]:
        performance_root = self.root / f"perf-{count}"
        performance_root.mkdir()
        audio_file = performance_root / "shared.mp3"
        audio_file.write_bytes(b"fixture")
        library_file = performance_root / "library.json"
        playlists_file = performance_root / "playlists.json"
        stats_file = performance_root / "stats.json"
        library = [
            {
                "path": str(audio_file),
                "title": f"歌曲 {index}",
                "artist": "性能艺人",
                "album": "性能专辑",
                "added_at": index,
                "recordKind": "remote" if index % 10 == 0 else "local",
            }
            for index in range(count)
        ]
        playlists = {
            "liked": {
                "songs": [str(audio_file)] * 3,
                "remoteSongs": ["remote-0", "remote-1", "remote-0"],
            },
            **{
                f"mix-{index}": {
                    "name": f"列表 {index}",
                    "songs": [str(audio_file)] * 20,
                    "remoteSongs": [f"remote-{index}"],
                }
                for index in range(1, 5)
            },
        }
        stats = {
            str(performance_root / "stats" / f"{index}.mp3"): {
                "play_count": index % 7,
                "last_played": index,
            }
            for index in range(count)
        }
        self.write_json(library_file, library)
        self.write_json(playlists_file, playlists)
        self.write_json(stats_file, stats)
        repository = LibraryRepository(library_file, playlists_file, stats_file)
        original_json_load = json.load
        json_seconds = 0.0

        def timed_json_load(*args, **kwargs):
            nonlocal json_seconds
            started_at = time.perf_counter()
            try:
                return original_json_load(*args, **kwargs)
            finally:
                json_seconds += time.perf_counter() - started_at

        started_at = time.perf_counter()
        with patch(
            "app.services.library_repository.json.load",
            side_effect=timed_json_load,
        ):
            snapshot = repository.load_snapshot()
        total_seconds = time.perf_counter() - started_at
        # Measure memory separately so tracing overhead is not reported as
        # normal JSON or mapping time.
        tracemalloc.start()
        repository.load_snapshot()
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "tracks": len(snapshot.library.tracks),
            "playlists": len(snapshot.playlists.playlists),
            "json_seconds": json_seconds,
            "mapping_seconds": max(0.0, total_seconds - json_seconds),
            "total_seconds": total_seconds,
            "peak_bytes": peak_bytes,
        }


if __name__ == "__main__":
    unittest.main()
