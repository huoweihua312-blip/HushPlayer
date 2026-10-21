"""Frameless main window with native Windows resize/maximise behaviour."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainterPath, QRegion
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ...core.logging_setup import get_logger
from ...core.theme import qcolor, theme

log = get_logger("ui.window")

BORDER = 6
HANDLE = 5

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


def _set_dwm_attribute(hwnd: int, attribute: int, value: int) -> None:
    try:
        data = ctypes.c_int(value)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), attribute, ctypes.byref(data), ctypes.sizeof(data)
        )
    except Exception:
        pass


def _enable_dwm_rounding(widget: QWidget, *, maximized: bool | None = None) -> None:
    """Ask DWM for rounded corners (Windows 11) and a dark title bar.

    A maximized frameless window still receives DWM's 1px frame, which shows up
    as a light ring around the screen edge (very visible on 2560x1440). Turning
    rounding off and setting the border colour to NONE removes it; restoring the
    window re-enables both.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
    except Exception:
        return
    if maximized is None:
        maximized = bool(widget.windowState() & Qt.WindowMaximized)
    if maximized:
        _set_dwm_attribute(hwnd, 33, 1)  # DWMWCP_DONOTROUND
        _set_dwm_attribute(hwnd, 34, 0xFFFFFFFE)  # DWMWA_COLOR_NONE
    else:
        _set_dwm_attribute(hwnd, 33, 2)  # DWMWCP_ROUND
        _set_dwm_attribute(hwnd, 34, 0xFFFFFFFF)  # DWMWA_COLOR_DEFAULT
    try:
        dark = ctypes.c_int(1 if theme().is_dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), 20, ctypes.byref(dark), ctypes.sizeof(dark)
        )
    except Exception:
        pass


