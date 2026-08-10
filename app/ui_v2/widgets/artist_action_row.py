"""Compact playback actions for the Artist detail surface."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class ArtistActionRow(QWidget):
    """One primary play action, one secondary shuffle action, and More."""

    play_requested = Signal()
    shuffle_requested = Signal()
    more_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playback_tooltip = ""
        self.play_button = QToolButton(self)
        self.play_button.setObjectName("artistPlayButton")
        self.play_button.setText("播放热门歌曲")
        self.play_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.play_button.clicked.connect(self.play_requested)
        self.shuffle_button = QToolButton(self)
        self.shuffle_button.setObjectName("artistShuffleButton")
        self.shuffle_button.setText("随机播放")
        self.shuffle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        self.more_button = QToolButton(self)
        self.more_button.setObjectName("artistMoreButton")
        self.more_button.setToolTip("更多艺人操作")
        self.more_button.clicked.connect(self.more_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.play_button)
        layout.addWidget(self.shuffle_button)
        layout.addWidget(self.more_button)
        layout.addStretch(1)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.play_button.setIcon(icon("play", theme, "selected"))
        self.play_button.setIconSize(QSize(16, 16))
        self.shuffle_button.setIcon(icon("shuffle", theme, "normal"))
        self.shuffle_button.setIconSize(QSize(16, 16))
        self.more_button.setIcon(icon("more", theme, "normal"))
        self.more_button.setIconSize(QSize(17, 17))
        self.play_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 0; border-radius: {metrics.radius_sm}px; color: {colors.content_background}; "
            f"background: {colors.accent}; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
            f"QToolButton:pressed {{ background: {colors.accent_pressed}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: {colors.surface_secondary}; }}"
        )
        self.shuffle_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.primary_text}; "
            f"background: {colors.surface_secondary}; }}"
            f"QToolButton:hover {{ background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
            f"QToolButton:pressed {{ background: {colors.selected_background}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: transparent; border-color: {colors.border}; }}"
        )
        self.more_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; min-width: {metrics.control_height}px; "
            f"border: 0; border-radius: {metrics.radius_sm}px; color: {colors.secondary_text}; background: transparent; }}"
            f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; }}"
            f"QToolButton:pressed {{ background: {colors.selected_background}; }}"
        )

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        self.play_button.setText("播放" if compact else "播放热门歌曲")
        self.shuffle_button.setText("" if compact else "随机播放")
        self.shuffle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        tooltip = self._playback_tooltip
        self.play_button.setToolTip(tooltip or "播放热门歌曲")
        self.shuffle_button.setToolTip(tooltip or "随机播放")

    def set_playback_enabled(self, enabled: bool, tooltip: str = "") -> None:
        self._playback_tooltip = str(tooltip or "")
        self.play_button.setEnabled(bool(enabled))
        self.shuffle_button.setEnabled(bool(enabled))
        self.play_button.setToolTip(self._playback_tooltip or "播放热门歌曲")
        self.shuffle_button.setToolTip(self._playback_tooltip or "随机播放")
