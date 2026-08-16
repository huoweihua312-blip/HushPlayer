from __future__ import annotations

import inspect
import os
import unittest
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = "mock"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableView

from app.ui_v2.models.track_table_model import TrackColumn, TrackTableModel
from app.ui_v2.models.playlist import Playlist
from app.ui_v2.pages.all_songs_page import AllSongsPage
from app.ui_v2.pages.playlist_page import PlaylistPage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.widgets.track_delegate import RowVisualState
from app.ui_v2.widgets.track_table import TrackTable
from app.ui_v2.widgets.playlist_header import PlaylistHeader
from app.ui_v2.widgets.track_collection_hero import TrackCollectionHero


class UiV2ContentPageTests(unittest.TestCase):
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

    def _playlist_page(self) -> PlaylistPage:
        page = self.window.router.page_for_route("playlist:playlist-seed-1")
        self.app.processEvents()
        self.assertIsInstance(page, PlaylistPage)
        return page

    def test_all_songs_and_playlist_use_shared_table_components(self) -> None:
        all_songs = self.window.library_page
        playlist = self._playlist_page()
        self.assertIsInstance(all_songs, AllSongsPage)
        self.assertIsInstance(all_songs.track_table, TrackTable)
        self.assertIsInstance(playlist.track_table, TrackTable)
        self.assertIs(all_songs.track_table.model.__class__, playlist.track_table.model.__class__)
        self.assertIs(all_songs.track_table.model.__class__, TrackTableModel)
        self.assertIsNot(all_songs.track_table.model, playlist.track_table.model)

    def test_playlist_hero_actions_are_inline_and_related_rail_is_responsive(self) -> None:
        page = self._playlist_page()
        self.assertTrue(page.playlist_header.play_button.isEnabled())
        self.assertTrue(page.playlist_header.shuffle_button.isEnabled())
        self.assertTrue(page.playlist_header.favorite_button.isHidden())
        self.assertFalse(page.playlist_header.favorite_button.isEnabled())
        page.set_responsive_reference_width(1200)
        self.assertTrue(page.related_playlists.isHidden())
        page.set_responsive_reference_width(1600)
        self.assertFalse(page.related_playlists.isHidden())
        self.assertEqual(page.related_playlists.width(), 260)

    def test_narrow_table_keeps_title_artist_duration_more_without_horizontal_scroll(self) -> None:
        table = self.window.library_page.track_table
        model = table.model
        table.set_responsive_reference_width(900)
        self.assertEqual(table.column_profile, "narrow")
        self.assertFalse(table.isColumnHidden(1))  # title
        self.assertFalse(table.isColumnHidden(2))  # artist
        self.assertTrue(table.isColumnHidden(3))  # album
        self.assertFalse(table.isColumnHidden(0))  # status
        self.assertTrue(table.isColumnHidden(5))  # favorite
        self.assertTrue(table.isColumnHidden(6))  # source
        self.assertFalse(table.isColumnHidden(7))  # more
        self.assertEqual(table.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(table.verticalHeader().defaultSectionSize(), 48)
        self.assertEqual(model, table.model)

    def test_browse_scroll_region_is_named_and_reveals_overflow(self) -> None:
        page = self.window.router.page_for_route("browse")
        self.app.processEvents()
        self.assertEqual(page.scroll_area.accessibleName(), "浏览内容")
        self.assertEqual(
            page.scroll_area.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )

    def test_browse_refresh_signals_are_coalesced(self) -> None:
        page = self.window.router.page_for_route("browse")
        self.app.processEvents()
        calls: list[str] = []
        original_refresh = page.refresh_cards
        page.refresh_cards = lambda: calls.append("refresh")
        try:
            page._schedule_refresh()
            page._schedule_refresh()
            self.assertTrue(page._refresh_scheduled)
            page._flush_scheduled_refresh()
            self.assertEqual(calls, ["refresh"])
            self.assertFalse(page._refresh_scheduled)
        finally:
            page.refresh_cards = original_refresh

    def test_track_table_uses_status_favorite_more_columns_and_neutral_playing_state(self) -> None:
        table = self.window.library_page.track_table
        self.assertEqual(table.model.headerData(0, Qt.Orientation.Horizontal), "#")
        self.assertLess(int(TrackColumn.DURATION), int(TrackColumn.FAVORITE))
        self.assertLess(int(TrackColumn.FAVORITE), int(TrackColumn.MORE))
        self.assertEqual(table.model.headerData(int(TrackColumn.MORE), Qt.Orientation.Horizontal), "")
        self.assertFalse(table.header.is_sorted_section(int(TrackColumn.MORE)))
        playing = table.delegate.background_color(RowVisualState.PLAYING)
        self.assertLess(playing.alpha(), 255)
        self.assertNotEqual(playing.name(), self.window.theme.colors.playing_background)

    def test_all_songs_header_has_no_second_search_or_preview_theme_control(self) -> None:
        page = self.window.library_page
        self.assertIsInstance(page, AllSongsPage)
        self.assertIsNone(page.search_box)
        self.assertIsNone(page.theme_toggle)
        self.assertIsNone(page.state_toggle)
        self.assertEqual(page.header.trailing_layout.count(), 0)
        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertEqual(page.collection_actions.shuffle_button.text(), "")
        self.assertEqual(page.collection_actions.shuffle_button.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)

        playlist = self._playlist_page()
        playlist.set_responsive_reference_width(900)
        self.assertEqual(playlist.playlist_header.shuffle_button.text(), "")
        self.assertEqual(playlist.playlist_header.shuffle_button.toolTip(), "随机播放")
        self.assertEqual(playlist.playlist_header.more_button.text(), "")

    def test_collection_hero_actions_keep_clear_primary_hierarchy(self) -> None:
        hero = TrackCollectionHero(self.window.theme)
        self.assertEqual(hero.play_button.accessibleName(), "播放")
        self.assertEqual(hero.shuffle_button.accessibleName(), "随机播放")
        self.assertIn("background: " + self.window.theme.colors.accent, hero.play_button.styleSheet())
        self.assertIn("background: " + self.window.theme.colors.surface_secondary, hero.shuffle_button.styleSheet())
        self.assertIn("border: 1px solid " + self.window.theme.colors.border, hero.shuffle_button.styleSheet())
        self.assertGreaterEqual(hero.play_button.minimumWidth(), 92)
        self.assertGreaterEqual(hero.shuffle_button.minimumWidth(), 116)
        self.assertEqual(hero.play_button.iconSize(), hero.shuffle_button.iconSize())
        self.assertNotEqual(hero.play_button.icon().cacheKey(), hero.shuffle_button.icon().cacheKey())
        hero.deleteLater()

    def test_empty_playlist_uses_formal_copy_and_music_semantic_icon(self) -> None:
        page = self.window.router.page_for_route("playlist:playlist-seed-8")
        self.app.processEvents()
        self.assertNotIn("mock", page.empty_state.detail_label.text().casefold())
        self.assertNotIn("demo", page.empty_state.detail_label.text().casefold())
        self.assertFalse(page.empty_state.icon_label.pixmap().isNull())
        self.assertEqual(page.empty_state.empty_icon_name, "playlist")

    def test_playlist_hero_hides_unusable_epoch_date(self) -> None:
        header = PlaylistHeader(self.window.theme)
        header.set_playlist(
            Playlist("epoch", "临时歌单", datetime(1970, 1, 1), entries=()),
            (),
        )
        self.assertNotIn("1970-01-01", header.meta_label.text())

    def test_content_safe_bottom_is_shared_and_models_survive_resize(self) -> None:
        all_songs = self.window.library_page
        playlist = self._playlist_page()
        identities = (
            all_songs.track_table.model,
            all_songs.track_table.delegate,
            playlist.track_table.model,
            playlist.track_table.delegate,
            self.window.library_adapter,
            self.window.playlist_adapter,
            self.window.player_bar,
        )
        self.assertGreater(all_songs.view_stack.contentsMargins().bottom(), 0)
        self.assertGreater(playlist.view_stack.contentsMargins().bottom(), 0)
        self.assertEqual(all_songs.view_host.objectName(), "libraryWorkSurface")
        self.assertEqual(playlist.view_host.objectName(), "trackListWorkSurface")
        self.assertGreater(all_songs.view_stack.contentsMargins().left(), 0)
        self.assertGreater(playlist.view_stack.contentsMargins().left(), 0)
        self.window.resize(900, 600)
        self.app.processEvents()
        self.window.resize(1600, 900)
        self.app.processEvents()
        self.assertEqual(
            identities,
            (
                all_songs.track_table.model,
                all_songs.track_table.delegate,
                playlist.track_table.model,
                playlist.track_table.delegate,
                self.window.library_adapter,
                self.window.playlist_adapter,
                self.window.player_bar,
            ),
        )

    def test_track_table_is_not_widget_per_row_and_keeps_full_tooltip(self) -> None:
        table = self.window.library_page.track_table
        self.assertIsInstance(table, QTableView)
        self.assertEqual(table.model.rowCount(), 1000)
        track = table.model.track_at(0)
        tooltip = table.model.index(0, 1).data(Qt.ItemDataRole.ToolTipRole)
        self.assertIn(track.title, tooltip)
        self.assertIn("添加时间:", tooltip)

    def test_pages_do_not_parse_json_or_access_remote_store(self) -> None:
        playlist_source = inspect.getsource(PlaylistPage)
        all_songs_source = inspect.getsource(AllSongsPage)
        self.assertNotIn("json.load", playlist_source)
        self.assertNotIn("RemoteTrackStore", playlist_source)
        self.assertNotIn("json.load", all_songs_source)
        self.assertNotIn("RemoteTrackStore", all_songs_source)


if __name__ == "__main__":
    unittest.main()
