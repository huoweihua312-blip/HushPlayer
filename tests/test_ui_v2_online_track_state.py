from __future__ import annotations

import os
import unittest
from dataclasses import replace
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.services.library_repository import LibraryRecords, LibraryRepository, LibrarySnapshot, PlaylistRecords
from app.ui_v2.adapters.real_library_adapter import RealLibraryAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.online_track_model import OnlineTrackModel
from app.ui_v2.models.track import Track
from app.ui_v2.widgets.track_display import present_track_identity_values


def _online_track(
    identity: str,
    *,
    title: str = "夜航",
    artist: str = "林澈",
    album: str = "夜间选集",
    availability: str = "not_resolved",
    favorite: bool = False,
) -> OnlineTrack:
    return OnlineTrack(
        id=identity,
        source_id="fixture",
        source_name="Fixture Source",
        title=title,
        artist=artist,
        album=album,
        duration_ms=None,
        artwork_key=identity,
        quality="标准",
        stable_identity=identity,
        is_favorite=favorite,
        is_downloaded=False,
        is_cached=False,
        availability=availability,
        explicit=False,
        result_rank=0,
    )


class OnlineTrackStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.collection = LibraryCollectionAdapter((), read_only=False)
        self.playlists = PlaylistAdapter(self.collection, seed_mock=False)
        self.adapter = OnlineAdapter(
            self.collection,
            self.playlists,
            timer_enabled=False,
        )
        self.first = _online_track("fixture:first")
        self.second = _online_track("fixture:second", title="另一首")
        self.adapter._results = (self.first, self.second)
        self.adapter.search_results_changed.emit(self.adapter.results())

    def test_unknown_and_not_resolved_have_no_error_presentation(self) -> None:
        for state in ("unknown", "not_resolved", "available", "playable"):
            identity = present_track_identity_values(
                "歌曲",
                "歌手",
                "专辑",
                is_online=True,
                availability=state,
            )
            self.assertFalse(identity.availability.is_confirmed_error)
            self.assertFalse(identity.availability.is_visible)

    def test_resolving_is_visible_but_not_error(self) -> None:
        identity = present_track_identity_values(
            "歌曲",
            "歌手",
            "专辑",
            is_online=True,
            availability="resolving",
        )
        self.assertTrue(identity.availability.is_resolving)
        self.assertFalse(identity.availability.is_confirmed_error)
        self.assertEqual(identity.availability.label, "解析中")

    def test_confirmed_failure_states_are_independent_from_metadata(self) -> None:
        identity = present_track_identity_values(
            "Умри если меня не любишь",
            "123",
            "",
            is_online=True,
            availability="resolve_failed",
            playback_detail="来源返回了不可播放媒体。",
        )
        self.assertTrue(identity.availability.is_confirmed_error)
        self.assertEqual(identity.metadata, "123")
        self.assertIn("不可播放媒体", identity.availability.tooltip)

    def test_resolution_failure_is_retryable_but_source_failure_is_blocked(self) -> None:
        failed = present_track_identity_values(
            "歌曲",
            "歌手",
            "专辑",
            is_online=True,
            availability="resolve_failed",
        )
        unavailable = present_track_identity_values(
            "歌曲",
            "歌手",
            "专辑",
            is_online=True,
            availability="source_unavailable",
        )
        self.assertTrue(failed.availability.is_retryable)
        self.assertFalse(unavailable.availability.is_retryable)

    def test_request_play_moves_only_target_to_resolving(self) -> None:
        self.assertTrue(self.adapter.request_play(self.first.id))
        self.assertEqual(self.adapter.results()[0].availability, "resolving")
        self.assertEqual(self.adapter.results()[1].availability, "not_resolved")
        self.assertEqual(self.collection.track_for_id(self.first.id).availability, "resolving")

    def test_request_play_retries_resolution_failure_and_clears_old_detail(self) -> None:
        self.adapter.apply_remote_state(
            self.first.stable_identity,
            "resolve_failed",
            "在线来源响应失败，请稍后重试。",
        )
        self.assertTrue(self.adapter.request_play(self.first.id))
        updated = self.adapter.results()[0]
        self.assertEqual(updated.availability, "resolving")
        self.assertEqual(updated.availability_detail, "")

    def test_incremental_formal_results_preserve_runtime_availability(self) -> None:
        self.adapter._formal_generation = 1
        self.adapter._query = "状态保持"
        self.adapter.apply_remote_state(
            self.first.stable_identity,
            "resolving",
            "正在解析在线播放地址…",
        )

        raw = {
            "sourceId": "fixture",
            "id": self.first.id,
            "title": self.first.title,
            "artist": self.first.artist,
            "album": self.first.album,
        }
        self.adapter._on_formal_results(
            1,
            "状态保持",
            [raw],
            {"final": False, "pendingCount": 1, "sources": []},
        )

        updated = self.adapter.results()[0]
        self.assertEqual(updated.availability, "resolving")
        self.assertEqual(updated.availability_detail, "正在解析在线播放地址…")

    def test_source_unavailable_stays_blocked(self) -> None:
        self.adapter._replace_result(replace(self.first, availability="source_unavailable"))
        self.assertFalse(self.adapter.request_play(self.first.id))

    def test_resolve_success_updates_metadata_duration_and_collection(self) -> None:
        self.adapter.request_play(self.first.id)
        updated = self.adapter.apply_remote_state(
            self.first.stable_identity,
            "playable",
            "在线播放地址已准备。",
            {"album": "真实专辑", "artwork": "cover:updated"},
            duration_ms=183_000,
        )
        self.assertIsNotNone(updated)
        result = self.adapter.results()[0]
        self.assertEqual(result.availability, "playable")
        self.assertEqual(result.album, "真实专辑")
        self.assertEqual(result.duration_ms, 183_000)
        collection_track = self.collection.track_for_id(self.first.id)
        self.assertEqual(collection_track.album, "真实专辑")
        self.assertEqual(collection_track.duration_ms, 183_000)
        self.assertFalse(collection_track.is_missing)

    def test_empty_enrichment_does_not_clear_existing_metadata(self) -> None:
        self.adapter.apply_remote_state(
            self.first.stable_identity,
            "playable",
            payload={"album": "真实专辑", "artist": "林澈"},
            duration_ms=180_000,
        )
        self.adapter.apply_remote_state(
            self.first.stable_identity,
            "playable",
            payload={"album": "", "artist": ""},
        )
        result = self.adapter.results()[0]
        self.assertEqual(result.album, "真实专辑")
        self.assertEqual(result.artist, "林澈")
        self.assertEqual(result.duration_ms, 180_000)

    def test_one_track_failure_does_not_pollute_other_track(self) -> None:
        self.adapter.apply_remote_state(
            self.first.stable_identity,
            "resolve_failed",
            "当前歌曲没有可播放媒体。",
        )
        self.assertEqual(self.adapter.results()[0].availability, "resolve_failed")
        self.assertEqual(self.adapter.results()[1].availability, "not_resolved")
        self.assertFalse(self.adapter.results()[1].as_track().is_missing)

    def test_stable_identity_round_trip_has_no_old_state_residue(self) -> None:
        self.adapter.apply_remote_state(self.first.stable_identity, "resolving")
        self.adapter.apply_remote_state(self.second.stable_identity, "playable", duration_ms=200_000)
        self.adapter.apply_remote_state(
            self.first.stable_identity,
            "playable",
            payload={"title": "第一首恢复", "album": "恢复专辑"},
            duration_ms=190_000,
        )
        first, second = self.adapter.results()
        self.assertEqual(first.title, "第一首恢复")
        self.assertEqual(first.album, "恢复专辑")
        self.assertEqual(first.duration_ms, 190_000)
        self.assertEqual(first.availability, "playable")
        self.assertEqual(second.duration_ms, 200_000)
        self.assertEqual(second.availability, "playable")

    def test_favorite_state_is_independent_from_availability(self) -> None:
        self.adapter._replace_result(replace(self.first, is_favorite=True))
        self.adapter.apply_remote_state(self.first.stable_identity, "resolve_failed")
        updated = self.adapter.results()[0]
        self.assertTrue(updated.is_favorite)
        self.assertEqual(updated.availability, "resolve_failed")

    def test_read_only_collection_accepts_runtime_refresh_without_persistence_write(self) -> None:
        collection = LibraryCollectionAdapter((self.first.as_track(),), read_only=True)
        playlists = PlaylistAdapter(collection, seed_mock=False, read_only=True)
        adapter = OnlineAdapter(collection, playlists, timer_enabled=False)
        adapter.apply_remote_state(self.first.stable_identity, "resolving")
        updated = collection.track_for_id(self.first.id)
        self.assertEqual(updated.availability, "resolving")
        self.assertTrue(updated.is_loading)

    def test_local_track_is_not_touched_by_remote_state(self) -> None:
        local = Track(
            id="local",
            title="本地",
            artist="本地艺人",
            album="本地专辑",
            duration_ms=100_000,
            source_id="local",
            source_name="本地音乐",
            source_type="local",
            added_at=datetime(2026, 8, 9),
            is_favorite=False,
            is_missing=False,
            is_loading=False,
            artwork_path=None,
            stable_identity="local:one",
            local_path="C:/music/local.mp3",
        )
        self.collection.upsert_track(local)
        self.adapter.apply_remote_state(self.first.stable_identity, "playable", duration_ms=180_000)
        self.assertEqual(self.collection.track_for_id("local").duration_ms, 100_000)

    def test_online_model_keeps_unknown_resolving_and_retryable_selectable(self) -> None:
        model = OnlineTrackModel(
            (
                _online_track("unknown", availability="not_resolved"),
                _online_track("resolving", availability="resolving"),
                _online_track("failed", availability="resolve_failed"),
            )
        )
        for row in (0, 1, 2):
            self.assertTrue(model.flags(model.index(row, 1)) & Qt.ItemFlag.ItemIsEnabled)
        blocked = OnlineTrackModel(
            (_online_track("blocked", availability="source_unavailable"),)
        )
        self.assertFalse(blocked.flags(blocked.index(0, 1)) & Qt.ItemFlag.ItemIsEnabled)

    def test_persisted_remote_membership_starts_not_resolved(self) -> None:
        snapshot = LibrarySnapshot(
            LibraryRecords((), "loaded", "", True),
            PlaylistRecords(LibraryRepository.default_playlists(), "", False),
            {},
        )
        data = RealLibraryAdapter.map_snapshot(
            snapshot,
            {
                "remote_fixture": {
                    "source_id": "fixture",
                    "remote_id": "one",
                    "title": "收藏在线歌曲",
                    "artist": "艺人",
                    "album": "专辑",
                    "duration": 0,
                    "local_path": "",
                }
            },
        )
        track = data.tracks[0]
        self.assertEqual(track.availability, "not_resolved")
        self.assertFalse(track.is_missing)


if __name__ == "__main__":
    unittest.main()