def _enable_native_resize_border(widget: QWidget) -> None:
    """Give the frameless window WS_THICKFRAME so Windows resizes it natively.

    Qt creates frameless windows as WS_POPUP without WS_THICKFRAME; without the
    style DefWindowProc refuses to start a resize loop even when a hit test
    asks for HTLEFT/HTTOP. Adding the style back keeps the custom title bar but
    restores the native 8px resize border and the resize cursors.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        WS_THICKFRAME = 0x00040000
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE)
        if not style & WS_THICKFRAME:
            user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE, style | WS_THICKFRAME)
            user32.SetWindowPos(
                wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
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

        # Windows does not reliably start a native resize loop from a
        # WM_NCHITTEST override on frameless windows (and Qt's synthetic hit
        # test can be skipped entirely), so drag-resizing is driven by thin
        # edge widgets that call QWindow.startSystemResize().
        self._edge_handles: list[EdgeHandle] = []
        if resizable:
            self._build_edge_handles()

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
        """Maximise or restore using the native window manager.

        Restoring must never leave the window at screen size: some Windows
        themes report a bogus ``normalGeometry()`` after a maximise that was
        triggered from a restored session, so HushPlayer tracks its own
        last normal geometry and re-applies it after ``showNormal()``.
        """
        if self.isMaximized():
            self.showNormal()
            self._maximized = False
            self._sync_maximized_ui()
            QTimer.singleShot(0, self._restore_normal_geometry)
            return
        geometry = QRect(self.geometry())
        if self._usable_normal_geometry(geometry):
            self._normal_geometry = geometry
        self.showMaximized()
        self._maximized = True
        self._sync_maximized_ui()

    def _sync_maximized_ui(self) -> None:
        _enable_dwm_rounding(self, maximized=self._maximized)
        self._update_root_style()
        self._update_round_mask()
        self._layout_edge_handles()
        bar = self._titlebar
        if bar is not None and hasattr(bar, "set_maximized"):
            bar.set_maximized(self._maximized)  # type: ignore[attr-defined]

    # -------------------------------------------------------- edge resizing
    def _build_edge_handles(self) -> None:
        specs = (
            ("top", Qt.Edges.TopEdge, Qt.CursorShape.SizeVerCursor),
            ("bottom", Qt.Edges.BottomEdge, Qt.CursorShape.SizeVerCursor),
            ("left", Qt.Edges.LeftEdge, Qt.CursorShape.SizeHorCursor),
            ("right", Qt.Edges.RightEdge, Qt.CursorShape.SizeHorCursor),
            ("top-left", Qt.Edges.TopEdge | Qt.Edges.LeftEdge, Qt.CursorShape.SizeFDiagCursor),
            ("top-right", Qt.Edges.TopEdge | Qt.Edges.RightEdge, Qt.CursorShape.SizeBDiagCursor),
            ("bottom-left", Qt.Edges.BottomEdge | Qt.Edges.LeftEdge, Qt.CursorShape.SizeBDiagCursor),
            ("bottom-right", Qt.Edges.BottomEdge | Qt.Edges.RightEdge, Qt.CursorShape.SizeFDiagCursor),
        )
        for name, edges, cursor in specs:
            handle = EdgeHandle(self, edges, name=name)
            handle.setCursor(cursor)
            self._edge_handles.append(handle)

    def _layout_edge_handles(self) -> None:
        if not self._edge_handles:
            return
        visible = not self._maximized and not self.isFullScreen()
        width = self.width()
        height = self.height()
        grip = HANDLE
        corner = HANDLE * 2
        rects = {
            "top": QRect(corner, 0, max(0, width - corner * 2), grip),
            "bottom": QRect(corner, height - grip, max(0, width - corner * 2), grip),
            "left": QRect(0, corner, grip, max(0, height - corner * 2)),
            "right": QRect(width - grip, corner, grip, max(0, height - corner * 2)),
            "top-left": QRect(0, 0, corner, corner),
            "top-right": QRect(width - corner, 0, corner, corner),
            "bottom-left": QRect(0, height - corner, corner, corner),
            "bottom-right": QRect(width - corner, height - corner, corner, corner),
        }
        for handle in self._edge_handles:
            handle.setGeometry(rects.get(handle.edge_name, QRect()))
            handle.setVisible(visible)
            if visible:
                handle.raise_()

    def _update_round_mask(self) -> None:
        """Clip the window to rounded corners on every Windows version.

        Windows 11 rounds frameless windows through DWM, but Windows 10 (and
        some 1080p machines) draws square corners, which shows the wallpaper in
        the corners. A window region keeps the shape identical everywhere.
        """
        if self._maximized or self.isFullScreen():
            self.clearMask()
            return
        try:
            radius = max(8, int(theme().scaled(10, factor=0.6)))
        except Exception:  # noqa: BLE001 - theme may not exist in tiny probes
            radius = 10
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.0, 0.0, float(self.width()), float(self.height())), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    @staticmethod
    def _usable_normal_geometry(geometry: QRect) -> bool:
        if geometry.width() < 480 or geometry.height() < 360:
            return False
        screen = QGuiApplication.screenAt(geometry.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return True
        # A window dragged to (almost) the whole screen is still a valid
        # restore target; only reject sizes that look like a broken snapshot.
        return True

    def _restore_normal_geometry(self) -> None:
        if self.isMaximized() or self.isMinimized():
            return
        geometry = QRect(self._normal_geometry)
        if not self._usable_normal_geometry(geometry):
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is None:
                return
            available = screen.availableGeometry()
            width = max(960, int(available.width() * 0.78))
            height = max(680, int(available.height() * 0.78))
            geometry = QRect(
                available.x() + (available.width() - width) // 2,
                available.y() + (available.height() - height) // 2,
                width,
                height,
            )
        self.setGeometry(ensure_on_screen(self, geometry))

    def normal_geometry(self) -> QRect:
        """Geometry that ``showNormal()`` should return to."""
        if self.isMaximized():
            if self._usable_normal_geometry(self._normal_geometry):
                return QRect(self._normal_geometry)
            fallback = self.normalGeometry()
            if self._usable_normal_geometry(fallback):
                return fallback
            return QRect(self._normal_geometry)
        return QRect(self.geometry())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._remember_normal_geometry()
        self._layout_edge_handles()
        self._update_round_mask()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._remember_normal_geometry()

    def _remember_normal_geometry(self) -> None:
        if self.isMaximized() or self.isMinimized() or self.isFullScreen():
            return
        geometry = QRect(self.geometry())
        if self._usable_normal_geometry(geometry):
            self._normal_geometry = geometry

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
            _enable_native_resize_border(self)
            _enable_dwm_rounding(self)
        self._update_root_style()
        self._update_round_mask()
        self._layout_edge_handles()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            maximized = bool(self.windowState() & Qt.WindowMaximized)
            if maximized != self._maximized:
                self._maximized = maximized
                self._sync_maximized_ui()

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


class EdgeHandle(QWidget):
    """Thin invisible strip that starts a native resize loop on drag."""

    def __init__(self, window: "FramelessWindow", edges, *, name: str) -> None:
        super().__init__(window)
        self._window = window
        self._edges = edges
        self.edge_name = name
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemResize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


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
    "EdgeHandle",
    "FramelessWindow",
    "WindowDragHandle",
    "center_on_screen",
    "ensure_on_screen",
    "_set_app_user_model_id",
    "apply_dark_mode",
]
