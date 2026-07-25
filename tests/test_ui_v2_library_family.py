from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.adapters.artists_adapter import ArtistsAdapter, UNKNOWN_ALBUM, UNKNOWN_ARTIST
from app.ui_v2.adapters.favorites_adapter import FavoritesAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.adapters.recent_adapter import RecentAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.track_table_model import PLAYING_ROLE, TrackColumn
from app.ui_v2.pages.album_detail_page import AlbumDetailPage
from app.ui_v2.pages.albums_page import AlbumsPage
from app.ui_v2.pages.artist_detail_page import ArtistDetailPage
from app.ui_v2.pages.artists_page import ArtistsPage
from app.ui_v2.pages.favorites_page import FavoritesPage
from app.ui_v2.pages.playlist_page import PlaylistPage
from app.ui_v2.pages.recent_page import RecentPage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme


class UiV2LibraryFamilyAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = LibraryCollectionAdapter(create_mock_tracks(1000))
        self.playlists = PlaylistAdapter(self.collection)

    def test_favorites_filter_latest_order_and_immediate_removal(self) -> None:
        adapter = FavoritesAdapter(self.collection)
        tracks = adapter.tracks()
        self.assertTrue(tracks)
        self.assertTrue(all(track.is_favorite for track in tracks))
        timestamps = [self.collection.favorite_at(track.id) for track in tracks]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))
        track = tracks[0]
        self.collection.set_favorite(track.id, False)
        self.assertNotIn(track.id, [item.id for item in adapter.tracks()])

    def test_favorites_keep_view_local_query_and_sort_state(self) -> None:
        adapter = FavoritesAdapter(self.collection)
        adapter.set_query("Paper Moon")
        adapter.set_sort(TrackColumn.TITLE, Qt.SortOrder.AscendingOrder)
        self.assertEqual(adapter.query, "Paper Moon")
        self.assertEqual(adapter.sort_column, TrackColumn.TITLE)
        self.assertEqual(adapter.sort_order, Qt.SortOrder.AscendingOrder)

    def test_recent_merges_repeated_play_counts_and_clears_without_tracks(self) -> None:
        track = next(track for track in self.collection.tracks() if not track.is_missing)
        recent = RecentAdapter(self.collection)
        self.collection.record_play(track.id, 1200)
        self.collection.record_play(track.id, 3400)
        entry = self.collection.recent_for_track(track.id)
        self.assertEqual(len(self.collection.recent_entries()), 1)
        self.assertEqual(entry.play_count, 2)
        self.assertEqual(entry.last_position_ms, 3400)
        self.assertEqual([item.id for item in recent.tracks()], [track.id])
        recent.clear()
        self.assertFalse(recent.tracks())
        self.assertIsNotNone(self.collection.track_for_id(track.id))

    def test_playlist_crud_membership_dedup_and_navigation_share_one_source(self) -> None:
        navigation = NavigationAdapter(self.playlists)
        playlist = navigation.create_playlist("测试歌单")
        self.assertIs(self.playlists.playlist_for_id(playlist.id), navigation.playlists()[-1])
        self.assertTrue(navigation.rename_playlist(playlist.id, "重命名歌单"))
        self.assertEqual(
            next(item for item in navigation.playlists() if item.id == playlist.id).name,
            "重命名歌单",
        )
        tracks = [track.id for track in self.collection.tracks() if not track.is_missing][:6]
        self.assertEqual(self.playlists.add_tracks(playlist.id, tracks + tracks), len(tracks))
        self.assertEqual(self.playlists.add_tracks(playlist.id, tracks), 0)
        self.assertEqual(
            [track.id for track in self.playlists.tracks_for_playlist(playlist.id)],
            list(reversed(tracks)),
        )
        self.assertTrue(self.playlists.remove_track(playlist.id, tracks[0]))
        self.assertNotIn(tracks[0], self.playlists.playlist_for_id(playlist.id).track_ids)
        navigation.set_route(f"playlist:{playlist.id}")
        self.assertTrue(navigation.delete_playlist(playlist.id))
        self.assertEqual(navigation.route, "library")
        self.assertIsNotNone(self.collection.track_for_id(tracks[0]))

    def test_playlist_bulk_add_uses_unique_member_count(self) -> None:
        playlist = self.playlists.create_playlist("批量")
        track_ids = [track.id for track in self.collection.tracks() if not track.is_missing]
        requested = track_ids[:300] + track_ids[:120] + ["missing-track"]
        self.assertEqual(self.playlists.add_tracks(playlist.id, requested), 300)
        self.assertEqual(len(self.playlists.playlist_for_id(playlist.id).entries), 300)

    def test_artist_and_album_aggregation_handle_unknown_and_identity(self) -> None:
        artists = ArtistsAdapter(self.collection)
        albums = AlbumsAdapter(self.collection)
        self.assertGreaterEqual(len(artists.artists()), 50)
        self.assertGreaterEqual(len(albums.albums()), 80)
        self.assertIn(UNKNOWN_ARTIST, [artist.name for artist in artists.artists()])
        self.assertIn(UNKNOWN_ALBUM, [album.title for album in albums.albums()])
        by_title: dict[str, set[str]] = {}
        for album in albums.albums():
            by_title.setdefault(album.title, set()).add(album.artist)
        shared_title = next(title for title, names in by_title.items() if len(names) > 1)
        identities = [album.id for album in albums.albums() if album.title == shared_title]
        self.assertEqual(len(identities), len(set(identities)))

    def test_artist_and_album_search_and_detail_track_sets(self) -> None:
        artists = ArtistsAdapter(self.collection)
        albums = AlbumsAdapter(self.collection)
        artist = next(item for item in artists.artists() if item.name != UNKNOWN_ARTIST)
        artists.set_query(artist.name[:3])
        self.assertIn(artist.id, [item.id for item in artists.artists()])
        album = next(item for item in albums.albums() if item.title != UNKNOWN_ALBUM)
        albums.set_query(album.artist)
        self.assertIn(album.id, [item.id for item in albums.albums()])
        self.assertEqual(
            {track.id for track in artists.tracks_for_artist(artist.id)}, set(artist.track_ids)
        )
        self.assertEqual(
            {track.id for track in albums.tracks_for_album(album.id)}, set(album.track_ids)
        )


