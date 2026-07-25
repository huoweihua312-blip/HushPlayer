"""Reusable route button with responsive labels and playlist context actions."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QToolButton, QWidget

from app.ui_v2.models.navigation_item import NavigationItem as NavigationValue
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class NavigationItem(QToolButton):
    route_requested = Signal(str)
    context_requested = Signal(str, object)

    def __init__(
        self, item: NavigationValue, theme: Theme, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.item = item
        self._theme = theme
        self._compact = False
        self._selected = False
        self.setText(item.title)
        self.setToolTip(item.title)
        self.setEnabled(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(theme.metrics.icon_md, theme.metrics.icon_md))
        self.setFixedHeight(38)
        self.clicked.connect(lambda: self.route_requested.emit(self.item.route_id))
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh_visuals()

    def set_compact(self, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._refresh_visuals()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._refresh_visuals()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        if self.item.playlist_id:
            self.context_requested.emit(self.item.playlist_id, event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def _refresh_visuals(self) -> None:
        c = self._theme.colors
        icon_state = "selected" if self._selected else "normal"
        self.setIcon(icon(self.item.icon_name, self._theme, icon_state))
        self.setMinimumWidth(46 if self._compact else 0)
        self.setStyleSheet(
            f"QToolButton {{ text-align: left; padding: 0 10px; border: 0; "
            f"border-radius: {self._theme.metrics.radius_sm}px; color: {c.primary_text if self._selected else c.secondary_text}; "
            f"background: {c.selected_background if self._selected else 'transparent'}; }}"
            f"QToolButton:hover {{ color: {c.primary_text}; background: {c.hover_background}; }}"
            f"QToolButton:pressed {{ background: {c.playing_background}; }}"
            f"QToolButton:disabled {{ color: {c.disabled_text}; background: transparent; }}"
            f"QToolButton:disabled:hover {{ color: {c.disabled_text}; background: transparent; }}"
        )
