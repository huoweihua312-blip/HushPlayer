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
        self.setObjectName("sectionToolbar")
        self.setMinimumHeight(56)
        self._theme = theme
        self.play_all_button = QToolButton(self)
        self.play_all_button.setText("播放全部")
        self.play_all_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.play_all_button.setAccessibleName("播放全部")
        self.play_all_button.clicked.connect(self.play_all_requested)
        self.shuffle_button = QToolButton(self)
        self.shuffle_button.setText("随机播放")
        self.shuffle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shuffle_button.setAccessibleName("随机播放")
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.addWidget(self.play_all_button)
        layout.addWidget(self.shuffle_button)
        layout.addStretch(1)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            f"QWidget#sectionToolbar {{ background: {colors.surface_primary}; border: 1px solid {colors.border}; "
            f"border-radius: {metrics.radius_md}px; }}"
        )
        self.play_all_button.setIcon(icon("play", theme, "inverse"))
        self.play_all_button.setIconSize(QSize(metrics.icon_sm, metrics.icon_sm))
        self.shuffle_button.setIcon(icon("shuffle", theme, "normal"))
        self.shuffle_button.setIconSize(QSize(metrics.icon_sm, metrics.icon_sm))
        self.play_all_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid transparent; border-radius: {metrics.radius_sm}px; color: {colors.content_background}; "
            f"background: {colors.accent}; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
            f"QToolButton:pressed {{ background: {colors.accent_pressed}; }}"
            f"QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border-color: {colors.focus_ring}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: {colors.surface_secondary}; }}"
        )
        self.shuffle_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.primary_text}; "
            f"background: {colors.surface_secondary}; }}"
            f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
            f"QToolButton:pressed {{ background: {colors.selected_background}; }}"
            f"QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border-color: {colors.focus_ring}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: transparent; border-color: {colors.border}; }}"
        )
