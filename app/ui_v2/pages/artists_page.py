"""Responsive artist aggregate page for the UI V2 mock library."""

from __future__ import annotations

from app.ui_v2.adapters.artists_adapter import ArtistsAdapter
from app.ui_v2.pages.entity_grid_page import EntityGridPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artist_card import ArtistCard


class ArtistsPage(EntityGridPage):
    def __init__(self, adapter: ArtistsAdapter, theme: Theme, parent=None) -> None:
        self.adapter = adapter
        super().__init__(
            "歌手",
            "位歌手",
            theme,
            search_callback=adapter.set_query,
            parent=parent,
        )
        self.configure_cards(
            lambda artist: ArtistCard(
                artist,
                theme,
                self.content,
                next((track for track in adapter.tracks_for_artist(artist.id) if not track.is_missing), None),
            ),
            lambda card, artist: card.set_artist(
                artist,
                next((track for track in adapter.tracks_for_artist(artist.id) if not track.is_missing), None),
            ),
        )
        self.empty_state.set_state("empty", "没有匹配的歌手。")
        adapter.artists_reset.connect(self.set_entities)
        self.set_entities(adapter.artists())
