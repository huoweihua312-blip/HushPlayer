"""Menus drawn *inside* the app window, plus a masked fallback for floating windows.

Native popup windows (``QMenu`` or a frameless ``Qt.Popup``) are rectangles owned
by Windows: DWM draws a rectangular shadow, corners depend on compositing, and
changing the window size while it is open breaks input hit-testing (submenus
became unclickable). Menus therefore render as a child overlay of the app window
whenever they fit there; only menus that must float outside a small window (the
desktop lyrics) fall back to a masked native popup.
"""

from __future__ import annotations

import ctypes
from typing import Callable

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from ...core import icons
from ...core.theme import rgba, theme

ROW_HEIGHT = 32
PAD_X = 12
PAD_Y = 6
_SUBMENU_GAP = 6

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DONOTROUND = 1


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
    """Rounded menu that prefers rendering as a child overlay of the app window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host_hint = parent
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._items: list = []
        self._hover = -1
        self._active: PopupAction | None = None
        self._loop: QEventLoop | None = None
        self._submenu: "PopupMenu | None" = None
        self._sub_open = -1
        self._sub_hover = -1
        self._owner_title = ""
        self._radius = max(10.0, theme().scaled(12, factor=0.5))
        self._row_font = theme().font(9.4, 400)
        self._font = theme().font(9.4, 500)
        self._base_width = 0
        self._overlay = False
        self._host: QWidget | None = None

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
            action.triggered.connect(text.trigger)
        else:
            action = PopupAction(str(text), callback)
        self._items.append(action)
        self._relayout()
        return action

    def addSeparator(self) -> None:  # noqa: N802
        self._items.append(None)
        self._relayout()

    def addMenu(self, title: str) -> "PopupMenu":  # noqa: N802
        child = PopupMenu(self)
        child._owner_title = title
        child.hide()
        self._items.append(child)
        self._relayout()
        return child

    def setFont(self, font) -> None:  # noqa: N802
        self._row_font = font
        self._font = font
        self._relayout()

    def setIcon(self, icon) -> None:  # noqa: N802
        return None

    def isEmpty(self) -> bool:  # noqa: N802
        return not self._items

    # ----------------------------------------------------------------- metrics
    def _has_checks(self) -> bool:
        return any(isinstance(item, PopupAction) and item.isCheckable() for item in self._items)

    def _rows(self) -> list[tuple[int, int]]:
        metrics = QFontMetrics(self._row_font)
        row = max(ROW_HEIGHT, metrics.height() + 10)
        out: list[tuple[int, int]] = []
        y = PAD_Y
        for item in self._items:
            height = 9 if item is None else row
            out.append((y, height))
            y += height
        return out

    def _content_width(self) -> int:
        metrics = QFontMetrics(self._row_font)
        widest = 0
        for item in self._items:
            if item is None:
                continue
            if isinstance(item, PopupMenu):
                text = item._owner_title
            else:
                text = item.text()
            extra = 20 if self._has_checks() else 0
            if isinstance(item, PopupAction) and item._shortcut:
                extra += metrics.horizontalAdvance(item._shortcut) + 24
            if isinstance(item, PopupAction) and item._icon:
                extra += 24
            widest = max(widest, metrics.horizontalAdvance(text) + extra)
        return widest

    def _intrinsic_size(self) -> tuple[int, int]:
        if not self._items:
            return 0, 0
        rows = self._rows()
        height = rows[-1][0] + rows[-1][1] + PAD_Y
        width = max(theme().scaled(140, factor=0.4), self._content_width() + PAD_X * 2 + 16)
        return int(width), int(height)

    def _relayout(self) -> None:
        if not self._items:
            return
        width, height = self._intrinsic_size()
        self._base_width = width
        total_width, total_height = width, height
        if self._sub_open >= 0 and self._submenu is not None:
            child_w, child_h = self._submenu._intrinsic_size()
            top, _ = self._rows()[self._sub_open]
            child_top = max(PAD_Y, top - PAD_Y)
            total_width = width + _SUBMENU_GAP + child_w
            total_height = max(height, child_top + child_h + PAD_Y)
        self.setFixedSize(int(total_width), int(total_height))

    # ------------------------------------------------------------------ showing
    def _host_window(self) -> QWidget | None:
        parent = self._host_hint
        if parent is None:
            return None
        window = parent.window()
        return window if window is not parent or parent.isWindow() else None

    def _fits_overlay(self, host: QWidget) -> bool:
        if host is None or not host.isVisible():
            return False
        width, height = self._intrinsic_size()
        child_w = 0
        if self._sub_open >= 0 and self._submenu is not None:
            child_w = self._submenu._intrinsic_size()[0] - 14
        return host.width() >= width + child_w + 8 and host.height() >= height + 8

    def popup(self, position: QPoint) -> None:  # noqa: N802
        host = self._host_window()
        if self._fits_overlay(host):
            self._show_overlay(host, position)
        else:
            self._show_native(position)

    def _show_overlay(self, host: QWidget, global_position: QPoint) -> None:
        self._overlay = True
        self._host = host
        self.setParent(host)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._relayout()
        local = host.mapFromGlobal(global_position)
        local.setX(max(4, min(local.x(), host.width() - self.width() - 4)))
        local.setY(max(4, min(local.y(), host.height() - self.height() - 4)))
        self.move(local)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        QApplication.instance().installEventFilter(self)

    def _show_native(self, position: QPoint) -> None:
        self._overlay = False
        self._host = None
        self.setParent(None)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self._apply_native_corners()
        self._relayout()
        self._apply_round_mask()
        self._place(position)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _apply_native_corners(self) -> None:
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(_DWMWCP_DONOTROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:  # pragma: no cover - non-Windows
            pass

    def _apply_round_mask(self) -> None:
        """Physical clipping: shadows and hit-testing follow the mask, not a rect."""
        path = QPainterPath()
        width, height = self._intrinsic_size()
        path.addRoundedRect(QRectF(0, 0, width, height), self._radius, self._radius)
        if self._submenu is not None and self._sub_open >= 0:
            sub = self._sub_rect()
            path.addRoundedRect(sub, self._radius, self._radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _place(self, position: QPoint) -> None:
        screen = self.screen()
        point = QPoint(position)
        if screen is not None:
            geo = screen.availableGeometry()
            if point.x() + self.width() > geo.right():
                point.setX(max(geo.left(), geo.right() - self.width()))
            if point.y() + self.height() > geo.bottom():
                point.setY(max(geo.top(), point.y() - self.height()))
        self.move(point)

    def exec(self, position: QPoint):  # noqa: N802
        self._active = None
        self.popup(position)
        loop = QEventLoop(self)
        self._loop = loop
        loop.exec()
        return self._active

    # ------------------------------------------------------------------- closing
    def _release(self) -> None:
        self._reset_submenu()
        QApplication.instance().removeEventFilter(self)
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        self.hide()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._release()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        super().hideEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if self._overlay and self.isVisible():
            if event.type() == QEvent.Type.MouseButtonPress:
                global_pos = event.globalPosition().toPoint()
                local = self.mapFromGlobal(global_pos)
                if not self.rect().contains(local):
                    self._release()
                elif self._submenu is None and local.x() >= self._base_width:
                    self._release()
            elif event.type() in (
                QEvent.Type.WindowDeactivate,
                QEvent.Type.ApplicationDeactivate,
            ):
                self._release()
        return False

    # ------------------------------------------------------------- submenu state
    def _reset_submenu(self) -> None:
        if self._submenu is not None:
            self._submenu.hide()
        self._submenu = None
        self._sub_open = -1
        self._sub_hover = -1
        self._relayout()

    def _open_submenu(self, index: int) -> None:
        item = self._items[index]
        if not isinstance(item, PopupMenu):
            return
        if self._sub_open == index:
            return
        self._submenu = item
        self._sub_open = index
        self._sub_hover = -1
        self._relayout()
        if self._overlay and self._host is not None:
            local = self.pos()
            local.setX(max(4, min(local.x(), self._host.width() - self.width() - 4)))
            local.setY(max(4, min(local.y(), self._host.height() - self.height() - 4)))
            self.move(local)
        else:
            self._apply_round_mask()
            self._place(self.pos())

    def _sub_rect(self) -> QRectF:
        if self._submenu is None or self._sub_open < 0:
            return QRectF()
        top, _ = self._rows()[self._sub_open]
        child_w, child_h = self._submenu._intrinsic_size()
        return QRectF(self._base_width + _SUBMENU_GAP, max(PAD_Y, top - PAD_Y), child_w, child_h)

    # ------------------------------------------------------------------- events
    def _item_at(self, y: int) -> int:
        for index, (top, height) in enumerate(self._rows()):
            if top <= y < top + height:
                return index
        return -1

    def _sub_item_at(self, point: QPoint) -> int:
        if self._submenu is None:
            return -1
        rect = self._sub_rect()
        inside = (
            rect.left() <= point.x() <= rect.right()
            and rect.top() <= point.y() <= rect.bottom()
        )
        if not inside:
            return -1
        return self._submenu._item_at(int(point.y() - rect.top()))

    def _in_bridge(self, point) -> bool:
        """Keep the submenu open while the pointer crosses the gap to it.

        With a visible 6 px gap between the panels the pointer briefly leaves
        both panels; treating that as "moved away" closed the submenu before it
        could be clicked. The bridge is the union of the parent row, the gap and
        the submenu rect.
        """
        if self._submenu is None or self._sub_open < 0:
            return False
        rect = self._sub_rect()
        if rect.left() <= point.x() <= rect.right() and rect.top() <= point.y() <= rect.bottom():
            return True
        row_top, row_h = self._rows()[self._sub_open]
        row_right = self._base_width
        bridge_left = min(row_right - 2, rect.left())
        bridge_right = max(row_right, rect.left() + 2)
        bridge_top = min(row_top, rect.top())
        bridge_bottom = max(row_top + row_h, rect.bottom())
        return (
            bridge_left <= point.x() <= bridge_right
            and bridge_top <= point.y() <= bridge_bottom
        )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        sub_index = self._sub_item_at(point)
        if sub_index >= 0:
            if sub_index != self._sub_hover:
                self._sub_hover = sub_index
                self.update()
            return
        if self._sub_open >= 0 and not self._in_bridge(point):
            self._reset_submenu()
        index = self._item_at(point.y()) if point.x() < self._base_width else -1
        if index != self._hover:
            self._hover = index
            self.update()
        if index >= 0 and isinstance(self._items[index], PopupMenu):
            self._open_submenu(index)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        sub_index = self._sub_item_at(point)
        if sub_index >= 0 and self._submenu is not None:
            item = self._submenu._items[sub_index]
            if isinstance(item, PopupAction) and item.isEnabled():
                if item.isCheckable():
                    item.setChecked(not item.isChecked())
                self._active = item
                item.triggered.emit()
                self._release()
            return
        if point.x() >= self._base_width:
            self._release()
            return
        index = self._item_at(point.y())
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
            self._release()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._release()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ painting
    def _panel(self, painter: QPainter, rect: QRectF) -> None:
        palette = theme().palette
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.fillPath(path, QColor(palette.elevated))
        painter.setPen(QPen(QColor(palette.border), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self._intrinsic_size()
        self._panel(painter, QRectF(0.5, 0.5, width - 1, height - 1))
        self._paint_items(painter, QPoint(0, 0), self._items, self._hover, width)
        if self._submenu is not None and self._sub_open >= 0:
            sub_rect = self._sub_rect()
            self._panel(
                painter,
                QRectF(sub_rect.left() + 0.5, sub_rect.top() + 0.5, sub_rect.width() - 1, sub_rect.height() - 1),
            )
            self._paint_items(
                painter,
                QPoint(int(sub_rect.left()), int(sub_rect.top())),
                self._submenu._items,
                self._sub_hover,
                int(sub_rect.width()),
            )
        painter.end()

    def _paint_items(
        self,
        painter: QPainter,
        origin: QPoint,
        items: list,
        hover: int,
        panel_width: int,
    ) -> None:
        palette = theme().palette
        metrics = QFontMetrics(self._row_font)
        rows = []
        y = PAD_Y
        row_h = max(ROW_HEIGHT, metrics.height() + 10)
        for item in items:
            rows.append((y, 9 if item is None else row_h))
            y += 9 if item is None else row_h
        has_checks = any(isinstance(item, PopupAction) and item.isCheckable() for item in items)
        for index, item in enumerate(items):
            top, height = rows[index]
            if item is None:
                painter.setPen(QPen(rgba(palette.text, 0.10), 1))
                painter.drawLine(
                    int(origin.x() + PAD_X - 2),
                    int(origin.y() + top + height / 2),
                    int(origin.x() + panel_width - PAD_X + 2),
                    int(origin.y() + top + height / 2),
                )
                continue
            row = QRectF(origin.x() + 5, origin.y() + top, panel_width - 10, height)
            if index == hover:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(rgba(palette.accent, 0.16))
                painter.drawRoundedRect(row, self._radius * 0.55, self._radius * 0.55)
            if isinstance(item, PopupMenu):
                text = item._owner_title
                enabled = True
            else:
                text = item.text()
                enabled = item.isEnabled()
            ink = rgba(palette.text, 1.0 if enabled else 0.42)
            x = row.left() + PAD_X
            painter.setFont(self._row_font)
            if has_checks:
                if isinstance(item, PopupAction) and item.isCheckable() and item.isChecked():
                    icons.draw(
                        painter,
                        "check",
                        QRectF(x, row.center().y() - 6, 12, 12),
                        QColor(palette.accent),
                    )
                x += 20
            if isinstance(item, PopupAction) and item._icon:
                icons.draw(painter, item._icon, QRectF(x, row.center().y() - 9, 18, 18), QColor(ink))
                x += 24
            text_rect = QRectF(x, row.top(), row.right() - x - 18, row.height())
            painter.setPen(QPen(QColor(ink)))
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
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

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.width(), self.height())


def list_popup(
    items: list[str],
    current: int,
    on_pick: Callable[[int], None],
    parent: QWidget | None = None,
) -> PopupMenu:
    """Rounded list popup used by combo boxes (overlay when it fits)."""
    menu = PopupMenu(parent)

    def choose(index: int) -> None:
        on_pick(index)
        menu._release()

    for index, label in enumerate(items):
        action = PopupAction(label, checkable=True, checked=index == current)
        action.triggered.connect(lambda idx=index: choose(idx))
        menu._items.append(action)
    menu._relayout()
    return menu

