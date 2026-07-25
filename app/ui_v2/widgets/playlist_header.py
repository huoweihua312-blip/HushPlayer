"""Metadata and commands for one mock playlist page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.playlist import Playlist
from app.ui_v2.theme.tokens import Theme


class PlaylistHeader(QWidget):
    rename_requested = Signal()
    delete_requested = Signal()
    add_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.title_label = QLabel(self)
        self.meta_label = QLabel(self)
        self.rename_button = QToolButton(self)
        self.rename_button.setText("重命名")
        self.rename_button.clicked.connect(self.rename_requested)
        self.delete_button = QToolButton(self)
        self.delete_button.setText("删除")
        self.delete_button.clicked.connect(self.delete_requested)
        self.add_button = QToolButton(self)
        self.add_button.setText("添加歌曲")
        self.add_button.clicked.connect(self.add_requested)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.meta_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(text_layout)
        layout.addStretch(1)
        layout.addWidget(self.add_button)
        layout.addWidget(self.rename_button)
        layout.addWidget(self.delete_button)
        self.set_theme(theme)

    def set_playlist(self, playlist: Playlist | None) -> None:
        if playlist is None:
            self.title_label.setText("歌单")
            self.meta_label.setText("歌单不存在")
            return
        self.title_label.setText(playlist.name)
        self.title_label.setToolTip(playlist.name)
        self.meta_label.setText(
            f"{len(playlist.entries)} 首歌曲  创建于 {playlist.created_at:%Y-%m-%d}"
        )
        self.meta_label.setToolTip(playlist.description)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};"
        )
        for button in (self.add_button, self.rename_button, self.delete_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
                f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
            )
