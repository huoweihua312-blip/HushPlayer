"""Popup menus must ignore the click that opened them."""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent



class _FakeRelease(QMouseEvent):
    def __init__(self, x: int, y: int):
        super().__init__(
            QEvent.Type.MouseButtonRelease,
            QPointF(x, y),
            QPointF(x, y),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )


def test_popup_ignores_release_right_after_opening(qapp) -> None:
    from hushplayer.ui.widgets.popup import PopupMenu

    menu = PopupMenu()
    fired: list[str] = []
    action = menu.addAction("第一项")
    action.triggered.connect(lambda: fired.append("hit"))
    menu.popup(QPoint(100, 100))
    qapp.processEvents()

    menu.mouseReleaseEvent(_FakeRelease(10, 12))
    assert fired == []

    menu._shown_at = time.monotonic() - 1.0
    menu.mouseReleaseEvent(_FakeRelease(10, 12))
    assert fired == ["hit"]

def _move(menu, x: int, y: int) -> None:
    from PySide6.QtGui import QMouseEvent

    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(x, y),
        QPointF(x, y),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    menu.mouseMoveEvent(event)


def test_submenu_hover_clears_when_pointer_leaves(qapp) -> None:
    from PySide6.QtCore import QPoint

    from hushplayer.ui.widgets.popup import PopupMenu

    menu = PopupMenu()
    first = menu.addAction("第一项")
    sub = menu.addMenu("更多")
    sub.addAction("子项 A")
    sub.addAction("子项 B")
    menu.popup(QPoint(120, 120))
    qapp.processEvents()

    menu._open_submenu(1)
    rect = menu._sub_rect()
    _move(menu, int(rect.left() + 10), int(rect.top() + 12))
    assert menu._sub_hover == 0

    # 移回父面板：子菜单高亮必须清掉，不能残留“外面也选中子项”的观感
    _move(menu, 10, 14)
    assert menu._sub_hover == -1
