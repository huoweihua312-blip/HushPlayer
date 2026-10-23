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
