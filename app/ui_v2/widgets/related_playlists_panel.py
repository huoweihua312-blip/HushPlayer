"""Deterministic related-playlist rail for the wide Playlist page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.playlist import Playlist
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel


class RelatedPlaylistRow(QFrame):
    clicked = Signal(str)

    def __init__(self, playlist: Playlist, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.playlist_id = playlist.id
        self._theme = theme
        self.setObjectName("relatedPlaylistRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artwork = ArtworkThumbnail(theme, self, size=34)
        self.artwork.set_track(None)
        self.name_label = ElidedLabel(self)
        self.name_label.set_full_text(playlist.name)
        self.meta_label = QLabel(f"{len(playlist.entries)} 首歌曲", self)
        self.meta_label.setObjectName("relatedPlaylistMeta")
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(1)
        details.addWidget(self.name_label)
        details.addWidget(self.meta_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)
        layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(details, 1)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.artwork.set_theme(theme)
        self.name_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.primary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"
        )
        self.setStyleSheet(
            f"QFrame#relatedPlaylistRow {{ border: 0; border-radius: {theme.metrics.radius_sm}px; }}"
            f"QFrame#relatedPlaylistRow:hover {{ background: {theme.colors.hover_background}; }}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.playlist_id)
            event.accept()
            return
        super().mousePressEvent(event)


class RelatedPlaylistsPanel(QWidget):
    """Compact rail that is removed entirely below the wide breakpoint."""

    playlist_requested = Signal(str)

    def __init__(self, playlists: PlaylistAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playlists = playlists
        self._theme = theme
        self._rows: list[RelatedPlaylistRow] = []
        self.setObjectName("relatedPlaylistsPanel")
        self.setFixedWidth(260)
        self.title_label = QLabel("相关歌单", self)
        self.title_label.setObjectName("relatedPlaylistsTitle")
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addLayout(self._rows_layout)
        layout.addStretch(1)
        playlists.playlists_changed.connect(lambda _items: self.refresh())
        self.set_theme(theme)
        self.refresh()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"QWidget#relatedPlaylistsPanel {{ border-left: 1px solid {theme.colors.divider}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        for row in self._rows:
            row.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        self.setVisible(int(width) >= 1450)

    def refresh(self) -> None:
        while self._rows:
            row = self._rows.pop()
            row.deleteLater()
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for playlist in self._playlists.playlists()[:7]:
            row = RelatedPlaylistRow(playlist, self._theme, self)
            representative = next(
                (
                    track
                    for track in self._playlists.collection.tracks_for_ids(playlist.track_ids)
                    if not track.is_missing
                ),
                None,
            )
            row.artwork.set_track(representative)
            row.clicked.connect(self.playlist_requested)
            self._rows.append(row)
            self._rows_layout.addWidget(row)
