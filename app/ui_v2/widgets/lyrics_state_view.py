"""Stable non-modal lyric state presentation for all non-ready conditions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.lyrics_state import LyricsState
from app.ui_v2.theme.tokens import Theme


class LyricsStateView(QWidget):
    retry_requested = Signal()
    source_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title_label = QLabel(self)
        self.detail_label = QLabel(self)
        self.retry_button = QToolButton(self)
        self.retry_button.setText("重新获取")
        self.source_button = QToolButton(self)
        self.source_button.setText("查看来源")
        self.retry_button.clicked.connect(self.retry_requested)
        self.source_button.clicked.connect(self.source_requested)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.addStretch(1)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.source_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        self.set_state(LyricsState())
        self.set_theme(theme)

    def set_state(self, state: LyricsState) -> None:
        values = {
            "idle": ("还没有正在播放的歌曲", "选择一首歌曲开始播放。"),
            "loading": ("正在加载歌词", "请稍候。"),
            "empty": ("暂无歌词", "没有找到这首歌曲的歌词。"),
            "failed": ("歌词加载失败", "暂时无法显示歌词，请稍后重试。"),
            "playback_unavailable": (
                "歌曲无法播放",
                state.message or "当前无法播放这首歌曲，暂不显示默认歌词。",
            ),
            "instrumental": ("纯音乐", "这首歌曲没有人声歌词。"),
        }
        title, detail = values.get(state.phase, ("歌词", state.message))
        self.title_label.setText(title)
        self.detail_label.setText(detail)
        self.retry_button.setVisible(state.phase in {"empty", "failed"})
        self.source_button.setVisible(state.phase == "failed")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};")
        self.detail_label.setStyleSheet(f"color: {theme.colors.secondary_text};")
        for button in (self.retry_button, self.source_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 0; "
                f"border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
            )
