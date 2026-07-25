"""Formal empty, loading, and error presentation used by the V2 library page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui_v2.theme.icons import missing
from app.ui_v2.theme.tokens import Theme


class EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_label = QLabel(self)
        self.title_label = QLabel(self)
        self.detail_label = QLabel(self)
        for label in (self.icon_label, self.title_label, self.detail_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addStretch(1)
        self.set_state("empty")

    def set_state(self, state: str, detail: str = "") -> None:
        content = {
            "empty": ("没有可显示的歌曲", "尝试调整搜索内容或添加音乐文件。"),
            "loading": ("正在加载歌曲", "正在准备歌曲列表。"),
            "error": ("无法显示歌曲", "请稍后重试。"),
        }
        title, default_detail = content.get(state, content["empty"])
        self.title_label.setText(title)
        self.detail_label.setText(detail or default_detail)

    def set_theme(self, theme: Theme) -> None:
        self.icon_label.setPixmap(missing(theme).pixmap(theme.metrics.icon_lg, theme.metrics.icon_lg))
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )
