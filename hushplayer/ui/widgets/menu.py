"""Themed popup menus.

A plain ``QMenu`` paints a rectangular, shadowed native frame on Windows: the
rounded corners from the stylesheet have nothing to antialias against, so the
menu shows square edges and a hard white box. Making the popup translucent lets
Qt composite the stylesheet's radius over the app behind it, and the soft
selection tint keeps rows readable (the old full-accent row made text vanish).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QWidget

from ...core.theme import theme


def themed_menu(parent: QWidget | None = None) -> QMenu:
    menu = QMenu(parent)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setFont(theme().font(9.4, 500))
    return menu
