from __future__ import annotations

import inspect
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = "mock"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.adapters.artists_adapter import ArtistsAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.models.album import Album
from app.ui_v2.pages.artist_detail_page import ArtistDetailPage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.widgets.artist_album_card import ArtistAlbumCard
from app.ui_v2.widgets.track_delegate import TrackDelegate
from app.ui_v2.widgets.track_table import TrackTable


class UiV2ArtistPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.resize(1200, 800)
        self.window.show()
        self.window.navigation_adapter.set_route("artist_detail:artist:mock artist 01")
        self.app.processEvents()
        self.page = self.window.router.currentWidget()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_artist_route_reuses_shared_aggregates_and_track_table(self) -> None:
        self.assertIsInstance(self.page, ArtistDetailPage)
        self.assertIs(self.page.artists, self.window.router._artists_adapter)
        self.assertIs(self.page.albums, self.window.router._albums_adapter)
        self.assertIs(self.page.collection, self.window.library_collection)
        self.assertIsInstance(self.page.track_table, TrackTable)
        self.assertIs(self.page.track_table.delegate.__class__, TrackDelegate)
        self.assertIs(self.page.hero.artist_aggregate, self.page.artist_aggregate)
        self.assertLessEqual(self.page.adapter.tracks().__len__(), 10)

    def test_popular_tracks_use_shared_model_and_resize_keeps_instances(self) -> None:
        model = self.page.track_table.model
        adapter = self.page.adapter
        player_bar = self.window.player_bar
        self.assertGreater(model.rowCount(), 0)
        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertEqual(self.page.track_table.column_profile, "narrow")
        self.assertTrue(self.page.track_table.isColumnHidden(3))
        self.assertFalse(self.page.track_table.isColumnHidden(7))
        self.window.resize(1600, 900)
        self.app.processEvents()
        self.assertEqual(self.page.track_table.model, model)
        self.assertIs(self.page.adapter, adapter)
        self.assertIs(self.window.player_bar, player_bar)
        self.assertFalse(self.page.info_rail.isVisible())
        self.assertEqual(self.page.info_rail.width(), 0)
        self.assertNotIn("专辑示例", self.page.info_body.text())

    def test_artist_page_has_no_direct_data_or_network_access(self) -> None:
        source = inspect.getsource(ArtistDetailPage)
        self.assertNotIn("json.load", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("RemoteTrackStore", source)
        self.assertNotIn("http", source.casefold())

    def test_mock_visible_text_is_formal(self) -> None:
        self.assertNotIn("mock", self.page.hero.name_label.full_text.casefold())
        self.assertNotIn("demo", self.page.hero.name_label.full_text.casefold())
        self.assertNotIn("fixture", self.page.hero.name_label.full_text.casefold())
        for card in self.page._album_cards:
            self.assertNotIn("mock", card.title_label.full_text.casefold())
            self.assertNotIn("demo", card.title_label.full_text.casefold())
            self.assertNotIn(card.title_label.full_text, card.meta_label.full_text)
        for row in range(self.page.track_table.model.rowCount()):
            text = str(self.page.track_table.model.index(row, 1).data(Qt.ItemDataRole.DisplayRole))
            self.assertNotIn("mock", text.casefold())

    def test_missing_artist_uses_formal_empty_state(self) -> None:
        self.page.set_artist("artist:does-not-exist")
        self.app.processEvents()
        self.assertTrue(self.page.empty_state.isVisible())
        self.assertEqual(self.page.empty_state.title_label.text(), "找不到这个艺人")
        self.assertIn("音乐库", self.page.empty_state.detail_label.text())
        self.assertFalse(self.page.popular_section.isVisible())
        self.assertFalse(self.page.albums_section.isVisible())
        self.assertFalse(self.page.artist_aggregate.exists)
        self.assertFalse(hasattr(self.page, "tabs"))
        self.assertFalse(self.page.hero_row.isVisible())
        self.assertFalse(self.page.info_rail.isVisible())

    def test_artist_aggregate_drives_zero_song_state_without_hiding_albums(self) -> None:
        artist = self.page.artist
        self.assertIsNotNone(artist)
        with patch.object(self.page.artists, "tracks_for_artist", return_value=()):
            self.page._refresh_artist()
        self.app.processEvents()
        aggregate = self.page.artist_aggregate
        self.assertTrue(aggregate.exists)
        self.assertEqual(aggregate.track_count, 0)
        self.assertEqual(aggregate.total_duration_ms, 0)
        self.assertEqual(aggregate.album_count, len(aggregate.albums))
        self.assertEqual(self.page.hero.meta_label.full_text.split(" 首歌曲")[0], "0")
        self.assertEqual(self.page.hero.duration_label.full_text, "")
        self.assertFalse(self.page.hero.action_row.play_button.isEnabled())
        self.assertFalse(self.page.hero.action_row.shuffle_button.isEnabled())
        self.assertEqual(self.page.hero.action_row.play_button.toolTip(), "没有可播放的歌曲")
        self.assertFalse(self.page.track_table.isVisible())
        self.assertTrue(self.page.popular_empty_state.isVisible())
        self.assertEqual(self.page.albums_section.isVisible(), bool(aggregate.album_count))

    def test_artist_aggregate_zero_songs_and_albums_has_only_popular_empty_state(self) -> None:
        artist = self.page.artist
        self.assertIsNotNone(artist)
        empty_artist = replace(artist, track_ids=(), album_ids=(), total_duration_ms=0)
        with patch.object(self.page.artists, "artist_for_id", return_value=empty_artist), patch.object(
            self.page.artists, "tracks_for_artist", return_value=()
        ):
            self.page._refresh_artist()
        self.app.processEvents()
        self.assertEqual(self.page.artist_aggregate.track_count, 0)
        self.assertEqual(self.page.artist_aggregate.album_count, 0)
        self.assertTrue(self.page.artist_aggregate.exists)
        self.assertTrue(self.page.hero_row.isVisible())
        self.assertIn("0 首歌曲 · 0 张专辑", self.page.hero.meta_label.full_text)
        self.assertTrue(self.page.popular_section.isVisible())
        self.assertFalse(self.page.track_table.isVisible())
        self.assertTrue(self.page.popular_empty_state.isVisible())
        self.assertFalse(self.page.albums_section.isVisible())

    def test_zero_albums_hides_album_section_without_affecting_tracks(self) -> None:
        with patch.object(self.page.albums, "album_for_id", return_value=None):
            self.page._refresh_artist()
        self.app.processEvents()
        self.assertEqual(self.page.artist_aggregate.album_count, 0)
        self.assertFalse(self.page.albums_section.isVisible())
        self.assertTrue(self.page.popular_section.isVisible())
        self.assertTrue(self.page.track_table.isVisible())
        self.assertIn("0 张专辑", self.page.hero.meta_label.full_text)

    def test_popular_visible_row_limit_follows_width_without_rebuilding_model(self) -> None:
        model = self.page.track_table.model
        adapter = self.page.adapter
        for width, expected in ((900, 4), (1200, 5), (1600, 6)):
            self.window.resize(width, 800 if width > 900 else 600)
            self.app.processEvents()
            self.assertEqual(self.page.track_table.visible_row_limit, expected)
            self.assertEqual(self.page.track_table.model, model)
            self.assertIs(self.page.adapter, adapter)
            visible_rows = sum(
                not self.page.track_table.isRowHidden(row)
                for row in range(model.rowCount())
            )
            self.assertEqual(visible_rows, min(expected, model.rowCount()))

    def test_artist_album_card_renders_title_and_valid_meta_once(self) -> None:
        album = Album("album:test", "夜间选集", "林岸", tuple(f"track-{i}" for i in range(6)), 0, 2024)
        card = ArtistAlbumCard(album, None, self.window.theme)
        card.set_cover_size(144)
        card.show()
        self.app.processEvents()
        self.assertEqual(card.title_label.full_text, "夜间选集")
        self.assertEqual(card.title_label.text().count("夜间选集"), 1)
        self.assertEqual(card.meta_label.full_text, "2024 · 6 首歌曲")
        self.assertNotIn(card.title_label.full_text, card.meta_label.full_text)
        self.assertLess(card.title_label.geometry().bottom(), card.meta_label.geometry().top())
        self.assertGreaterEqual(card.height(), card.meta_label.geometry().bottom())
        card.deleteLater()

    def test_artist_album_card_hides_invalid_year_and_missing_count(self) -> None:
        invalid_year = Album("album:invalid", "私人收藏", "林岸", ("track-1",), 0, 1970)
        no_count = Album("album:none", "城市漫游", "林岸", None, 0, None)
        invalid_card = ArtistAlbumCard(invalid_year, None, self.window.theme)
        no_count_card = ArtistAlbumCard(no_count, None, self.window.theme)
        self.assertEqual(invalid_card.meta_label.full_text, "1 首歌曲")
        self.assertEqual(no_count_card.meta_label.full_text, "")
        self.assertNotIn("1970", invalid_card.meta_label.full_text)
        invalid_card.deleteLater()
        no_count_card.deleteLater()

    def test_artist_context_menu_exposes_navigation_without_changing_row_visuals(self) -> None:
        menu = self.page.track_table.build_context_menu(self.page.track_table.model.index(0, 1))
        self.assertIsNotNone(menu)
        self.assertIn("查看艺人", [action.text() for action in menu.actions()])
        menu.deleteLater()
        self.assertEqual(self.page.track_table.delegate.__class__, TrackDelegate)

    def test_real_read_only_artist_hides_write_controls(self) -> None:
        collection = LibraryCollectionAdapter(create_mock_tracks(30), read_only=True)
        artists = ArtistsAdapter(collection)
        albums = AlbumsAdapter(collection)
        page = ArtistDetailPage(collection, artists, albums, self.window.theme)
        page.set_artist(artists.artists()[0].id)
        page.resize(900, 600)
        page.show()
        self.app.processEvents()
        self.assertTrue(page.track_table.isColumnHidden(5))
        self.assertFalse(page.hero.action_row.play_button.isEnabled())
        self.assertFalse(page.hero.action_row.shuffle_button.isEnabled())
        page.resize(1600, 900)
        self.app.processEvents()
        self.assertFalse(page.info_rail.isVisible())
        self.assertEqual(page.info_rail.width(), 0)
        page.close()
        page.deleteLater()

    def test_album_ids_are_stable_and_artist_does_not_create_second_adapter(self) -> None:
        ids = [card.album_id for card in self.page._album_cards]
        self.assertEqual(ids, list(dict.fromkeys(ids)))
        self.assertEqual(sum(isinstance(child, ArtistsAdapter) for child in self.page.children()), 0)

    def test_artist_page_reuses_shared_content_safe_bottom(self) -> None:
        self.page.set_content_safe_bottom(120)
        margins = self.page.content_layout.contentsMargins()
        self.assertEqual(margins.bottom(), self.window.theme.metrics.page_margin + 120)

    def test_album_cards_remain_unique_through_resize_and_state_cycles(self) -> None:
        album_ids = tuple(card.album_id for card in self.page._album_cards)
        initial_cards = tuple(self.page._album_cards)
        aggregate_id = id(self.page.artist_aggregate)
        player_bar = self.window.player_bar

        def assert_cards(expected_ids: tuple[str, ...]) -> None:
            self.app.processEvents()
            visible = [
                card for card in self.page.findChildren(ArtistAlbumCard)
                if card.isVisible()
            ]
            self.assertEqual(tuple(card.album_id for card in visible), expected_ids)
            self.assertEqual(
                sum(
                    self.page.album_row.itemAt(index).widget() is not None
                    for index in range(self.page.album_row.count())
                ),
                len(expected_ids),
            )
            self.assertEqual(len({id(card) for card in visible}), len(visible))
            for left_index, left in enumerate(visible):
                for right in visible[left_index + 1 :]:
                    self.assertFalse(left.geometry().intersects(right.geometry()))

        for width, height in ((1600, 900), (1200, 800), (900, 600), (1200, 800), (1600, 900)):
            self.window.resize(width, height)
            assert_cards(album_ids)
            self.assertEqual(tuple(self.page._album_cards), initial_cards)
            self.assertEqual(id(self.page.artist_aggregate), aggregate_id)
            self.assertIs(self.window.player_bar, player_bar)

        original_artist = self.page.artist
        original_tracks_for_artist = self.page.artists.tracks_for_artist
        original_artist_for_id = self.page.artists.artist_for_id
        empty_artist = replace(original_artist, track_ids=(), album_ids=(), total_duration_ms=0)
        try:
            for _ in range(2):
                with patch.object(self.page.artists, "tracks_for_artist", return_value=()):
                    self.page.set_artist(self.page.artist_id)
                    assert_cards(album_ids)
                    self.assertTrue(self.page.hero_row.isVisible())
                    self.assertEqual(
                        self.page.artist_aggregate.album_count,
                        len(album_ids),
                    )
                with patch.object(
                    self.page.artists,
                    "artist_for_id",
                    return_value=empty_artist,
                ), patch.object(self.page.artists, "tracks_for_artist", return_value=()):
                    self.page.set_artist(self.page.artist_id)
                    assert_cards(())
                    self.assertTrue(self.page.hero_row.isVisible())
                    self.assertEqual(self.page.hero.meta_label.full_text, "0 首歌曲 · 0 张专辑")
                self.page.set_artist(self.page.artist_id)
                assert_cards(album_ids)
        finally:
            self.page.artists.tracks_for_artist = original_tracks_for_artist
            self.page.artists.artist_for_id = original_artist_for_id


if __name__ == "__main__":
    unittest.main()
