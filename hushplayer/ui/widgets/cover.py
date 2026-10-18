"""Album artwork widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core.theme import rgba, theme
from ...library.artwork import placeholder_pixmap as placeholder_pixmap_for
from ...model.track import Album, Artist, Playlist, Track
from .common import paint_rounded_pixmap


class CoverWidget(QWidget):
    """Rounded artwork with a soft cross-fade when the track changes."""

    clicked = Signal()

    def __init__(
        self,
        size: int = 44,
        *,
        radius: int = 6,
        shadow: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._radius = radius
        self._shadow = shadow
        self._track: Track | Album | Artist | Playlist | None = None
        self._pixmap: QPixmap | None = None
        self._previous: QPixmap | None = None
        self._fade = 1.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_fade)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor if parent is not None else Qt.ArrowCursor)

    # ------------------------------------------------------------------ api
    def set_size(self, size: int) -> None:
        self._size = size
        self.setFixedSize(size, size)
        self._refresh()

    def set_radius(self, radius: int) -> None:
        self._radius = radius
        self.update()

    def set_track(self, item: Track | Album | Artist | Playlist | None, *, animate: bool = True) -> None:
        if item is self._track:
            return
        self._track = item
        if animate and not theme().reduce_motion:
            self._previous = self._pixmap
            self._fade = 0.0
            self._refresh(animate=True)
        else:
            self._previous = None
            self._fade = 1.0
            self._refresh()

    def set_pixmap(self, pixmap: QPixmap | None, *, animate: bool = False) -> None:
        self._pixmap = pixmap
        if animate and not theme().reduce_motion:
            self._fade = 0.0
            self._animation.stop()
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        else:
            self._fade = 1.0
            self._previous = None
        self.update()

    @property
    def track(self):
        return self._track

    def refresh(self) -> None:
        self._refresh()

    def _refresh(self, *, animate: bool = False) -> None:
        if self._track is None:
            self._pixmap = None
            self.update()
            return
        try:
            from ..context import ctx

            provider = ctx().covers
            self._pixmap = provider.pixmap(self._track, self._size)
        except Exception:
            self._pixmap = None
        if animate and not theme().reduce_motion:
            self._animation.stop()
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        self.update()

    def _on_fade(self, value) -> None:
        self._fade = float(value)
        self.update()

    # --------------------------------------------------------------- events
    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self._radius
        border = rgba(theme().palette.border, 0.55)
        if self._previous is not None and self._fade < 1.0:
            painter.save()
            painter.setOpacity(1.0 - self._fade)
            paint_rounded_pixmap(painter, rect, self._previous, radius, border=None)
            painter.restore()
        opacity = self._fade if self._previous is not None else 1.0
        painter.setOpacity(opacity)
        paint_rounded_pixmap(painter, rect, self._pixmap, radius, border=border)
        painter.end()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._size, self._size)


class HeroCover(QWidget):
    """Large artwork used by album/playlist headers and the now playing page."""

    clicked = Signal()

    def __init__(self, size: int = 200, *, radius: int = 14, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._radius = radius
        self._track = None
        self._pixmap: QPixmap | None = None
        self._round = False
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        try:
            from ..context import ctx

            ctx().covers.ready.connect(self._on_cover_ready)
        except Exception:
            pass

    def _on_cover_ready(self, _track_id: str) -> None:
        if self._track is not None and getattr(self._track, "id", "") == _track_id:
            self.refresh()

    def set_track(self, item) -> None:
        self._track = item
        self.refresh()

    def set_size(self, size: int) -> None:
        self._size = size
        self.setFixedSize(size, size)
        self.refresh()

    def set_round(self, round_cover: bool) -> None:
        self._round = round_cover
        self.update()

    def refresh(self) -> None:
        if self._track is None:
            self._pixmap = None
            self.update()
            return
        try:
            from ..context import ctx

            self._pixmap = ctx().covers.pixmap(self._track, self._size)
        except Exception:
            self._pixmap = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        palette = theme().palette
        radius = self._size / 2 if self._round else self._radius
        paint_rounded_pixmap(
            painter,
            rect,
            self._pixmap,
            radius,
            border=rgba(palette.text, 0.10 if palette.is_dark else 0.06),
        )
        painter.end()


class CoverTile(QWidget):
    """Grid card: artwork + title + subtitle, used for albums/artists/playlists."""

    activated = Signal()
    context_requested = Signal(object)
    hovered = Signal(bool)

    def __init__(self, item, *, size: int = 148, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self._size = size
        self._subtitle = subtitle
        self._hover = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_hover_value)
        self._cover = CoverWidget(size, radius=10, parent=self)
        self._cover.move(0, 0)
        self._cover.setCursor(Qt.PointingHandCursor)
        self._cover.clicked.connect(self._activate)
        self.setFixedSize(size, size + 54)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setMouseTracking(True)
        self._cover.setAttribute(Qt.WA_TransparentForMouseEvents, False)

    def _on_hover_value(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _activate(self) -> None:
        self.activated.emit()

    def set_subtitle(self, text: str) -> None:
        self._subtitle = text
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate(1.0)
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate(0.0)
        self.hovered.emit(False)
        super().leaveEvent(event)

    def _animate(self, target: float) -> None:
        if theme().reduce_motion:
            self._on_hover_value(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._activate()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._activate()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.context_requested.emit(self.item)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # hover plate behind the artwork
        if self._hover > 0.01:
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.05 * self._hover))
            painter.drawRoundedRect(
                QRectF(-8, -8, self._size + 16, self._size + 62 + 8), 12, 12
            )
        font = theme().font(9.8, 600)
        painter.setFont(font)
        painter.setPen(QPen(rgba(palette.text, 0.94)))
        title = getattr(self.item, "name", "") or getattr(self.item, "display_name", "") or ""
        from PySide6.QtGui import QFontMetrics

        metrics = QFontMetrics(font)
        painter.drawText(
            QRectF(1, self._size + 10, self._size - 2, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(title, Qt.ElideRight, self._size - 2),
        )
        if self._subtitle:
            sub_font = theme().font(8.8, 500)
            painter.setFont(sub_font)
            painter.setPen(QPen(rgba(palette.text, 0.55)))
            painter.drawText(
                QRectF(1, self._size + 28, self._size - 2, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                QFontMetrics(sub_font).elidedText(self._subtitle, Qt.ElideRight, self._size - 2),
            )
        painter.end()


__all__ = ["CoverWidget", "HeroCover", "CoverTile"]
