"""Album card used only by the Artist detail page."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui_v2.models.album import Album
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track


class ArtistAlbumCard(QFrame):
    """A quiet album tile with the same artwork resolver as Browse cards."""

    _FORBIDDEN_TITLE_MARKERS = ("mock", "demo", "preview", "fixture", "unknown album")

    activated = Signal(str)

    def __init__(
        self,
        album: Album,
        representative: Track | None,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.album_id = album.id
        self._album = album
        self._representative = representative
        self._theme = theme
        self._cover_size = 144
        self.setObjectName("artistAlbumCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artwork = QLabel(self)
        self.artwork.setObjectName("artistAlbumArtwork")
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork.setScaledContents(False)
        self.title_label = ElidedLabel(self)
        self.meta_label = ElidedLabel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.artwork)
        layout.addSpacing(8)
        layout.addWidget(self.title_label)
        layout.addSpacing(3)
        layout.addWidget(self.meta_label)
        layout.addSpacing(6)
        self.title_label.setFixedHeight(20)
        self.meta_label.setFixedHeight(18)
        self.set_album(album, representative)
        self.set_theme(theme)

    def set_album(self, album: Album, representative: Track | None) -> None:
        self._album = album
        self._representative = representative
        self.album_id = album.id
        title = str(album.title or "").strip()
        if not title or any(marker in title.casefold() for marker in self._FORBIDDEN_TITLE_MARKERS):
            title = "未命名专辑"
        self.title_label.clear()
        self.meta_label.clear()
        self.title_label.set_full_text(title)
        self.meta_label.set_full_text(self._format_meta(album))
        tooltip_parts = [self.title_label.full_text]
        if self.meta_label.full_text:
            tooltip_parts.append(self.meta_label.full_text)
        self.setToolTip(" · ".join(tooltip_parts))
        self._refresh_artwork()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.setStyleSheet(
            f"QFrame#artistAlbumCard {{ background: transparent; border: 0; }}"
            f"QFrame#artistAlbumCard:hover {{ background: {colors.hover_background}; border-radius: {theme.metrics.radius_sm}px; }}"
            f"QLabel#artistAlbumArtwork {{ border: 0; border-radius: {theme.metrics.radius_md}px; background: {colors.surface_secondary}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.card_title}px; font-weight: 600; color: {colors.primary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.card_meta}px; color: {colors.secondary_text};"
        )
        self._refresh_artwork()

    def set_cover_size(self, size: int) -> None:
        self._cover_size = max(112, int(size))
        self.artwork.setFixedSize(self._cover_size, self._cover_size)
        self.title_label.setFixedWidth(self._cover_size)
        self.meta_label.setFixedWidth(self._cover_size)
        self.setFixedWidth(self._cover_size)
        self.setFixedHeight(self._cover_size + 55)
        self._refresh_artwork()

    @staticmethod
    def _format_meta(album: Album) -> str:
        year = ArtistAlbumCard._valid_year(getattr(album, "year", None))
        track_ids = getattr(album, "track_ids", None)
        song_count = len(track_ids) if track_ids is not None else None
        parts: list[str] = []
        if year is not None:
            parts.append(str(year))
        if song_count is not None and song_count > 0:
            parts.append(f"{song_count} 首歌曲")
        return " · ".join(parts)

    @staticmethod
    def _valid_year(value: object) -> int | None:
        try:
            year = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return year if 1900 <= year <= date.today().year + 1 and year != 1970 else None

    def _refresh_artwork(self) -> None:
        # Clear the old pixmap before a responsive size change.  This forces
        # the styled QLabel surface to repaint instead of retaining a stale
        # larger pixmap in the Windows backing store.
        self.artwork.clear()
        if self._representative is None:
            return
        self.artwork.setPixmap(
            artwork_pixmap_for_track(self._representative, self._cover_size, self._cover_size)
        )
        self.artwork.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.activated.emit(self.album_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)
