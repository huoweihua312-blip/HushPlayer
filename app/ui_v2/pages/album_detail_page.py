"""Reusable album detail page with a shared Hero above the TrackTable."""

from __future__ import annotations

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.content_heroes import AlbumHero


class AlbumDetailPage(TrackListPage):
    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        albums: AlbumsAdapter,
        theme: Theme,
        parent=None,
    ) -> None:
        self.albums = albums
        self._album_id = ""
        adapter = TrackListAdapter(collection, predicate=lambda _track: False)
        super().__init__("专辑", adapter, theme, parent)
        self.collection_hero = AlbumHero(theme, self)
        self.album_hero = self.collection_hero
        layout = self.layout()
        layout.replaceWidget(self.header, self.collection_hero)
        self.header.hide()
        self.toolbar.hide()
        self.back_button = self.collection_hero.back_button
        self.collection_hero.set_back_action("返回专辑")
        self.collection_hero.play_requested.connect(lambda: self._request_queue(False))
        self.collection_hero.shuffle_requested.connect(lambda: self._request_queue(True))
        self.set_theme(theme)

    def set_album(self, album_id: str) -> None:
        self._album_id = album_id
        album = self.albums.album_for_id(album_id)
        track_ids = frozenset(album.track_ids) if album else frozenset()
        self.adapter.set_predicate(lambda track: track.id in track_ids)
        self.collection_hero.set_album(album, self.adapter.tracks())

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if not hasattr(self, "back_button"):
            return
        self.collection_hero.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        super().set_responsive_reference_width(width)
        if hasattr(self, "collection_hero"):
            self.collection_hero.set_responsive_reference_width(width)
