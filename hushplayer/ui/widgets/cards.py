"""Grid cards for albums, artists and playlists."""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from ...core.theme import rgba, theme
from ...library.artwork import placeholder_pixmap
from ...model.track import Track
from .common import paint_rounded_pixmap


def cover_pixmap(item, size: int) -> QPixmap | None:
    """Resolve artwork for a track/album/artist/playlist without blocking."""
    if item is None:
        return None
    try:
        from ..context import ctx

        covers = ctx().covers
    except Exception:  # noqa: BLE001
        return None
    if isinstance(item, Track):
        return covers.pixmap(item, size)
    path = getattr(item, "artwork_path", "")
    if path and os.path.exists(path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return pixmap.scaled(
                size,
                size,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
    track_id = getattr(item, "cover_track_id", "")
    if track_id:
        try:
            track = ctx().library.track(track_id)
        except Exception:  # noqa: BLE001
            track = None
        if track is not None:
            return covers.pixmap(track, size)
    return None


class _CardBase(QWidget):
    activated = Signal(object)  # payload
    context_requested = Signal(object, QPoint)

    def __init__(self, size: int = 168, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._title = ""
        self._subtitle = ""
        self._hover = 0.0
        self._pixmap = None
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title = QFontMetrics(theme().font(9.6, 600))
        sub = QFontMetrics(theme().font(8.6, 400))
        self._text_top = 8
        self._title_h = title.height()
        self._sub_h = sub.height()
        self._text_gap = 2
        self.setFixedSize(
            self._size,
            self._size + self._text_top + self._title_h + self._text_gap + self._sub_h + 6,
        )

    # ------------------------------------------------------------------ data
    def set_text(self, title: str, subtitle: str = "") -> None:
        self._title = title or ""
        self._subtitle = subtitle or ""
        self.update()

    def set_pixmap(self, pixmap) -> None:
        self._pixmap = pixmap
        self.update()

    @property
    def payload(self):
        return None

    def load_cover(self) -> None:
        self.set_pixmap(cover_pixmap(self.payload, self._size * 2))

    # ----------------------------------------------------------------- paint
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = 1.0
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = 0.0
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.payload)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.context_requested.emit(self.payload, event.globalPos())

    def _art_radius(self) -> float:
        return 14.0 if self._size >= 120 else 10.0

    def _paint_art(self, painter: QPainter) -> None:
        palette = theme().palette
        art_rect = QRectF(0, 0, self._size, self._size)
        radius = self._art_radius()
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba("#000000", 0.16 if palette.is_dark else 0.07))
        painter.drawRoundedRect(art_rect.translated(0, 3), radius, radius)
        if self._pixmap is not None:
            paint_rounded_pixmap(painter, art_rect, self._pixmap, radius, border=rgba(palette.text, 0.08))
        else:
            paint_rounded_pixmap(
                painter,
                art_rect,
                placeholder_pixmap(int(self._size * 2), not palette.is_dark),
                radius,
                border=rgba(palette.text, 0.06),
            )
        if self._hover > 0.5:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba("#000000", 0.10 * self._hover))
            painter.drawRoundedRect(art_rect, radius, radius)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_art(painter)

        font = theme().font(9.6, 600)
        painter.setFont(font)
        painter.setPen(QPen(rgba(palette.text, 0.96)))
        metrics = QFontMetrics(font)
        painter.drawText(
            QRectF(0, self._size + self._text_top, self._size, self._title_h),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            metrics.elidedText(self._title or "—", Qt.ElideRight, int(self._size)),
        )
        if self._subtitle:
            sub = theme().font(8.6, 400)
            painter.setFont(sub)
            painter.setPen(QPen(rgba(palette.text, 0.52)))
            painter.drawText(
                QRectF(
                    0,
                    self._size + self._text_top + self._title_h + self._text_gap,
                    self._size,
                    self._sub_h,
                ),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                QFontMetrics(sub).elidedText(self._subtitle, Qt.ElideRight, int(self._size)),
            )
        painter.end()


