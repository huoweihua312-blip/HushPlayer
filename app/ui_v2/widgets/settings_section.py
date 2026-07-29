"""Lightweight settings section; deliberately not a QGroupBox card."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui_v2.theme.tokens import Theme


class SettingsSection(QWidget):
    """A title, optional description, and aligned settings rows."""

    def __init__(self, title: str, description: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title = QLabel(title, self)
        self.description = QLabel(description, self)
        self.description.setWordWrap(True)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.metrics.spacing_sm)
        layout.addWidget(self.title)
        if description:
            layout.addWidget(self.description)
        layout.addSpacing(theme.metrics.spacing_xs)
        layout.addLayout(self.rows_layout)
        self.set_theme(theme)

    def add_row(self, row: QWidget) -> None:
        self.rows_layout.addWidget(row)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title.setStyleSheet(f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};")
        self.description.setStyleSheet(f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};")
