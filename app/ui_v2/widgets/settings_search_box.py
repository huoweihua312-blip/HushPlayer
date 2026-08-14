"""Search field wrapper for the settings center."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class SettingsSearchBox(QWidget):
    """Searches setting labels, explanations, categories, and keywords."""

    query_changed = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.input = QLineEdit(self)
        self.input.setObjectName("settingsSearchInput")
        self.input.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.input.setPlaceholderText("搜索设置")
        self.clear_button = QToolButton(self)
        self.clear_button.setToolTip("清空设置搜索")
        self.input.textChanged.connect(self.query_changed)
        self.clear_button.clicked.connect(self.input.clear)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.input, 1)
        layout.addWidget(self.clear_button)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.clear_button.setIcon(icon("search", theme))
        self.clear_button.setStyleSheet(f"border: 0; border-radius: {theme.metrics.radius_sm}px; padding: 4px; background: transparent;")
        self.input.setStyleSheet(
            f"min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
            f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_md}px; "
            f"background: {theme.colors.input_background}; color: {theme.colors.primary_text};"
        )
