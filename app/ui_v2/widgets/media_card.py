"""Theme-aware, reusable compact card for mock artist and album entities."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui_v2.theme.icons import IconName, icon
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from app.ui_v2.models.track import Track


class MediaCard(QFrame):
    activated = Signal(str)

    def __init__(
        self,
        entity_id: str,
        icon_name: IconName,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entity_id = entity_id
        self._icon_name = icon_name
        self._theme = theme
        self._representative: Track | None = None
        self._circular_artwork = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(142)
        self.cover_label = QLabel(self)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedSize(104, 104)
        self.cover_label.setScaledContents(False)
        self.title_label = ElidedLabel(self)
        self.subtitle_label = ElidedLabel(self)
        self.detail_label = ElidedLabel(self)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)
        text_layout.addWidget(self.detail_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(self.cover_label)
        layout.addLayout(text_layout, 1)
        self.set_theme(theme)

    def set_content(self, title: str, subtitle: str, detail: str) -> None:
        self.title_label.set_full_text(title)
        self.subtitle_label.set_full_text(subtitle)
        self.detail_label.set_full_text(detail)

    def set_presentation(self, *, list_mode: bool) -> None:
        """Reflow the same clickable card; entity identity/signals stay intact."""
        self.layout().setDirection(QBoxLayout.Direction.LeftToRight if list_mode else QBoxLayout.Direction.TopToBottom)
        size = 64 if list_mode else 176
        self.cover_label.setFixedSize(size, size)
        self.layout().setAlignment(self.cover_label, Qt.AlignmentFlag.AlignLeft)
        self.setFixedHeight(84 if list_mode else 266)
        for label in (self.title_label, self.subtitle_label, self.detail_label):
            label.setFixedHeight(22)
        self._refresh_artwork()

    def set_artwork(self, track: Track | None, *, circular: bool = False) -> None:
        self._representative = track
        self._circular_artwork = bool(circular)
        self._refresh_artwork()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh_artwork()
        b2 = theme is get_theme(theme.mode, profile="b2")
        hover_border = "transparent" if b2 else theme.colors.border_strong
        self.setStyleSheet(
            f"QFrame {{ border: 1px solid transparent; border-radius: {theme.metrics.radius_md}px; "
            f"background: transparent; }}"
            f"QFrame:hover {{ border-color: {hover_border}; background: {theme.colors.hover_background}; }}"
        )
        self.cover_label.setStyleSheet(
            f"background: transparent; border: 0; "
            f"border-radius: {52 if self._circular_artwork else theme.metrics.radius_sm}px;"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; font-weight: 400; color: {theme.colors.primary_text};"
        )
        self.subtitle_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; font-weight: 400; color: {theme.colors.secondary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 400; color: {theme.colors.subtle_text};"
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.entity_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _refresh_artwork(self) -> None:
        if self._representative is None:
            self.cover_label.setPixmap(icon(self._icon_name, self._theme, "selected").pixmap(QSize(30, 30)))
            return
        size = self.cover_label.size()
        pixmap = artwork_pixmap_for_track(self._representative, size.width(), size.height())
        if self._circular_artwork and self._theme is get_theme(self._theme.mode, profile="b2"):
            clipped = QPixmap(pixmap.size())
            clipped.setDevicePixelRatio(pixmap.devicePixelRatio())
            clipped.fill(Qt.GlobalColor.transparent)
            painter = QPainter(clipped)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(QRectF(0, 0, size.width(), size.height()))
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            pixmap = clipped
        self.cover_label.setPixmap(pixmap)
