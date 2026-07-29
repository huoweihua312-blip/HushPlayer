"""Small status badge used by the settings title area."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from app.ui_v2.theme.tokens import Theme


class SettingsBadge(QLabel):
    """A restrained status label that does not compete with the page title."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setVisible(False)
        self.set_theme(theme)

    def set_status(self, text: str, tone: str = "neutral") -> None:
        self.setText(text)
        self.setProperty("tone", tone)
        self.setVisible(bool(text))
        self.set_theme(self._theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        if not self.text():
            return
        colors = theme.colors
        tone = self.property("tone") or "neutral"
        foreground = {"warning": colors.warning, "success": colors.success, "danger": colors.danger}.get(tone, colors.secondary_text)
        self.setStyleSheet(
            f"padding: 3px 8px; border-radius: {theme.metrics.radius_sm}px; "
            f"background: {colors.hover_background}; color: {foreground}; "
            f"font-size: {theme.fonts.caption}px;"
        )