class UiV2LibraryFamilyPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    @staticmethod
    def _available_index(page):
        return next(
            page.track_table.model.index(row, int(TrackColumn.TITLE))
            for row, track in enumerate(page.track_table.model.tracks())
            if not track.is_missing
        )

    def _route_page(self, route: str):
        self.window.navigation_adapter.set_route(route)
        self.app.processEvents()
        return self.window.router.currentWidget()

    def _play_from_page(self, page):
        index = self._available_index(page)
        track = page.track_table.model.track_at(index.row())
        page.track_table.doubleClicked.emit(index)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, track.id)
        return track

    def test_favorites_page_player_sync_and_state_preservation(self) -> None:
        page = self._route_page("liked")
        self.assertIsInstance(page, FavoritesPage)
        model = page.track_table.model
        page.search_box.set_text("Paper Moon")
        page.adapter.set_sort(TrackColumn.TITLE, Qt.SortOrder.AscendingOrder)
        page.track_table.verticalScrollBar().setValue(20)
        saved_scroll = page.track_table.verticalScrollBar().value()
        self._route_page("library")
        page = self._route_page("liked")
        self.assertIs(page.track_table.model, model)
        self.assertEqual(page.adapter.query, "Paper Moon")
        self.assertEqual(page.adapter.sort_column, TrackColumn.TITLE)
        self.assertEqual(page.track_table.verticalScrollBar().value(), saved_scroll)
        page.search_box.set_text("")
        track = self._play_from_page(page)
        self.window.player_bar.favorite_button.click()
        self.app.processEvents()
        self.assertFalse(self.window.library_collection.track_for_id(track.id).is_favorite)
        self.assertFalse(self.window.playback_adapter.state.current_track.is_favorite)
        self.assertNotIn(track.id, [item.id for item in page.adapter.tracks()])

    def test_recent_page_updates_from_playback_and_clear(self) -> None:
        track = self._play_from_page(self.window.library_page)
        page = self._route_page("recent")
        self.assertIsInstance(page, RecentPage)
        self.assertIn(track.id, [item.id for item in page.adapter.tracks()])
        self._play_from_page(page)
        self.assertEqual(self.window.library_collection.recent_for_track(track.id).play_count, 2)
        page.clear_button.click()
        self.app.processEvents()
        self.assertFalse(page.adapter.tracks())

    def test_playlist_route_crud_page_and_context_action(self) -> None:
        playlist = self.window.playlist_adapter.create_playlist("页面歌单")
        tracks = [track.id for track in self.window.library_collection.tracks() if not track.is_missing][:2]
        self.window.playlist_adapter.add_tracks(playlist.id, tracks)
        page = self._route_page(f"playlist:{playlist.id}")
        self.assertIsInstance(page, PlaylistPage)
        self.assertEqual(page.playlist_header.title_label.text(), "页面歌单")
        self._play_from_page(page)
        menu = page.track_table.build_context_menu(self._available_index(page))
        self.assertIn("从当前歌单移除", [action.text() for action in menu.actions()])
        menu.deleteLater()
        page.track_table.set_playlist_context(None)
        self.assertTrue(self.window.playlist_adapter.remove_track(playlist.id, tracks[0]))
        self.assertNotIn(tracks[0], [item.id for item in page.adapter.tracks()])
        self.window.playlist_adapter.delete_playlist(playlist.id)
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "library")

    def test_artist_and_album_pages_open_reused_detail_pages_and_play(self) -> None:
        artists_page = self._route_page("artists")
        self.assertIsInstance(artists_page, ArtistsPage)
        artist_id = self.window.router._artists_adapter.artists()[0].id
        artists_page.entity_requested.emit(artist_id)
        self.app.processEvents()
        artist_detail = self.window.router.currentWidget()
        self.assertIsInstance(artist_detail, ArtistDetailPage)
        self._play_from_page(artist_detail)
        artist_detail.back_button.click()
        self.app.processEvents()
        self.assertIs(self.window.router.currentWidget(), artists_page)

        albums_page = self._route_page("albums")
        self.assertIsInstance(albums_page, AlbumsPage)
        album_id = self.window.router._albums_adapter.albums()[0].id
        albums_page.entity_requested.emit(album_id)
        self.app.processEvents()
        album_detail = self.window.router.currentWidget()
        self.assertIsInstance(album_detail, AlbumDetailPage)
        self._play_from_page(album_detail)
        self.window.navigation_adapter.set_route(f"album_detail:{album_id}")
        self.app.processEvents()
        self.assertIs(self.window.router.currentWidget(), album_detail)

    def test_playing_highlight_queue_actions_theme_and_responsive_geometry(self) -> None:
        liked = self._route_page("liked")
        track = self._play_from_page(liked)
        liked_playing_row = next(
            row for row, item in enumerate(liked.track_table.model.tracks()) if item.id == track.id
        )
        self.assertTrue(
            liked.track_table.model.data(
                liked.track_table.model.index(liked_playing_row, 0), PLAYING_ROLE
            )
        )
        library_model = self.window.library_page.track_table.model
        playing_row = next(
            row for row, item in enumerate(library_model.tracks()) if item.id == track.id
        )
        self.assertTrue(
            library_model.data(
                library_model.index(playing_row, 0), PLAYING_ROLE
            )
        )
        liked.toolbar.play_all_button.click()
        self.app.processEvents()
        self.assertEqual(
            [item.id for item in self.window.playback_adapter._queue],
            [item.id for item in liked.adapter.tracks() if not item.is_missing],
        )
        liked.toolbar.shuffle_button.click()
        self.app.processEvents()
        self.assertTrue(self.window.playback_adapter.state.shuffle_enabled)
        library_model_identity = library_model
        for mode in ("light", "dark"):
            self.window.set_theme(mode)
            self.assertEqual(self.window.theme.mode, mode)
        for width, height in ((900, 600), (1100, 700), (1400, 850), (1600, 900)):
            self.window.resize(width, height)
            self.app.processEvents()
            self.assertIs(self.window.library_page.track_table.model, library_model_identity)
            self.assertFalse(self.window.library_page.track_table.horizontalScrollBar().isVisible())
            artists = self._route_page("artists")
            self.assertFalse(artists.scroll_area.horizontalScrollBar().isVisible())
            albums = self._route_page("albums")
            self.assertFalse(albums.scroll_area.horizontalScrollBar().isVisible())


if __name__ == "__main__":
    unittest.main()
