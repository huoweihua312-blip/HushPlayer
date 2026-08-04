"""Persistent save/cancel footer for settings drafts."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.ui_v2.theme.tokens import Theme


class SettingsFooter(QFrame):
    """Keeps draft actions reachable while the category content scrolls."""

    category_defaults_requested = Signal()
    all_defaults_requested = Signal()
    cancel_requested = Signal()
    save_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.category_defaults_button = QPushButton("恢复当前分类默认", self)
        self.all_defaults_button = QPushButton("恢复全部默认", self)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("settingsFooterStatus")
        self.cancel_button = QPushButton("取消", self)
        self.save_button = QPushButton("保存", self)
        self.category_defaults_button.clicked.connect(self.category_defaults_requested)
        self.all_defaults_button.clicked.connect(self.all_defaults_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.save_button.clicked.connect(self.save_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)
        # The legacy settings implementation has no restore-default command;
        # keep these compatibility widgets available to old callers but do not
        # expose invented actions in the formal V2 Overlay.
        self.category_defaults_button.setVisible(False)
        self.all_defaults_button.setVisible(False)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.save_button)
        self.set_theme(theme)

    def set_state(self, *, dirty: bool, valid: bool) -> None:
        self.cancel_button.setEnabled(dirty)
        self.save_button.setEnabled(dirty and valid)

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or ""))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(f"SettingsFooter {{ border-top: 1px solid {theme.colors.border}; background: {theme.colors.elevated_background}; }}")
        neutral = f"QPushButton {{ min-height: {theme.metrics.control_height}px; padding: 0 12px; border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text}; }} QPushButton:hover {{ background: {theme.colors.hover_background}; }} QPushButton:disabled {{ color: {theme.colors.disabled_text}; }}"
        for button in (self.category_defaults_button, self.all_defaults_button, self.cancel_button):
            button.setStyleSheet(neutral)
        self.save_button.setStyleSheet(
            f"QPushButton {{ min-height: {theme.metrics.control_height}px; padding: 0 16px; border: 0; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.accent}; color: white; font-weight: 600; }} "
            f"QPushButton:hover {{ background: {theme.colors.accent_hover}; }} QPushButton:disabled {{ background: {theme.colors.border}; color: {theme.colors.disabled_text}; }}"
        )
        self.status_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"
        )
