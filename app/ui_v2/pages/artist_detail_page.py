"""Reusable artist detail TrackTable page with related-album information."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QToolButton

from app.ui_v2.adapters.artists_adapter import ArtistsAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme


class ArtistDetailPage(TrackListPage):
    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        artists: ArtistsAdapter,
        theme: Theme,
        parent=None,
    ) -> None:
        self.artists = artists
        self._artist_id = ""
        adapter = TrackListAdapter(collection, predicate=lambda _track: False)
        super().__init__("歌手", adapter, theme, parent)
        self.back_button = QToolButton(self)
        self.back_button.setText("返回歌手")
        self.related_albums = QLabel(self)
        self.related_albums.setWordWrap(True)
        self.header.trailing_layout.insertWidget(0, self.back_button)
        self.layout().insertWidget(2, self.related_albums)
        self.set_theme(theme)

    def set_artist(self, artist_id: str) -> None:
        self._artist_id = artist_id
        artist = self.artists.artist_for_id(artist_id)
        track_ids = frozenset(artist.track_ids) if artist else frozenset()
        self.adapter.set_predicate(lambda track: track.id in track_ids)
        self.header.title_label.setText(artist.name if artist else "歌手")
        self.related_albums.setText(
            f"专辑  {len(artist.album_ids) if artist else 0} 张"
        )

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if not hasattr(self, "back_button"):
            return
        self.back_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
        )
        self.related_albums.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )
