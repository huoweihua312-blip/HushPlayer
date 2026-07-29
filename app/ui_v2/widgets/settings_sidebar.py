"""Persistent category navigation for the cached settings page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.settings_category import SETTINGS_CATEGORIES
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class SettingsSidebar(QFrame):
    """Fixed-order category buttons that keep their instances through resize."""

    category_requested = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._compact = False
        self._buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(2)
        for category in SETTINGS_CATEGORIES:
            button = QToolButton(self)
            button.setText(category.title)
            button.setToolTip(category.title)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, key=category.key: self.category_requested.emit(key))
            self._group.addButton(button)
            self._buttons[category.key] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.set_current("general")
        self.set_theme(theme)

    def set_current(self, category: str) -> None:
        button = self._buttons.get(category)
        if button is not None:
            button.setChecked(True)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self.set_theme(self._theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setMinimumWidth(56 if self._compact else 176)
        self.setMaximumWidth(56 if self._compact else 176)
        self.setStyleSheet(f"SettingsSidebar {{ background: {theme.colors.navigation_background}; border-right: 1px solid {theme.colors.border}; }}")
        for category in SETTINGS_CATEGORIES:
            button = self._buttons[category.key]
            button.setIcon(icon(category.icon_name, theme))
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
                if self._compact
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; text-align: left; padding: 0 10px; border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }} "
                f"QToolButton:hover {{ background: {theme.colors.hover_background}; color: {theme.colors.primary_text}; }} "
                f"QToolButton:checked {{ background: {theme.colors.selected_background}; color: {theme.colors.primary_text}; font-weight: 600; }}"
            )
