"""Themed popup menu factory."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from .popup import PopupMenu


def themed_menu(parent: QWidget | None = None) -> PopupMenu:
    """Rounded, self-painted menu (native QMenus show black square corners)."""
    return PopupMenu(parent)
