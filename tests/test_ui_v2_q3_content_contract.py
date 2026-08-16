from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HUSHPLAYER_UI_V2_DATA_MODE"] = "mock"

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from app.ui_v2.models.track_table_model import (
    PLAYBACK_ACTIVE_ROLE,
    PLAYING_ROLE,
    TrackColumn,
    TrackTableModel,
)
from app.ui_v2.pages.album_detail_page import AlbumDetailPage
from app.ui_v2.pages.recent_page import RecentPage
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.album_card import AlbumCard
from app.ui_v2.widgets.artist_card import ArtistCard
from app.ui_v2.widgets.content_cards import CompactContentCard, PlaylistCard
from app.ui_v2.widgets.content_heroes import AlbumHero, PlaylistHero
from app.ui_v2.widgets.content_primitives import (
    ActionToolbar,
    ContentPageHeader,
    QuietTrackDelegate,
    QuietTrackTable,
)
from app.ui_v2.widgets.content_states import InlineErrorState
from app.ui_v2.widgets.quiet_context_menu import QuietContextMenu
from app.ui_v2.widgets.responsive_columns import ResponsiveColumnPolicy
from app.ui_v2.widgets.track_delegate import RowVisualState, TrackDelegate
from app.ui_v2.widgets.track_table import TrackTable


