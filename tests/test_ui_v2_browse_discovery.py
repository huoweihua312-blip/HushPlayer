import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.browse_discovery import BrowseDiscoveryAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.online_track import OnlineTrack


class BrowseDiscoveryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.collection = LibraryCollectionAdapter(create_mock_tracks(80))
        self.playlists = PlaylistAdapter(self.collection)
        self.online = OnlineAdapter(
            self.collection,
            self.playlists,
            timer_enabled=False,
        )
        self.adapter = BrowseDiscoveryAdapter(
            self.collection,
            self.playlists,
            self.online,
        )

    def tearDown(self) -> None:
        self.adapter.shutdown()
        self.online.shutdown()
        self.adapter.deleteLater()
        self.online.deleteLater()
        self.app.processEvents()

    def test_browse_snapshot_includes_online_collection_and_playlist_reason(self) -> None:
        snapshot = self.adapter.snapshot

        self.assertEqual(len(snapshot.recent_added), 5)
        self.assertEqual(len(snapshot.recommended), 5)
        self.assertEqual(len(snapshot.recent_played), 5)
        self.assertTrue(any(track.is_online for track in snapshot.recent_added))
        self.assertTrue(snapshot.recommendation_reason.startswith("来自歌单："))

    def test_recommendations_are_stable_until_inputs_change(self) -> None:
        first = tuple(track.stable_id for track in self.adapter.snapshot.recommended)
        self.adapter.refresh()
        second = tuple(track.stable_id for track in self.adapter.snapshot.recommended)

        self.assertEqual(first, second)

    def test_recommendations_reserve_visible_slots_for_new_online_tracks(self) -> None:
        saved = tuple(self.collection.tracks()[:5])
        online = tuple(
            OnlineTrack(
                id=f"recommendation-only-{index}",
                source_id="qq",
                source_name="QQ音乐",
                title=f"在线推荐 {index}",
                artist="推荐歌手",
                album="推荐专辑",
                duration_ms=180000,
                artwork_key=f"recommendation-only-{index}",
                quality="标准",
                stable_identity=f"qq:recommendation-only-{index}",
                is_favorite=False,
                is_downloaded=False,
                is_cached=False,
                availability="unresolved",
                explicit=False,
                result_rank=index,
            )
            for index in range(3)
        )

        merged = self.adapter._merge_recommendations(saved, online)

        self.assertEqual(len(merged), 5)
        self.assertGreaterEqual(sum(track.is_online for track in merged), 3)
        self.assertTrue(
            any(track.stable_id == "qq:recommendation-only-0" for track in merged)
        )

    def test_online_track_can_enter_existing_playlist_action_path(self) -> None:
        playlist = self.playlists.playlists()[0]
        source = next(
            track
            for track in self.collection.tracks()
            if track.is_online and track.id not in playlist.track_ids
        )
        remote = self.online.ensure_actionable_track(source)

        self.assertIsNotNone(remote)
        self.assertTrue(self.online.request_add_to_playlist(remote.id, playlist.id))
        self.assertIn(source.id, self.playlists.playlist_for_id(playlist.id).track_ids)


if __name__ == "__main__":
    unittest.main()
