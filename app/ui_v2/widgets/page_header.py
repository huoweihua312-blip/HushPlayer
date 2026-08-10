"""Compact, non-card page title presentation."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui_v2.theme.tokens import Theme


class PageHeader(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_label = QLabel(title, self)
        self.count_label = QLabel("0 首歌曲", self)
        self.title_label.setObjectName("pageTitle")
        self.count_label.setObjectName("pageCount")
        self.trailing_layout = QHBoxLayout()
        self.trailing_layout.setContentsMargins(0, 0, 0, 0)
        self.trailing_layout.setSpacing(8)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.count_label)
        layout.addStretch(1)
        layout.addLayout(self.trailing_layout)

    def set_count(self, count: int) -> None:
        self.count_label.setText(f"{count} 首歌曲")

    def set_theme(self, theme: Theme) -> None:
        c = theme.colors
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; color: {c.primary_text};"
        )
        self.count_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {c.secondary_text};"
        )
