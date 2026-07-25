"""Shared compact actions for mock Track collections."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class SectionToolbar(QWidget):
    play_all_requested = Signal()
    shuffle_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.play_all_button = QToolButton(self)
        self.play_all_button.setText("播放全部")
        self.play_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.play_all_button.clicked.connect(self.play_all_requested)
        self.shuffle_button = QToolButton(self)
        self.shuffle_button.setText("随机播放")
        self.shuffle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.play_all_button)
        layout.addWidget(self.shuffle_button)
        layout.addStretch(1)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for button, icon_name in ((self.play_all_button, "play"), (self.shuffle_button, "shuffle")):
            button.setIcon(icon(icon_name, theme))
            button.setIconSize(QSize(theme.metrics.icon_sm, theme.metrics.icon_sm))
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
                f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; "
                f"background: transparent; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
                f"QToolButton:pressed {{ background: {theme.colors.selected_background}; }}"
                f"QToolButton:disabled {{ color: {theme.colors.disabled_text}; }}"
            )
