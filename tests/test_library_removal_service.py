from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.services.library_removal_service import LibraryRemovalService
from app.services.library_repository import LibraryRepository
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.models.track import Track


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _local_track(path: Path) -> Track:
    return Track(
        id=f"local:{str(path.resolve()).casefold()}",
        title="待删除歌曲",
        artist="测试歌手",
        album="测试专辑",
        duration_ms=180_000,
        source_id="local",
        source_name="本地音乐",
        source_type="local",
        added_at=datetime(2026, 1, 1, 12, 0),
        is_favorite=True,
        is_missing=False,
        is_loading=False,
        artwork_path=None,
        stable_identity=f"local:{str(path.resolve()).casefold()}",
        local_path=str(path.resolve()),
    )


def _online_track(stable_id: str, source_id: str, remote_id: str) -> Track:
    return Track(
        id=stable_id,
        title="在线待删除歌曲",
        artist="测试歌手",
        album="测试专辑",
        duration_ms=180_000,
        source_id=source_id,
        source_name="测试来源",
        source_type="online",
        added_at=datetime(2026, 1, 1, 12, 0),
        is_favorite=True,
        is_missing=False,
        is_loading=False,
        artwork_path=None,
        stable_identity=stable_id,
        availability="playable",
        remote_identity=stable_id,
        remote_track_id=remote_id,
        remote_payload={"id": remote_id, "sourceId": source_id},
    )


