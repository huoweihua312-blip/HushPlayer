"""Reusable album detail TrackTable page with a themed album header card."""

from __future__ import annotations

from PySide6.QtWidgets import QToolButton

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.pages.track_list_page import TrackListPage
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.album_card import AlbumCard


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
        self.back_button = QToolButton(self)
        self.back_button.setText("返回专辑")
        self.header.trailing_layout.insertWidget(0, self.back_button)
        self.album_card: AlbumCard | None = None
        self.set_theme(theme)

    def set_album(self, album_id: str) -> None:
        self._album_id = album_id
        album = self.albums.album_for_id(album_id)
        track_ids = frozenset(album.track_ids) if album else frozenset()
        self.adapter.set_predicate(lambda track: track.id in track_ids)
        self.header.title_label.setText(album.title if album else "专辑")
        if album is not None:
            if self.album_card is None:
                self.album_card = AlbumCard(album, self._theme, self)
                self.layout().insertWidget(2, self.album_card)
            else:
                self.album_card.set_album(album)
                self.album_card.setVisible(True)
        elif self.album_card is not None:
            self.album_card.setVisible(False)

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if not hasattr(self, "back_button"):
            return
        self.back_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
        )
        if self.album_card is not None:
            self.album_card.set_theme(theme)
