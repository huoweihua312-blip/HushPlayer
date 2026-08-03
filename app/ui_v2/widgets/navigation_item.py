"""Reusable route button with responsive labels and playlist context actions."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QIcon
from PySide6.QtWidgets import QSizePolicy, QToolButton, QWidget

from app.ui_v2.models.navigation_item import NavigationItem as NavigationValue
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


_NAVIGATION_ICON_SIZES = {
    "library": 18,
    "browse": 18,
    "favorite": 18,
    "playlist_more": 17,
    "settings": 17,
}


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
        self._full_title = item.title
        self._custom_icon: QIcon | None = None
        self.setText(item.title)
        self.setToolTip(item.title)
        self.setEnabled(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(16, 16))
        self.setFixedHeight(42)
        # A playlist title must never determine the scroll-content width.  The
        # sidebar owns that width; the button consumes what it receives and
        # lets Qt elide within the real content rectangle.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.clicked.connect(lambda: self.route_requested.emit(self.item.route_id))
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh_visuals()

    def set_compact(self, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        # The approved compact sidebar narrows but retains the full product
        # vocabulary; it must not collapse names into a partial brand or icons.
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._refresh_visuals()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._refresh_visuals()

    def set_custom_icon(self, custom_icon: QIcon) -> None:
        """Use a deterministic local playlist cover in place of a glyph."""

        self._custom_icon = custom_icon
        self._refresh_visuals()

    def refresh_elided_text(self) -> None:
        """Refresh visible copy after a sidebar layout pass."""

        self._refresh_elided_text()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_elided_text()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_elided_text()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        if self.item.playlist_id:
            self.context_requested.emit(self.item.playlist_id, event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def _refresh_visuals(self) -> None:
        c = self._theme.colors
        icon_state = "selected" if self._selected else "normal"
        self.setIcon(
            self._custom_icon
            if self._custom_icon is not None
            else icon(self.item.icon_name, self._theme, icon_state)
        )
        icon_size = 18 if self._custom_icon is not None else _NAVIGATION_ICON_SIZES.get(
            self.item.icon_name, 17
        )
        self.setIconSize(QSize(icon_size, icon_size))
        self.setMinimumWidth(0)
        self.setStyleSheet(
            f"QToolButton {{ text-align: left; padding: 0 12px; border: 0; "
            f"border-radius: {self._theme.metrics.radius_md}px; font-size: {self._theme.fonts.body}px; "
            f"color: {c.primary_text if self._selected else c.secondary_text}; "
            f"background: {c.selected_background if self._selected else 'transparent'}; }}"
            f"QToolButton:hover {{ color: {c.primary_text}; background: {c.hover_background}; }}"
            f"QToolButton:pressed {{ background: {c.playing_background}; }}"
            f"QToolButton:disabled {{ color: {c.disabled_text}; background: transparent; }}"
            f"QToolButton:disabled:hover {{ color: {c.disabled_text}; background: transparent; }}"
        )
        self._refresh_elided_text()

    def _refresh_elided_text(self) -> None:
        """Elide from the current content rectangle, never by string slicing."""

        contents = self.contentsRect()
        # The visual width remains stable for default, hover, and selected
        # states: 12px side insets, the displayed icon, then a 10px gap.
        horizontal_padding = 24
        icon_and_gap = self.iconSize().width() + 10
        available = max(0, contents.width() - horizontal_padding - icon_and_gap)
        self.setText(
            self.fontMetrics().elidedText(
                self._full_title, Qt.TextElideMode.ElideRight, available
            )
        )