class LibraryRemovalServiceTests(unittest.TestCase):
    def test_local_removal_trashes_file_and_cleans_library_playlists_and_stats(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer-remove-local-") as directory:
            root = Path(directory)
            removed_file = root / "music" / "remove.mp3"
            kept_file = root / "music" / "keep.mp3"
            removed_file.parent.mkdir(parents=True)
            removed_file.write_bytes(b"remove")
            kept_file.write_bytes(b"keep")
            library_path = root / "library.json"
            playlists_path = root / "playlists.json"
            stats_path = root / "stats.json"
            remote_path = root / "remote_tracks.json"
            removed_path = str(removed_file.resolve())
            kept_path = str(kept_file.resolve())
            _write_json(
                library_path,
                [
                    {"path": removed_path, "title": "删除", "unknown": {"keep": False}},
                    {"path": kept_path, "title": "保留", "unknown": {"keep": True}},
                ],
            )
            _write_json(
                playlists_path,
                {
                    "liked": {
                        "name": "我喜欢",
                        "songs": [removed_path, kept_path],
                        "remoteSongs": [],
                        "members": [
                            {"kind": "local", "id": removed_path, "added_at": 1},
                            {"kind": "local", "id": kept_path, "added_at": 2},
                        ],
                        "fixed": True,
                    },
                    "road": {
                        "name": "通勤",
                        "songs": [removed_path],
                        "remoteSongs": [],
                        "members": [
                            {"kind": "local", "id": removed_path, "added_at": 3},
                        ],
                        "vendorExtension": {"keep": True},
                    },
                },
            )
            _write_json(stats_path, {removed_path: {"play_count": 5}, kept_path: {"play_count": 2}})
            repository = LibraryRepository(library_path, playlists_path, stats_path)
            remote_store = RemoteTrackStore(remote_path)
            trashed: list[Path] = []

            def trash(path: Path) -> bool:
                trashed.append(Path(path))
                Path(path).unlink()
                return True

            result = LibraryRemovalService(
                repository,
                remote_store,
                file_to_trash=trash,
            ).remove_track(_local_track(removed_file))

            self.assertTrue(result.success)
            self.assertEqual(trashed, [removed_file])
            self.assertFalse(removed_file.exists())
            self.assertTrue(kept_file.exists())
            library = json.loads(library_path.read_text(encoding="utf-8"))
            self.assertEqual([entry["path"] for entry in library], [kept_path])
            self.assertEqual(library[0]["unknown"], {"keep": True})
            playlists = json.loads(playlists_path.read_text(encoding="utf-8"))
            self.assertEqual(playlists["liked"]["songs"], [kept_path])
            self.assertEqual(
                [member["id"] for member in playlists["liked"]["members"]],
                [kept_path],
            )
            self.assertEqual(playlists["road"]["songs"], [])
            self.assertEqual(playlists["road"]["members"], [])
            self.assertEqual(playlists["road"]["vendorExtension"], {"keep": True})
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            self.assertNotIn(removed_path, stats)
            self.assertIn(kept_path, stats)

    def test_failed_trash_preserves_all_documents_and_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer-remove-failure-") as directory:
            root = Path(directory)
            audio_file = root / "remove.mp3"
            audio_file.write_bytes(b"remove")
            library_path = root / "library.json"
            playlists_path = root / "playlists.json"
            stats_path = root / "stats.json"
            remote_path = root / "remote_tracks.json"
            audio_path = str(audio_file.resolve())
            _write_json(library_path, [{"path": audio_path, "title": "删除"}])
            _write_json(
                playlists_path,
                {
                    "liked": {
                        "name": "我喜欢",
                        "songs": [audio_path],
                        "remoteSongs": [],
                        "members": [{"kind": "local", "id": audio_path, "added_at": 1}],
                        "fixed": True,
                    }
                },
            )
            _write_json(stats_path, {audio_path: {"play_count": 1}})
            before = {
                path: path.read_bytes()
                for path in (library_path, playlists_path, stats_path)
            }
            repository = LibraryRepository(library_path, playlists_path, stats_path)
            result = LibraryRemovalService(
                repository,
                RemoteTrackStore(remote_path),
                file_to_trash=lambda _path: False,
            ).remove_track(_local_track(audio_file))

            self.assertFalse(result.success)
            self.assertTrue(audio_file.exists())
            self.assertEqual(
                before,
                {path: path.read_bytes() for path in before},
            )

    def test_online_removal_deletes_record_memberships_and_cache(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hushplayer-remove-online-") as directory:
            root = Path(directory)
            library_path = root / "library.json"
            playlists_path = root / "playlists.json"
            stats_path = root / "stats.json"
            remote_path = root / "remote_tracks.json"
            _write_json(library_path, [])
            _write_json(stats_path, {})
            stable_id, record = RemoteTrackStore.build_record(
                {
                    "source_id": "catalog",
                    "remote_id": "remote-1",
                    "title": "在线待删除歌曲",
                }
            )
            remote_store = RemoteTrackStore(remote_path)
            remote_store.save_tracks({stable_id: record})
            _write_json(
                playlists_path,
                {
                    "liked": {
                        "name": "我喜欢",
                        "songs": [],
                        "remoteSongs": [stable_id],
                        "members": [{"kind": "remote", "id": stable_id, "added_at": 1}],
                        "fixed": True,
                    }
                },
            )
            deleted_values: list[dict] = []

            class FakeCache:
                def delete_cache(self, value):
                    deleted_values.append(dict(value))
                    return {"removed": 1, "skipped": 0, "bytes": 1024}

            result = LibraryRemovalService(
                LibraryRepository(library_path, playlists_path, stats_path),
                remote_store,
                online_audio_cache=FakeCache(),
                file_to_trash=lambda _path: True,
            ).remove_track(_online_track(stable_id, "catalog", "remote-1"))

            self.assertTrue(result.success)
            self.assertNotIn(stable_id, remote_store.load_tracks())
            playlists = json.loads(playlists_path.read_text(encoding="utf-8"))
            self.assertEqual(playlists["liked"]["remoteSongs"], [])
            self.assertEqual(playlists["liked"]["members"], [])
            self.assertEqual(len(deleted_values), 1)
            self.assertEqual(deleted_values[0]["remote_stable_id"], stable_id)


if __name__ == "__main__":
    unittest.main()
