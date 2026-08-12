from __future__ import annotations

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.services.library_repository import LibraryRepository
from app.services.online_discovery_bridge import OnlineDiscoveryBridge
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter


class FakeSourceClient(QObject):
    metadataFinished = Signal(int, str, dict)
    requestFailed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self._next_request = 1
        self.metadata_requests: list[tuple[int, str, dict]] = []

    def get_metadata(self, source_id: str, track: dict) -> int:
        request_id = self._next_request
        self._next_request += 1
        self.metadata_requests.append((request_id, source_id, dict(track)))
        return request_id

    def emit_metadata(self, request_id: int, source_id: str, metadata: dict) -> None:
        self.metadataFinished.emit(request_id, source_id, dict(metadata))


class FakeSearchService(QObject):
    resultsChanged = Signal(int, str, list, dict)
    sourceCatalogChanged = Signal(list, list)
    statusChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.generation = 0
        self.keyword = ""
        self.selected_source_ids: list[str] = []

    def ensure_source_catalog(self) -> int:
        self.sourceCatalogChanged.emit(
            [
                {
                    "id": "north",
                    "name": "North Source",
                    "selectable": True,
                    "capabilities": {"search": True, "playback": True},
                },
                {
                    "id": "south",
                    "name": "South Source",
                    "selectable": True,
                    "capabilities": {"search": True, "playback": False},
                },
            ],
            ["north", "south"],
        )
        return 0

    def schedule_search(self, keyword: str, local_only: bool = False) -> int:
        self.generation += 1
        self.keyword = str(keyword or "").strip()
        self.resultsChanged.emit(
            self.generation,
            self.keyword,
            [],
            {"final": False, "pendingCount": 1, "sources": [], "errors": {}},
        )
        return self.generation

    def set_selected_source_ids(self, source_ids, *, restart: bool = True) -> list[str]:
        self.selected_source_ids = list(source_ids)
        return list(self.selected_source_ids)

    def emit_results(self, results: list[dict], *, generation: int | None = None) -> None:
        current = self.generation if generation is None else generation
        self.resultsChanged.emit(
            current,
            self.keyword,
            list(results),
            {
                "final": True,
                "pendingCount": 0,
                "sources": [
                    {
                        "sourceId": "north",
                        "sourceName": "North Source",
                        "status": "success",
                        "resultCount": len(results),
                        "message": "",
                    }
                ],
                "errors": {},
            },
        )

    def shutdown(self) -> None:
        return None


class FakeArtworkService(QObject):
    imageReady = Signal(int, str, bytes)
    failed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.generation = 0
        self.requests = []

    def request_many(self, requests) -> int:
        self.generation += 1
        self.requests = list(requests)
        return self.generation

    def cancel(self) -> None:
        return None


class FakeBridge:
    def __init__(self) -> None:
        self.favorites: list[tuple[str, bool]] = []
        self.playlists: list[tuple[str, str]] = []

    def set_favorite(self, track: dict, liked: bool) -> bool:
        self.favorites.append((str(track.get("remote_id") or ""), bool(liked)))
        return True

    def add_to_playlist(self, track: dict, playlist_id: str) -> bool:
        self.playlists.append((str(track.get("remote_id") or ""), str(playlist_id)))
        return True


