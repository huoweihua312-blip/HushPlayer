"""Persistent category navigation for the cached settings page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.settings_category import SETTINGS_CATEGORIES
from app.ui_v2.theme.icons import fluent_settings_icon
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
            button.setAccessibleName(category.title)
            button.setAccessibleDescription(f"打开{category.title}设置")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
            self._refresh_icons()

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self.set_theme(self._theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        # Settings keeps the category labels readable even at 900px.  The
        # compact state narrows the rail, but never switches to icon-only
        # navigation or hides the formal category names.
        width = 156 if self._compact else 196
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)
        self.setStyleSheet(f"SettingsSidebar {{ background: {theme.colors.navigation_background}; border-right: 1px solid {theme.colors.border}; }}")
        self._refresh_icons()
        for category in SETTINGS_CATEGORIES:
            button = self._buttons[category.key]
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; max-width: {width - 16}px; text-align: left; padding: 0 8px; border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }} "
                f"QToolButton:hover {{ background: {theme.colors.hover_background}; color: {theme.colors.primary_text}; }} "
                f"QToolButton:checked {{ background: {theme.colors.selected_background}; color: {theme.colors.primary_text}; font-weight: 600; }}"
            )

    def _refresh_icons(self) -> None:
        """Refresh only glyph color; category files and icon size stay stable."""

        for category in SETTINGS_CATEGORIES:
            button = self._buttons[category.key]
            state = "selected" if button.isChecked() else "normal"
            button.setIcon(fluent_settings_icon(category.icon_name, self._theme, state, 18))
