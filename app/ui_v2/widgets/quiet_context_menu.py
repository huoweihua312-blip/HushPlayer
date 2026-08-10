"""Explicitly themed QMenu used by content-page actions and track rows."""

from __future__ import annotations

from PySide6.QtWidgets import QMenu, QWidget

from app.ui_v2.theme.tokens import Theme


def menu_stylesheet(theme: Theme) -> str:
    """Return the shared menu stylesheet for native and subclassed menus."""

    c = theme.colors
    m = theme.metrics
    return (
        f"QMenu#quietContextMenu {{ padding: {m.spacing_xs}px; border: 1px solid {c.border}; "
        f"border-radius: {m.radius_sm}px; background: {c.surface_elevated}; color: {c.primary_text}; }}"
        f"QMenu#quietContextMenu::item {{ min-height: 24px; padding: {m.spacing_sm}px {m.spacing_md}px; "
        f"border-radius: {m.radius_sm}px; color: {c.primary_text}; }}"
        f"QMenu#quietContextMenu::item:selected {{ background: {c.hover_background}; color: {c.primary_text}; }}"
        f"QMenu#quietContextMenu::item:disabled {{ color: {c.disabled_text}; }}"
        f"QMenu#quietContextMenu::separator {{ height: 1px; margin: {m.spacing_xs}px {m.spacing_sm}px; background: {c.divider}; }}"
    )


def apply_menu_theme(menu: QMenu, theme: Theme) -> QMenu:
    """Apply the same theme to a native QMenu without changing its class."""

    menu.setObjectName("quietContextMenu")
    menu.setMinimumWidth(218)
    menu.setStyleSheet(menu_stylesheet(theme))
    return menu


class QuietContextMenu(QMenu):
    """A native Qt menu with an explicit Quiet Orbit surface and focus ring."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("quietContextMenu")
        self.setMinimumWidth(218)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        apply_menu_theme(self, theme)