class OnlineDiscoveryQ5ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.client = FakeSourceClient()
        self.search = FakeSearchService()
        self.artwork = FakeArtworkService()
        self.bridge = FakeBridge()
        self.discovery = SimpleNamespace(
            client=self.client,
            search_service=self.search,
            artwork_service=self.artwork,
            bridge=self.bridge,
        )
        collection = LibraryCollectionAdapter((), read_only=True)
        playlists = PlaylistAdapter(collection, seed_mock=False, read_only=True)
        self.adapter = OnlineAdapter(collection, playlists, timer_enabled=False, discovery=self.discovery)

    @staticmethod
    def _make_formal_adapter():
        client = FakeSourceClient()
        search = FakeSearchService()
        artwork = FakeArtworkService()
        bridge = FakeBridge()
        discovery = SimpleNamespace(
            client=client,
            search_service=search,
            artwork_service=artwork,
            bridge=bridge,
        )
        collection = LibraryCollectionAdapter((), read_only=True)
        playlists = PlaylistAdapter(collection, seed_mock=False, read_only=True)
        adapter = OnlineAdapter(collection, playlists, timer_enabled=False, discovery=discovery)
        return adapter, client, search, artwork

    def _search(self) -> int:
        self.adapter.set_query("夜航")
        return self.search.generation

    def _results(self) -> list[dict]:
        return [
            {
                "id": "same-id",
                "sourceId": "north",
                "sourceName": "North Source",
                "title": "夜航",
                "artist": "林澈",
                "album": "North",
                "duration": 180,
                "artworkUrl": "https://example.test/north.jpg",
            },
            {
                "id": "same-id",
                "sourceId": "south",
                "sourceName": "South Source",
                "title": "夜航",
                "artist": "林澈",
                "album": "South",
                "duration": 181,
                "artworkUrl": "https://example.test/south.jpg",
            },
        ]

    def test_stable_identity_and_stale_generation(self) -> None:
        first = self._search()
        self.search.emit_results(self._results(), generation=first)
        tracks = self.adapter.results()
        self.assertEqual(len(tracks), 2)
        self.assertEqual(len({track.id for track in tracks}), 2)
        self.assertEqual(len({track.stable_identity for track in tracks}), 2)
        self.assertEqual(
            [track.availability for track in tracks],
            ["not_resolved", "source_unavailable"],
        )
        self.adapter.set_query("新查询")
        second = self.search.generation
        self.search.emit_results(self._results(), generation=first)
        self.assertEqual(self.adapter.state.generation, second)
        self.assertFalse(self.adapter.results())

    def test_keyed_artwork_metadata_and_remote_actions(self) -> None:
        generation = self._search()
        self.search.emit_results(self._results(), generation=generation)
        track = self.adapter.results()[0]
        self.assertEqual(self.artwork.requests[0][0], track.id)
        self.artwork.imageReady.emit(self.artwork.generation, track.id, b"image")
        updated = self.adapter.results()[0]
        self.assertEqual(updated.id, track.id)
        self.assertEqual(updated.artwork_data, b"image")

        self.assertTrue(self.adapter.request_metadata(track.id))
        request_id = self.client.metadata_requests[0][0]
        self.client.emit_metadata(request_id, track.source_id, {"title": "夜航（更新）"})
        self.assertEqual(self.adapter.results()[0].title, "夜航（更新）")

        self.adapter.toggle_favorite(track.id)
        self.assertEqual(self.bridge.favorites, [(track.remote_id, True)])
        self.assertTrue(self.adapter.request_add_to_playlist(track.id, "playlist-1"))
        self.assertEqual(self.bridge.playlists, [(track.remote_id, "playlist-1")])

    def test_playable_remote_track_leaves_the_unavailable_boundary(self) -> None:
        played = []
        self.adapter.play_requested.connect(played.append)
        generation = self._search()
        self.search.emit_results(self._results(), generation=generation)
        track = self.adapter.results()[0]
        self.assertTrue(self.adapter.request_play(track.id))
        self.assertEqual(played[0].stable_identity, track.stable_identity)

    def test_formal_bridge_preserves_remote_membership_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            playlists_path = root / "playlists.json"
            playlists_path.write_text(
                json.dumps(
                    {
                        "liked": {
                            "name": "我喜欢",
                            "songs": [],
                            "remoteSongs": [],
                            "fixed": True,
                        },
                        "playlist-1": {
                            "name": "夜航",
                            "songs": [],
                            "remoteSongs": [],
                            "fixed": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            repository = LibraryRepository(
                root / "library.json",
                playlists_path,
                root / "stats.json",
            )
            remote_store = RemoteTrackStore(root / "remote_tracks.json")
            bridge = OnlineDiscoveryBridge(repository, remote_store)
            payload = {
                "source_id": "north",
                "remote_id": "same-id",
                "title": "夜航",
                "artist": "林澈",
                "album": "North",
            }
            stable_id, _record = bridge.persist_track(payload)
            self.assertTrue(stable_id.startswith("remote_"))
            self.assertIn(stable_id, remote_store.load_tracks())
            self.assertTrue(bridge.set_favorite(payload, True))
            self.assertTrue(bridge.add_to_playlist(payload, "playlist-1"))
            document = json.loads(playlists_path.read_text(encoding="utf-8"))
            self.assertEqual(document["liked"]["remoteSongs"], [stable_id])
            self.assertEqual(document["playlist-1"]["remoteSongs"], [stable_id])
            self.assertTrue(bridge.set_favorite(payload, False))
            document = json.loads(playlists_path.read_text(encoding="utf-8"))
            self.assertEqual(document["liked"]["remoteSongs"], [])

    def test_formal_bridge_replaces_track_memberships_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_path = (root / "missing.mp3").resolve()
            replacement = {
                "source_id": "north",
                "remote_id": "replacement-id",
                "title": "替代歌曲",
                "artist": "在线歌手",
                "album": "在线专辑",
                "duration": 180_000,
            }
            stable_id = RemoteTrackStore.stable_id_for_track(replacement)
            playlists_path = root / "playlists.json"
            playlists_path.write_text(
                json.dumps(
                    {
                        "liked": {
                            "name": "我喜欢",
                            "songs": [str(old_path)],
                            "remoteSongs": [],
                            "members": [
                                {"kind": "local", "id": str(old_path), "added_at": 300}
                            ],
                            "membershipVersion": 1,
                            "fixed": True,
                        },
                        "road": {
                            "name": "通勤",
                            "songs": [str(old_path), "other.mp3"],
                            "remoteSongs": [],
                            "members": [
                                {"kind": "local", "id": str(old_path), "added_at": 500},
                                {"kind": "local", "id": "other.mp3", "added_at": 400},
                            ],
                            "membershipVersion": 1,
                            "fixed": False,
                            "vendorExtension": {"keep": True},
                        },
                        "already": {
                            "name": "已有在线版本",
                            "songs": [str(old_path)],
                            "remoteSongs": [stable_id],
                            "members": [
                                {"kind": "local", "id": str(old_path), "added_at": 700},
                                {"kind": "remote", "id": stable_id, "added_at": 200},
                            ],
                            "membershipVersion": 1,
                            "fixed": False,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            repository = LibraryRepository(
                root / "library.json",
                playlists_path,
                root / "stats.json",
            )
            remote_store = RemoteTrackStore(root / "remote_tracks.json")
            bridge = OnlineDiscoveryBridge(repository, remote_store)

            result = bridge.replace_track_memberships(("local", str(old_path)), replacement)

            self.assertEqual(result, OnlineDiscoveryBridge.REPLACED)
            document = json.loads(playlists_path.read_text(encoding="utf-8"))
            self.assertEqual(document["liked"]["songs"], [])
            self.assertEqual(document["liked"]["remoteSongs"], [stable_id])
            self.assertEqual(
                document["liked"]["members"],
                [{"kind": "remote", "id": stable_id, "added_at": 300}],
            )
            self.assertEqual(document["road"]["songs"], ["other.mp3"])
            self.assertEqual(document["road"]["remoteSongs"], [stable_id])
            self.assertEqual(document["road"]["members"][0]["id"], stable_id)
            self.assertEqual(document["road"]["members"][0]["added_at"], 500)
            self.assertEqual(document["road"]["vendorExtension"], {"keep": True})
            self.assertEqual(document["already"]["remoteSongs"], [stable_id])
            self.assertEqual(
                [member["id"] for member in document["already"]["members"]],
                [stable_id],
            )
            self.assertIn(stable_id, remote_store.load_tracks())

    def test_rapid_query_generation_replacement_100_cycles(self) -> None:
        previous_generation = 0
        for index in range(100):
            self.adapter.set_query(f"夜航 {index}")
            generation = self.search.generation
            if previous_generation:
                self.search.emit_results(self._results(), generation=previous_generation)
                self.assertEqual(self.adapter.state.generation, generation)
            self.search.emit_results(self._results(), generation=generation)
            self.assertEqual(self.adapter.state.generation, generation)
            self.assertTrue(self.adapter.results())
            previous_generation = generation

    def test_pending_metadata_and_artwork_are_ignored_after_shutdown_50_cycles(self) -> None:
        for _index in range(50):
            adapter, client, search, artwork = self._make_formal_adapter()
            adapter.set_query("夜航")
            generation = search.generation
            search.emit_results(self._results(), generation=generation)
            track = adapter.results()[0]
            adapter.request_metadata(track.id)
            request_id = client.metadata_requests[0][0]
            adapter.shutdown()
            client.emit_metadata(request_id, track.source_id, {"title": "过期信息"})
            artwork.imageReady.emit(artwork.generation, track.id, b"late")
            self.assertEqual(adapter.results()[0].title, track.title)
            self.assertEqual(adapter.results()[0].artwork_data, b"")


if __name__ == "__main__":
    unittest.main()