class UiV2Q3ContentContractTests(unittest.TestCase):
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

    def test_shared_contract_has_one_table_and_delegate_family(self) -> None:
        self.assertTrue(issubclass(QuietTrackTable, TrackTable))
        self.assertTrue(issubclass(QuietTrackDelegate, TrackDelegate))
        self.assertTrue(issubclass(ContentPageHeader, object))
        self.assertTrue(issubclass(ActionToolbar, object))
        self.assertTrue(issubclass(PlaylistHero, object))
        self.assertTrue(issubclass(AlbumHero, object))

    def test_responsive_policy_preserves_more_column(self) -> None:
        narrow = ResponsiveColumnPolicy.profile_for_width(900)
        standard = ResponsiveColumnPolicy.profile_for_width(1200)
        wide = ResponsiveColumnPolicy.profile_for_width(1600)
        self.assertEqual(narrow.name, "narrow")
        self.assertNotIn(TrackColumn.ALBUM, narrow.visible)
        self.assertIn(TrackColumn.MORE, narrow.visible)
        self.assertIn(TrackColumn.ALBUM, standard.visible)
        self.assertIn(TrackColumn.SOURCE, wide.visible)

    def test_current_and_selected_states_are_independent_and_pause_is_distinct(self) -> None:
        track = next(item for item in self.window.library_collection.tracks() if not item.is_missing)
        delegate = self.window.library_page.track_table.delegate
        self.assertEqual(
            delegate.row_visual_state(track, True, False, True, True),
            RowVisualState.SELECTED_PLAYING,
        )
        self.assertEqual(
            delegate.row_visual_state(track, False, False, True, False),
            RowVisualState.PAUSED,
        )
        self.assertEqual(
            delegate.row_visual_state(track, True, False, False, True),
            RowVisualState.SELECTED,
        )

    def test_model_pause_updates_roles_without_reset(self) -> None:
        model = self.window.library_page.track_table.model
        resets = []
        model.modelReset.connect(lambda: resets.append(True))
        track = model.track_at(0)
        model.set_playing_track(track.id)
        model.set_playback_state(track.id, False)
        index = model.index(0, int(TrackColumn.TITLE))
        self.assertTrue(index.data(PLAYING_ROLE))
        self.assertFalse(index.data(PLAYBACK_ACTIVE_ROLE))
        self.assertFalse(resets)

    def test_enter_plays_selected_and_space_does_not_start_another_track(self) -> None:
        table = self.window.library_page.track_table
        row = next(
            row for row, item in enumerate(table.model.tracks()) if not item.is_missing
        )
        table.selectRow(row)
        table.setFocus()
        enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        table.keyPressEvent(enter)
        self.app.processEvents()
        current = self.window.playback_adapter.state.current_track
        self.assertIsNotNone(current)
        selected = table.model.track_at(row)
        self.assertEqual(current.id, selected.id)
        space = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        table.keyPressEvent(space)
        self.app.processEvents()
        self.assertEqual(self.window.playback_adapter.state.current_track.id, selected.id)

    def test_playback_pause_reaches_cached_content_pages(self) -> None:
        track = next(item for item in self.window.library_collection.tracks() if not item.is_missing)
        self.window.playback_adapter.set_queue(self.window.library_collection.tracks())
        self.window.playback_adapter.play_track(track.id)
        self.window.playback_adapter.pause()
        page = self.window.router.page_for_route("liked")
        self.window.router.set_playback_state(False)
        self.app.processEvents()
        self.assertEqual(page.track_table.model._playing_track_id, track.id)
        self.assertFalse(page.track_table.model._playing_active)

    def test_recent_uses_recorded_metadata_only(self) -> None:
        page = self.window.router.page_for_route("recent")
        self.assertIsInstance(page, RecentPage)
        self.assertEqual(page.track_table.model.headerData(6, Qt.Orientation.Horizontal), "最近")
        self.assertEqual(page.track_table.model.rowCount(), 0)

    def test_album_hero_keeps_artist_year_and_duration(self) -> None:
        page = self.window.router.page_for_route("albums")
        album = page.adapter.albums()[0]
        detail = self.window.router.page_for_route(f"album_detail:{album.id}")
        self.assertIsInstance(detail, AlbumDetailPage)
        self.assertIsInstance(detail.album_hero, AlbumHero)
        detail.set_album(album.id)
        self.assertIn(album.artist, detail.album_hero.meta_label.text())
        if album.year:
            self.assertIn(str(album.year), detail.album_hero.meta_label.text())

    def test_theme_context_menu_has_explicit_light_and_dark_surfaces(self) -> None:
        light = QuietContextMenu(get_theme("light"))
        dark = QuietContextMenu(get_theme("dark"))
        self.assertIn(get_theme("light").colors.surface_elevated, light.styleSheet())
        self.assertIn(get_theme("dark").colors.surface_elevated, dark.styleSheet())
        light.deleteLater()
        dark.deleteLater()

    def test_content_card_contract_is_artwork_first(self) -> None:
        self.assertTrue(issubclass(PlaylistCard, CompactContentCard))
        self.assertTrue(issubclass(ArtistCard, object))
        self.assertTrue(issubclass(AlbumCard, object))
        artists = self.window.router.page_for_route("artists")
        self.app.processEvents()
        card = next(iter(artists._cards.values()))
        self.assertGreaterEqual(card.cover_label.width(), 100)

    def test_inline_error_state_is_non_modal_and_retryable(self) -> None:
        state = InlineErrorState()
        seen = []
        state.retry_requested.connect(lambda: seen.append(True))
        state.action_button.click()
        self.assertTrue(seen)
        self.assertEqual(state.windowModality(), Qt.WindowModality.NonModal)
        state.deleteLater()

    def test_repeated_route_resize_theme_keeps_cached_content_and_player(self) -> None:
        library_page = self.window.library_page
        player_bar = self.window.player_bar
        table = library_page.track_table
        routes = ("library", "recent", "favorites", "artists", "albums")
        widths = (900, 1200, 1600)
        for cycle in range(20):
            self.window.navigation_adapter.set_route(routes[cycle % len(routes)])
            self.window.resize(widths[cycle % len(widths)], 900)
            self.window.set_theme("dark" if cycle % 2 else "light")
            self.app.processEvents()
            self.assertIs(self.window.library_page, library_page)
            self.assertIs(self.window.player_bar, player_bar)
            self.assertIs(self.window.library_page.track_table, table)
            self.assertEqual(table.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertLessEqual(self.window.player_bar.geometry().bottom(), self.window.root.geometry().bottom())


if __name__ == "__main__":
    unittest.main()
