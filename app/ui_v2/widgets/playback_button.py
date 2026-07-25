"""Consistent icon button for UI V2 transport and player actions."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QToolButton, QWidget

from app.ui_v2.theme.icons import IconName, icon
from app.ui_v2.theme.tokens import Theme


class PlaybackButton(QToolButton):
    def __init__(
        self,
        icon_name: IconName,
        tooltip: str,
        theme: Theme,
        parent: QWidget | None = None,
        *,
        primary: bool = False,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_name = icon_name
        self._primary = primary
        self._active = False
        self.setToolTip(tooltip)
        self.setAutoRaise(True)
        self.setFixedSize(36 if not primary else 42, 36 if not primary else 42)
        self.set_theme(theme)

    def set_icon_name(self, icon_name: IconName) -> None:
        self._icon_name = icon_name
        self._refresh_icon()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        if self._primary:
            self.setStyleSheet(
                f"QToolButton {{ border: 0; border-radius: 21px; background: {colors.accent}; }}"
                f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
                f"QToolButton:pressed {{ background: {colors.accent_pressed}; }}"
                f"QToolButton:disabled {{ background: {colors.elevated_background}; }}"
            )
        else:
            self.setStyleSheet(
                f"QToolButton {{ border: 0; border-radius: {theme.metrics.radius_sm}px; "
                f"background: {colors.selected_background if self._active else 'transparent'}; }}"
                f"QToolButton:hover {{ background: {colors.hover_background}; }}"
                f"QToolButton:pressed {{ background: {colors.selected_background}; }}"
            )
        self._refresh_icon()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.set_theme(self._theme)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        if hasattr(self, "_icon_name"):
            self._refresh_icon()

    def _refresh_icon(self) -> None:
        state = "hover" if self._primary and self.isEnabled() else "normal"
        if not self.isEnabled():
            state = "disabled"
        self.setIcon(icon(self._icon_name, self._theme, state))
        icon_size = 20 if self._primary else self._theme.metrics.icon_md
        self.setIconSize(QSize(icon_size, icon_size))
