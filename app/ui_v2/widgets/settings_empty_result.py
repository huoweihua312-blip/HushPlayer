"""Formal empty state for settings search without decorative illustration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui_v2.theme.tokens import Theme


class SettingsEmptyResult(QWidget):
    """Keeps an empty search result clear and compact."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title = QLabel("未找到匹配的设置", self)
        self.detail = QLabel("请尝试主题、音量、歌词、透明、缓存或更新。", self)
        self.detail.setWordWrap(True)
        for label in (self.title, self.detail):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(6)
        layout.addStretch(1)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addStretch(1)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title.setStyleSheet(f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};")
        self.detail.setStyleSheet(f"color: {theme.colors.secondary_text};")
