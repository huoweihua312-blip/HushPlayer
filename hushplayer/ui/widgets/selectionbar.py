"""Floating bar shown when several rows are selected in a track list."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ...core.theme import Metrics, css_rgba, rgba, theme
from .common import TextButton


class SelectionBar(QWidget):
    """Compact action bar for multi-selection (appears above the player bar)."""

    play_requested = Signal()
    next_requested = Signal()
    queue_requested = Signal()
    favorite_requested = Signal()
    playlist_requested = Signal()
    remove_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = 0
        self._can_remove = False
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 12, 6)
        layout.setSpacing(6)
        self.count_label = QLabel("已选择 0 首")
        layout.addWidget(self.count_label)
        layout.addSpacing(8)
        self.play_button = TextButton("播放", icon_name="play", size=30, accent=True)
        self.next_button = TextButton("下一首播放", icon_name="queue_add", size=30)
        self.queue_button = TextButton("加入队列", icon_name="queue", size=30)
        self.favorite_button = TextButton("收藏", icon_name="heart", size=30)
        self.playlist_button = TextButton("加入歌单", icon_name="plus", size=30)
        self.remove_button = TextButton("从歌单移除", icon_name="trash", size=30)
        for button in (
            self.play_button,
            self.next_button,
            self.queue_button,
            self.favorite_button,
            self.playlist_button,
            self.remove_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)
        self.clear_button = TextButton("取消选择", size=30)
        layout.addWidget(self.clear_button)

        self.play_button.clicked.connect(self.play_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.queue_button.clicked.connect(self.queue_requested)
        self.favorite_button.clicked.connect(self.favorite_requested)
        self.playlist_button.clicked.connect(self.playlist_requested)
        self.remove_button.clicked.connect(self.remove_requested)
        self.clear_button.clicked.connect(self.clear_requested)
        self.setVisible(False)

    # ------------------------------------------------------------------ API
    def set_selection(self, count: int, *, can_remove: bool = False) -> None:
        self._count = max(0, count)
        self._can_remove = can_remove
        self.count_label.setText(f"已选择 {self._count} 首")
        self.remove_button.setVisible(can_remove)
        self.setVisible(self._count >= 2)
        self.refresh_theme()

    def count(self) -> int:
        return self._count

    def refresh_theme(self) -> None:
        palette = theme().palette
        self.count_label.setFont(theme().font(9.2, 600))
        self.count_label.setStyleSheet(f"color:{css_rgba(palette.accent, 1.0)};")

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(rgba(palette.border_strong, 0.55))
        painter.setBrush(rgba(palette.elevated, 0.98))
        painter.drawRoundedRect(rect, Metrics.radius, Metrics.radius)
        painter.end()
