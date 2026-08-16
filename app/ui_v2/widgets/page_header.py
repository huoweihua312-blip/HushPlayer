"""Compact, non-card page title presentation."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui_v2.theme.tokens import Theme


class PageHeader(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contentPageHeader")
        self.setMinimumHeight(70)
        self.accent_rail = QFrame(self)
        self.accent_rail.setObjectName("pageHeaderAccentRail")
        self.accent_rail.setFixedSize(3, 44)
        self.context_label = QLabel("资料库", self)
        self.context_label.setObjectName("pageContext")
        self.title_label = QLabel(title, self)
        self.count_label = QLabel("0 首歌曲", self)
        self.title_label.setObjectName("pageTitle")
        self.count_label.setObjectName("pageCount")
        self.title_row = QWidget(self)
        title_row_layout = QHBoxLayout(self.title_row)
        title_row_layout.setContentsMargins(0, 0, 0, 0)
        title_row_layout.setSpacing(10)
        title_row_layout.addWidget(self.title_label)
        title_row_layout.addWidget(self.count_label)
        title_row_layout.addStretch(1)
        self.identity = QWidget(self)
        identity_layout = QVBoxLayout(self.identity)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(2)
        identity_layout.addWidget(self.context_label)
        identity_layout.addWidget(self.title_row)
        self.trailing_layout = QHBoxLayout()
        self.trailing_layout.setContentsMargins(0, 0, 0, 0)
        self.trailing_layout.setSpacing(8)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.accent_rail, 0)
        layout.addWidget(self.identity, 0)
        layout.addStretch(1)
        layout.addLayout(self.trailing_layout)

    def set_count(self, count: int) -> None:
        self.count_label.setText(f"{count} 首歌曲")

    def set_context(self, text: str) -> None:
        self.context_label.setText(str(text or "资料库"))

    def set_theme(self, theme: Theme) -> None:
        c = theme.colors
        self.setStyleSheet(
            f"QWidget#contentPageHeader {{ background: transparent; }}"
            f"QFrame#pageHeaderAccentRail {{ background: {c.accent}; border: 0; border-radius: 1px; }}"
            f"QLabel#pageContext {{ color: {c.text_tertiary}; font-size: {theme.fonts.caption}px; font-weight: 600; }}"
            f"QLabel#pageCount {{ padding: 2px 8px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; "
            f"background: {c.surface_secondary}; color: {c.text_secondary}; font-size: {theme.fonts.caption}px; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 700; color: {c.primary_text};"
        )
