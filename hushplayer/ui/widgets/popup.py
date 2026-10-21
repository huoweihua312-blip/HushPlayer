"""Self-drawn popup menus and list popups.

Qt's ``QMenu`` is a native window: on Windows its corners stay square (the
window is opaque, so a stylesheet radius only reveals the black window fill),
and submenus are separate native windows that cannot be clipped. Painting the
menu ourselves gives real rounded corners, consistent hover rows and submenus
that look like one piece.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ...core import icons
from ...core.theme import rgba, theme

ROW_HEIGHT = 32
PAD_X = 12
PAD_Y = 6
RADIUS = 12


class PopupAction(QObject):
    """Minimal QAction stand-in understood by :class:`PopupMenu`."""

    triggered = Signal()

    def __init__(
        self,
        text: str,
        callback: Callable[[], None] | None = None,
        *,
        checkable: bool = False,
        checked: bool = False,
        enabled: bool = True,
        icon_name: str = "",
        shortcut: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._checkable = checkable
        self._checked = checked
        self._enabled = enabled
        self._icon = icon_name
        self._shortcut = shortcut
        if callback is not None:
            self.triggered.connect(callback)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text

    def isCheckable(self) -> bool:  # noqa: N802
        return self._checkable

    def setCheckable(self, value: bool) -> None:  # noqa: N802
        self._checkable = value

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, value: bool) -> None:  # noqa: N802
        self._checked = value

    def isEnabled(self) -> bool:  # noqa: N802
        return self._enabled

    def setEnabled(self, value: bool) -> None:  # noqa: N802
        self._enabled = value

    def isSeparator(self) -> bool:  # noqa: N802
        return False


class PopupMenu(QWidget):
    """Rounded, self-painted popup menu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._items: list[PopupAction | None] = []  # None => separator
        self._hover = -1
        self._active: PopupAction | None = None
        self._loop: QEventLoop | None = None
        self._submenu: PopupMenu | None = None
        self._submenu_index = -1
        self._radius = max(10.0, theme().scaled(12, factor=0.5))
        self._font = theme().font(9.4, 500)
        self._row_font = theme().font(9.4, 400)

    # ---------------------------------------------------------------- building
    def addAction(self, text, callback=None) -> PopupAction:  # noqa: N802
        if isinstance(text, PopupAction):
            action = text
        elif hasattr(text, "text") and hasattr(text, "triggered"):
            action = PopupAction(
                text.text(),
                checkable=text.isCheckable(),
                checked=text.isChecked(),
                enabled=text.isEnabled(),
            )
            # Menu click -> QAction.trigger() so slots connected to the original
            # QAction keep working (menus.py builds QActions, not wrappers).
            action.triggered.connect(text.trigger)
        else:
            action = PopupAction(str(text), callback)
        self._items.append(action)
        self._resize_to_content()
        return action

    def addSeparator(self) -> None:  # noqa: N802
        self._items.append(None)
        self._resize_to_content()

    def addMenu(self, title: str) -> "PopupMenu":  # noqa: N802
        child = PopupMenu(self)
        self._items.append(child)
        child._owner_title = title
        self._resize_to_content()
        return child

    def setFont(self, font) -> None:  # noqa: N802
        self._font = font
        self._row_font = font
        self._resize_to_content()

    def setIcon(self, icon) -> None:  # noqa: N802
        # Kept for QMenu compatibility; our rows use vector icon names instead.
        return None

    def isEmpty(self) -> bool:  # noqa: N802
        return not self._items

    # ----------------------------------------------------------------- metrics
    def _rows(self) -> list[tuple[int, int]]:
        """(top, height) for every entry, separators are 9 px tall."""
        metrics = QFontMetrics(self._row_font)
        row = max(ROW_HEIGHT, metrics.height() + 10)
        out: list[tuple[int, int]] = []
        y = PAD_Y
        for item in self._items:
            h = 9 if item is None else row
            out.append((y, h))
            y += h
        return out

    def _has_checks(self) -> bool:
        return any(isinstance(item, PopupAction) and item.isCheckable() for item in self._items)

    def _content_width(self) -> int:
        metrics = QFontMetrics(self._row_font)
        widest = 0
        for item in self._items:
            if item is None:
                continue
            if isinstance(item, PopupMenu):
                text = getattr(item, "_owner_title", "")
            else:
                text = item.text()
            extra = 20 if self._has_checks() else 0
            if isinstance(item, PopupAction) and item.isCheckable():
                extra += 0
            if isinstance(item, PopupAction) and item._shortcut:
                extra += metrics.horizontalAdvance(item._shortcut) + 24
            if isinstance(item, PopupAction) and item._icon:
                extra += 24
            widest = max(widest, metrics.horizontalAdvance(text) + extra)
        return widest

    def _resize_to_content(self) -> None:
        if not self._items:
            return
        height = self._rows()[-1][0] + self._rows()[-1][1] + PAD_Y
        width = max(theme().scaled(140, factor=0.4), self._content_width() + PAD_X * 2 + 14)
        self.setFixedSize(int(width), int(height))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.width(), self.height())

    # ------------------------------------------------------------------ showing
    def popup(self, position: QPoint) -> None:  # noqa: N802
        screen = self.screen() or self.parentWidget()
        point = QPoint(position)
        if screen is not None and hasattr(screen, "availableGeometry"):
            geo = screen.availableGeometry()
            if point.x() + self.width() > geo.right():
                point.setX(max(geo.left(), geo.right() - self.width()))
            if point.y() + self.height() > geo.bottom():
                point.setY(max(geo.top(), point.y() - self.height()))
        self.move(point)
        self.show()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def exec(self, position: QPoint):  # noqa: N802
        self._active = None
        self.popup(position)
        loop = QEventLoop(self)
        self._loop = loop
        loop.exec()
        return self._active

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._submenu is not None:
            self._submenu.close()
            self._submenu = None
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        super().hideEvent(event)

    # ------------------------------------------------------------------- events
    def _item_at(self, y: int) -> int:
        for index, (top, height) in enumerate(self._rows()):
            if top <= y < top + height:
                return index
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._submenu is not None and not self.rect().contains(event.position().toPoint()):
            # The child popup grabbed the mouse; leaving its rect must dismiss it
            # so the parent rows become hoverable again.
            self.close()
            return
        index = self._item_at(int(event.position().y()))
        if index != self._hover:
            self._hover = index
            self.update()
        if index >= 0 and index < len(self._items):
            item = self._items[index]
            if isinstance(item, PopupMenu):
                self._open_submenu(index)
            else:
                self._close_submenu()

    def _open_submenu(self, index: int) -> None:
        if self._submenu_index == index and self._submenu is not None:
            return
        self._close_submenu()
        child = self._items[index]
        if not isinstance(child, PopupMenu):
            return
        top, height = self._rows()[index]
        child.popup(self.mapToGlobal(QPoint(self.width() - 6, top - PAD_Y)))
        self._submenu = child
        self._submenu_index = index

    def _close_submenu(self) -> None:
        if self._submenu is not None:
            self._submenu.close()
            self._submenu = None
            self._submenu_index = -1

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self.rect().contains(event.position().toPoint()):
            self.close()
            return
        index = self._item_at(int(event.position().y()))
        if index < 0:
            return
        item = self._items[index]
        if isinstance(item, PopupMenu):
            self._open_submenu(index)
            return
        if isinstance(item, PopupAction) and item.isEnabled():
            if item.isCheckable():
                item.setChecked(not item.isChecked())
            self._active = item
            item.triggered.emit()
            self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = theme().palette
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.fillPath(path, QColor(palette.elevated))
        painter.setPen(QPen(QColor(palette.border), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        metrics = QFontMetrics(self._row_font)
        for index, item in enumerate(self._items):
            top, height = self._rows()[index]
            if item is None:
                painter.setPen(QPen(rgba(palette.text, 0.10), 1))
                painter.drawLine(
                    int(rect.left() + PAD_X - 2),
                    int(top + height / 2),
                    int(rect.right() - PAD_X + 2),
                    int(top + height / 2),
                )
                continue
            row = QRectF(rect.left() + 5, top, rect.width() - 10, height)
            hovered = index == self._hover
            if hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(rgba(palette.accent, 0.16))
                painter.drawRoundedRect(row, self._radius * 0.55, self._radius * 0.55)
            if isinstance(item, PopupMenu):
                text = getattr(item, "_owner_title", "")
                enabled = True
            else:
                text = item.text()
                enabled = item.isEnabled()
            ink = rgba(palette.text, 1.0 if enabled else 0.42)
            painter.setPen(QPen(QColor(ink)))
            painter.setFont(self._row_font)
            x = row.left() + PAD_X
            if self._has_checks():
                if isinstance(item, PopupAction) and item.isCheckable() and item.isChecked():
                    box = QRectF(x, row.center().y() - 6, 12, 12)
                    icons.draw(painter, "check", box, QColor(palette.accent))
                x += 20
            if isinstance(item, PopupAction) and item._icon:
                box = QRectF(x, row.center().y() - 9, 18, 18)
                icons.draw(painter, item._icon, box, QColor(ink))
                x += 24
            text_rect = QRectF(x, row.top(), row.right() - x - 20, row.height())
            painter.drawText(
                text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text
            )
            if isinstance(item, PopupAction) and item._shortcut:
                painter.setPen(QPen(rgba(palette.text, 0.45)))
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    item._shortcut,
                )
            if isinstance(item, PopupMenu):
                painter.setPen(QPen(rgba(palette.text, 0.55), 1.4))
                ax = row.right() - 12
                ay = row.center().y()
                painter.drawLine(int(ax - 4), int(ay - 4), int(ax), int(ay))
                painter.drawLine(int(ax), int(ay), int(ax - 4), int(ay + 4))


def list_popup(items: list[str], current: int, on_pick: Callable[[int], None]) -> PopupMenu:
    """Rounded popup used by combo boxes instead of the native view window."""
    menu = PopupMenu()
    rows: list[PopupAction] = []

    def choose(index: int) -> None:
        on_pick(index)
        menu.close()

    for index, label in enumerate(items):
        action = PopupAction(label, checkable=True, checked=index == current)
        action.triggered.connect(lambda idx=index: choose(idx))
        menu._items.append(action)
        rows.append(action)
    menu._resize_to_content()
    return menu
