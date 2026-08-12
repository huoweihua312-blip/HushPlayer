"""Consistent icon button for UI V2 transport and player actions."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QToolButton, QWidget

from app.ui_v2.theme.icons import FLUENT_PLAYER_ASSETS, IconName, fluent_icon, icon
from app.ui_v2.theme.tokens import Theme


def _rgba(value: str, alpha: float) -> str:
    color = QColor(value)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha:.2f})"


class PlayerIconButton(QToolButton):
    """One stateful, fixed-hit-area icon control for the formal PlayerBar."""

    def __init__(
        self,
        icon_name: IconName,
        tooltip: str,
        theme: Theme,
        parent: QWidget | None = None,
        *,
        primary: bool = False,
        size: int | None = None,
        icon_canvas_size: int | None = None,
        asset_family: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_name = icon_name
        self._primary = primary
        self._asset_family = asset_family
        self._active = False
        self._hovered = False
        self._button_size = max(20, int(size or (50 if primary else 32)))
        self._icon_canvas_size = max(
            15,
            int(icon_canvas_size or (21 if primary else 18)),
        )
        self.setProperty("selected", False)
        self.setToolTip(tooltip)
        self.setAutoRaise(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._button_size, self._button_size)
        self.set_theme(theme)

    def set_icon_name(self, icon_name: IconName) -> None:
        self._icon_name = icon_name
        self._refresh_icon()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        if self._primary:
            self.setStyleSheet(
                f"QToolButton {{ border: 0; border-radius: {self._button_size // 2}px; background: {colors.text_primary}; }}"
                f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
                f"QToolButton:pressed {{ background: {colors.accent_pressed}; }}"
                f"QToolButton:focus {{ border: 1px solid {colors.text_primary}; }}"
                f"QToolButton:disabled {{ background: {_rgba(colors.text_primary, 0.16)}; }}"
            )
        else:
            self.setStyleSheet(
                f"QToolButton {{ border: 0; border-radius: {self._button_size // 2}px; "
                "background: transparent; }"
                f"QToolButton:hover {{ background: {_rgba(colors.text_primary, 0.08)}; }}"
                f"QToolButton:pressed {{ background: {_rgba(colors.text_primary, 0.13)}; }}"
                f"QToolButton:focus {{ border: 1px solid {colors.text_primary}; }}"
                f"QToolButton:disabled, QToolButton:disabled:hover, QToolButton:disabled:pressed {{ background: transparent; }}"
            )
        self._refresh_icon()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.setProperty("selected", active)
        self.set_theme(self._theme)

    @property
    def active(self) -> bool:
        """Expose the lightweight selected state for focused UI tests."""

        return self._active

    @property
    def icon_name(self) -> IconName:
        """The semantic vector glyph currently shown by this fixed-size button."""

        return self._icon_name

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        if hasattr(self, "_icon_name"):
            self._refresh_icon()

    def _refresh_icon(self) -> None:
        state = "inverse" if self._primary else (
            "disabled" if not self.isEnabled() else
            "selected" if self._active else
            "hover" if self._hovered else "normal"
        )
        if not self.isEnabled():
            state = "disabled"
        if self._asset_family == "fluent_player":
            self.setIcon(fluent_icon(self._icon_name, self._theme, state, self._icon_canvas_size))
        else:
            self.setIcon(icon(self._icon_name, self._theme, state))
        self.setIconSize(QSize(self._icon_canvas_size, self._icon_canvas_size))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._refresh_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._refresh_icon()
        super().leaveEvent(event)

    @property
    def button_size(self) -> int:
        return self._button_size

    @property
    def icon_canvas_size(self) -> int:
        return self._icon_canvas_size

    @property
    def asset_family(self) -> str | None:
        return self._asset_family

    @property
    def asset_filename(self) -> str | None:
        """Expose the vendored filename used by this control for audits."""

        if self._asset_family != "fluent_player":
            return None
        return FLUENT_PLAYER_ASSETS.get(self._icon_name)


# Existing immersive-preview code imports the old name. Keep that API stable
# while the formal PlayerBar uses the more precise control name.
PlaybackButton = PlayerIconButton
