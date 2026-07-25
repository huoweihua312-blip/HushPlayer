"""Theme-aware, reusable compact card for mock artist and album entities."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui_v2.theme.icons import IconName, icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.elided_label import ElidedLabel


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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(72)
        self.cover_label = QLabel(self)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedSize(48, 48)
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

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.cover_label.setPixmap(
            icon(self._icon_name, theme, "selected").pixmap(QSize(24, 24))
        )
        self.setStyleSheet(
            f"QFrame {{ border: 1px solid transparent; border-radius: {theme.metrics.radius_md}px; "
            f"background: transparent; }}"
            f"QFrame:hover {{ border-color: {theme.colors.border}; background: {theme.colors.hover_background}; }}"
        )
        self.cover_label.setStyleSheet(
            f"background: {theme.colors.elevated_background}; border: 1px solid {theme.colors.border}; "
            f"border-radius: {theme.metrics.radius_sm}px;"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.subtitle_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.subtle_text};"
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.entity_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)