class AlbumCard(_CardBase):
    def __init__(self, album, size: int = 168, parent: QWidget | None = None) -> None:
        super().__init__(size, parent)
        self._album = album
        subtitle = getattr(album, "artist", "") or ""
        self.set_text(getattr(album, "name", ""), subtitle)
        self.load_cover()

    @property
    def album(self):
        return self._album

    @property
    def payload(self):
        return self._album


class ArtistCard(_CardBase):
    def __init__(self, artist, size: int = 150, parent: QWidget | None = None) -> None:
        super().__init__(size, parent)
        self._artist = artist
        self.set_text(getattr(artist, "name", ""), _artist_subtitle(artist))
        self.load_cover()

    @property
    def artist(self):
        return self._artist

    @property
    def payload(self):
        return self._artist

    def _paint_art(self, painter: QPainter) -> None:
        palette = theme().palette
        art_rect = QRectF(0, 0, self._size, self._size)
        radius = self._size / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba("#000000", 0.14 if palette.is_dark else 0.06))
        painter.drawEllipse(art_rect.translated(0, 3))
        pixmap = self._pixmap or placeholder_pixmap(int(self._size * 2), not palette.is_dark)
        paint_rounded_pixmap(painter, art_rect, pixmap, radius, border=rgba(palette.text, 0.07))
        if self._hover > 0.5:
            painter.setBrush(rgba("#000000", 0.08 * self._hover))
            painter.drawEllipse(art_rect)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_art(painter)
        font = theme().font(9.6, 600)
        painter.setFont(font)
        painter.setPen(QPen(rgba(palette.text, 0.96)))
        painter.drawText(
            QRectF(-6, self._size + 9, self._size + 12, 19),
            int(Qt.AlignHCenter | Qt.AlignVCenter),
            QFontMetrics(font).elidedText(self._title or "—", Qt.ElideRight, int(self._size)),
        )
        if self._subtitle:
            sub = theme().font(8.6, 400)
            painter.setFont(sub)
            painter.setPen(QPen(rgba(palette.text, 0.5)))
            painter.drawText(
                QRectF(-6, self._size + 27, self._size + 12, 18),
                int(Qt.AlignHCenter | Qt.AlignVCenter),
                QFontMetrics(sub).elidedText(self._subtitle, Qt.ElideRight, int(self._size)),
            )
        painter.end()


def _artist_subtitle(artist) -> str:
    albums = getattr(artist, "album_count", 0) or 0
    tracks = getattr(artist, "track_count", 0) or 0
    if albums:
        return f"{albums} 张专辑"
    if tracks:
        return f"{tracks} 首歌曲"
    return ""


class PlaylistCard(_CardBase):
    def __init__(self, playlist, size: int = 168, parent: QWidget | None = None) -> None:
        super().__init__(size, parent)
        self._playlist = playlist
        count = getattr(playlist, "track_count", 0) or 0
        self.set_text(getattr(playlist, "name", ""), f"{count} 首歌曲" if count else "歌单")
        self.load_cover()

    @property
    def playlist(self):
        return self._playlist

    @property
    def payload(self):
        return self._playlist


class CardGrid(QWidget):
    """A wrapping grid that re-flows its cards when the width changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(20)
        self._grid.setVerticalSpacing(24)
        self._grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._cards: list[QWidget] = []
        self._columns = 0
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

    def set_cards(self, cards: list[QWidget]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards = list(cards)
        for card in self._cards:
            card.setParent(self)
        self._columns = 0
        self._reflow()

    def cards(self) -> list[QWidget]:
        return list(self._cards)

    def _reflow(self) -> None:
        if not self._cards:
            self.setVisible(False)
            return
        self.setVisible(True)
        step = self._cards[0].width() + 20
        columns = max(1, max(self.width(), step) // step)
        if columns == self._columns:
            return
        self._columns = columns
        for index, card in enumerate(self._cards):
            self._grid.addWidget(card, index // columns, index % columns, Qt.AlignLeft | Qt.AlignTop)
        self.setMinimumHeight(
            ((len(self._cards) + columns - 1) // columns) * (self._cards[0].height() + 24)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow()
