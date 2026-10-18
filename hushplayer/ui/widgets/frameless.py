"""Frameless main window with native Windows resize/maximise behaviour."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ...core.logging_setup import get_logger
from ...core.theme import qcolor, theme

log = get_logger("ui.window")

BORDER = 6

HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


def _enable_dwm_rounding(widget: QWidget) -> None:
    """Ask DWM for rounded corners (Windows 11) and a dark title bar."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
    except Exception:
        return
    try:
        value = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), 33, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass
    try:
        dark = ctypes.c_int(1 if theme().is_dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
    except Exception:
        pass


def _set_app_user_model_id(app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass


class FramelessWindow(QWidget):
    """A top-level window drawn entirely by HushPlayer."""

    closing = Signal()

    def __init__(self, *, resizable: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        flags = Qt.Window | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
        flags |= Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setMouseTracking(True)
        self._resizable = resizable
        self._maximized = False
        self._normal_geometry = QRect()
        self._titlebar: QWidget | None = None
        self._dwm_applied = False

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)
        self.container = QWidget(self)
        self.container.setObjectName("HushWindowRoot")
        self.container.setAttribute(Qt.WA_StyledBackground, True)
        self._body = QVBoxLayout(self.container)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        self._root.addWidget(self.container)

    # ------------------------------------------------------------------ api
    def set_titlebar(self, titlebar: QWidget) -> None:
        self._titlebar = titlebar
        self._body.addWidget(titlebar)

    def body_layout(self) -> QVBoxLayout:
        return self._body

    @property
    def is_maximized(self) -> bool:
        return self._maximized

    def toggle_maximize(self) -> None:
        if self.isMaximized() and not self._maximized:
            self.showNormal()
            return
        if self._maximized:
            self.showNormal()
        else:
            self.showMaximized()

    def minimize(self) -> None:
        self.showMinimized()

    def close_window(self) -> None:
        self.closing.emit()
        self.close()

    # --------------------------------------------------------------- events
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._dwm_applied:
            self._dwm_applied = True
            _enable_dwm_rounding(self)
        self._update_root_style()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            maximized = bool(self.windowState() & Qt.WindowMaximized)
            if maximized != self._maximized:
                self._maximized = maximized
                if not maximized:
                    self._normal_geometry = QRect()
                self._update_root_style()
                bar = self._titlebar
                if bar is not None and hasattr(bar, "set_maximized"):
                    bar.set_maximized(maximized)  # type: ignore[attr-defined]

    def _update_root_style(self) -> None:
        palette = theme().palette
        radius = 0 if self._maximized else 10
        self.container.setStyleSheet(
            f"#HushWindowRoot {{ background: {palette.window};"
            f" border-top-left-radius: {radius}px; border-top-right-radius: {radius}px;"
            f" border-bottom-left-radius: {radius}px; border-bottom-right-radius: {radius}px; }}"
        )

    def nativeEvent(self, event_type, message):  # noqa: N802
        if sys.platform == "win32" and self._resizable and not self._maximized:
            try:
                msg = wintypes.MSG.from_address(int(message))
            except Exception:
                return super().nativeEvent(event_type, message)
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                dpr = self.devicePixelRatioF() or 1.0
                local = self.mapFromGlobal(QPoint(int(x / dpr), int(y / dpr)))
                return self._hit_test(local, QPoint(int(x / dpr), int(y / dpr)))
        return super().nativeEvent(event_type, message)

    def _hit_test(self, local: QPoint, global_pos: QPoint) -> tuple[bool, int]:
        width = self.width()
        height = self.height()
        left = local.x() <= BORDER
        right = local.x() >= width - BORDER
        top = local.y() <= BORDER
        bottom = local.y() >= height - BORDER
        if top and left:
            return (True, HTTOPLEFT)
        if top and right:
            return (True, HTTOPRIGHT)
        if bottom and left:
            return (True, HTBOTTOMLEFT)
        if bottom and right:
            return (True, HTBOTTOMRIGHT)
        if left:
            return (True, HTLEFT)
        if right:
            return (True, HTRIGHT)
        if top:
            return (True, HTTOP)
        if bottom:
            return (True, HTBOTTOM)
        return (False, 0)

    def update_cursor_for(self, pos: QPoint) -> None:
        """Give the window edges the native resize cursor."""
        if self._maximized or not self._resizable:
            self.unsetCursor()
            return
        right = pos.x() >= self.width() - BORDER
        left = pos.x() <= BORDER
        top = pos.y() <= BORDER
        bottom = pos.y() >= self.height() - BORDER
        shape = Qt.ArrowCursor
        if (top and left) or (bottom and right):
            shape = Qt.SizeFDiagCursor
        elif (top and right) or (bottom and left):
            shape = Qt.SizeBDiagCursor
        elif left or right:
            shape = Qt.SizeHorCursor
        elif top or bottom:
            shape = Qt.SizeVerCursor
        self.setCursor(shape) if shape != Qt.ArrowCursor else self.unsetCursor()


def center_on_screen(widget: QWidget, *, screen_ratio: float = 0.72) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    width = max(960, int(available.width() * screen_ratio))
    height = max(680, int(available.height() * screen_ratio))
    width = min(width, available.width())
    height = min(height, available.height())
    widget.resize(QSize(width, height))
    widget.move(
        available.x() + (available.width() - width) // 2,
        available.y() + (available.height() - height) // 2,
    )


class WindowDragHandle(QWidget):
    """Transparent strip that drags the window and toggles maximise on double click."""

    def __init__(self, window: FramelessWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.ArrowCursor)
        self._press_pos: QPoint | None = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._window.toggle_maximize()
        super().mouseDoubleClickEvent(event)


def apply_dark_mode(widget: QWidget) -> None:
    _enable_dwm_rounding(widget)


def screen_for_widget(widget: QWidget):
    screen = widget.screen() or QGuiApplication.primaryScreen()
    return screen


def ensure_on_screen(widget: QWidget, geometry: QRect) -> QRect:
    """Clamp a stored geometry to a currently available screen."""
    if geometry.isNull() or geometry.width() < 200 or geometry.height() < 150:
        return geometry
    for screen in QGuiApplication.screens():
        available = screen.availableGeometry()
        if available.intersects(geometry):
            rect = QRect(geometry)
            width = min(rect.width(), available.width())
            height = min(rect.height(), available.height())
            x = min(max(rect.x(), available.x()), available.right() - width)
            y = min(max(rect.y(), available.y()), available.bottom() - height)
            return QRect(x, y, width, height)
    primary = QGuiApplication.primaryScreen()
    if primary is not None:
        available = primary.availableGeometry()
        return QRect(
            available.center().x() - geometry.width() // 2,
            available.center().y() - geometry.height() // 2,
            min(geometry.width(), available.width()),
            min(geometry.height(), available.height()),
        )
    return geometry


__all__ = [
    "FramelessWindow",
    "WindowDragHandle",
    "center_on_screen",
    "ensure_on_screen",
    "_set_app_user_model_id",
    "apply_dark_mode",
]
