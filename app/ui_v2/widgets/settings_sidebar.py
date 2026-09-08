"""Persistent category navigation for the cached settings page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QScrollArea, QToolButton, QVBoxLayout, QWidget

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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(self.scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)
        for category in SETTINGS_CATEGORIES:
            button = QToolButton(self)
            button.setText(category.title)
            button.setToolTip(category.title)
            button.setAccessibleName(category.title)
            button.setAccessibleDescription(f"打开{category.title}设置")
            button.setCheckable(True)
            button.setMinimumHeight(theme.metrics.control_height)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(lambda checked=False, key=category.key: self.category_requested.emit(key))
            self._group.addButton(button)
            self._buttons[category.key] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)
        self.set_current("general")
        self.set_theme(theme)

    def set_current(self, category: str) -> None:
        button = self._buttons.get(category)
        if button is not None:
            button.setChecked(True)
            self._refresh_icons()
            self.scroll.ensureWidgetVisible(button)

    def set_category_count(self, category: str, count: int) -> None:
        button = self._buttons.get(str(category))
        if button is None:
            return
        metadata = next(
            (item for item in SETTINGS_CATEGORIES if item.key == str(category)),
            None,
        )
        if metadata is None:
            return
        total = max(0, int(count))
        button.setText(f"{metadata.title}  {total}" if total else metadata.title)
        button.setToolTip(
            f"{metadata.title}（{total}）" if total else metadata.title
        )

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
        self.setStyleSheet(
            f"SettingsSidebar {{ background: {theme.colors.navigation_background}; border-right: 1px solid {theme.colors.border}; }}"
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ min-height: 24px; background: {theme.colors.border_strong}; border-radius: 2px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._refresh_icons()
        for category in SETTINGS_CATEGORIES:
            button = self._buttons[category.key]
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; max-width: {width - 16}px; text-align: left; padding: 0 8px; border: 0; border-left: 3px solid transparent; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; font-size: {theme.fonts.body}px; font-weight: 400; }} "
                f"QToolButton:hover {{ background: {theme.colors.hover_background}; color: {theme.colors.primary_text}; }} "
                f"QToolButton:checked {{ background: {theme.colors.selected_background}; color: {theme.colors.primary_text}; border-left-color: {theme.colors.accent}; }}"
                f"QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border: 1px solid {theme.colors.focus_ring}; border-left-width: 3px; }}"
            )

    def _refresh_icons(self) -> None:
        """Refresh only glyph color; category files and icon size stay stable."""

        for category in SETTINGS_CATEGORIES:
            button = self._buttons[category.key]
            state = "selected" if button.isChecked() else "normal"
            button.setIcon(fluent_settings_icon(category.icon_name, self._theme, state, 18))
