"""Explicitly themed QMenu used by content-page actions and track rows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QWidget

from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.theme.system_surfaces import menu_stylesheet as system_menu_stylesheet


def menu_stylesheet(theme: Theme) -> str:
    """Return the shared menu stylesheet for native and subclassed menus."""

    return system_menu_stylesheet(theme, "QMenu#quietContextMenu")


def apply_menu_theme(menu: QMenu, theme: Theme) -> QMenu:
    """Apply the same theme to a native QMenu without changing its class."""

    menu.setObjectName("quietContextMenu")
    menu.setMinimumWidth(238)
    menu.setStyleSheet(menu_stylesheet(theme))
    menu._hush_system_theme = theme
    if not menu.property("hushSystemDecorated"):
        menu.aboutToShow.connect(lambda: _decorate_destructive_actions(menu))
        menu.setProperty("hushSystemDecorated", True)
    return menu


class QuietContextMenu(QMenu):
    """A native Qt menu with an explicit Quiet Orbit surface and focus ring."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("quietContextMenu")
        self.setMinimumWidth(238)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        apply_menu_theme(self, theme)


def _decorate_destructive_actions(menu: QMenu) -> None:
    """Add a danger glyph to existing mapped actions; never alter their semantics."""
    theme = get_theme(menu._hush_system_theme.mode, profile="b2")
    for action in menu.actions():
        if action.text() not in {"删除歌单", "从当前歌单移除"}:
            continue
        if not action.icon().isNull() and not action.property("hushDangerGlyph"):
            continue
        dpr = menu.devicePixelRatioF()
        pixmap = QPixmap(round(16 * dpr), round(16 * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(theme.colors.danger), 1.3))
        if action.text() == "删除歌单":
            painter.drawLine(3, 4, 13, 4)
            painter.drawLine(6, 2, 10, 2)
            painter.drawRoundedRect(4, 4, 8, 10, 1, 1)
            painter.drawLine(7, 7, 7, 11)
            painter.drawLine(9, 7, 9, 11)
        else:
            painter.drawEllipse(2, 2, 12, 12)
            painter.drawLine(5, 8, 11, 8)
        painter.end()
        action.setIcon(QIcon(pixmap))
        action.setProperty("hushDangerGlyph", True)
