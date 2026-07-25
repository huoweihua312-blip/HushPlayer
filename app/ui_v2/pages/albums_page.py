"""Responsive artist-qualified album aggregate page for UI V2."""

from __future__ import annotations

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.pages.entity_grid_page import EntityGridPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.album_card import AlbumCard


class AlbumsPage(EntityGridPage):
    def __init__(self, adapter: AlbumsAdapter, theme: Theme, parent=None) -> None:
        self.adapter = adapter
        super().__init__(
            "专辑",
            "张专辑",
            theme,
            search_callback=adapter.set_query,
            parent=parent,
        )
        self.configure_cards(
            lambda album: AlbumCard(album, theme, self.content),
            lambda card, album: card.set_album(album),
        )
        self.empty_state.set_state("empty", "没有匹配的专辑。")
        adapter.albums_reset.connect(self.set_entities)
        self.set_entities(adapter.albums())
