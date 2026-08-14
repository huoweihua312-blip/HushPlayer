"""Primary query control for the mock online-search page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class OnlineSearchBar(QWidget):
    search_requested = Signal()
    query_changed = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.line_edit = QLineEdit(self)
        self.line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.line_edit.setPlaceholderText("搜索歌曲、歌手或专辑")
        self.line_edit.setMaxLength(120)
        self.line_edit.textChanged.connect(self.query_changed)
        self.line_edit.returnPressed.connect(self.search_requested)
        self.search_button = QToolButton(self)
        self.search_button.setText("搜索")
        self.search_button.clicked.connect(self.search_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.search_button)
        self.set_theme(theme)

    def set_text(self, value: str) -> None:
        self.line_edit.setText(value)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.line_edit.setStyleSheet(
            f"min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
            f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_md}px; "
            f"background: {theme.colors.input_background}; color: {theme.colors.primary_text};"
        )
        self.search_button.setIcon(icon("search", theme))
        self.search_button.setIconSize(QSize(theme.metrics.icon_sm, theme.metrics.icon_sm))
        self.search_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.selected_background}; "
            f"color: {theme.colors.primary_text}; }}"
            f"QToolButton:hover {{ background: {theme.colors.hover_background}; }}"
            f"QToolButton:disabled {{ color: {theme.colors.disabled_text}; }}"
        )
