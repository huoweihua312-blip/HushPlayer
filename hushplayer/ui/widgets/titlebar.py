"""Custom title bar: navigation cluster on the left, window controls on the right."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ...core.theme import qcolor, rgba, theme
from .common import IconButton
from .frameless import FramelessWindow


class WindowButton(IconButton):
    def __init__(self, icon_name: str, tooltip: str, *, danger: bool = False, parent=None) -> None:
        super().__init__(icon_name, size=38, icon_size=15, tooltip=tooltip, bg=False, parent=parent)
        self._danger = danger
        self.setFixedSize(38, 30)
        self._radius = 6

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter

        from ...core import icons

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        palette = theme().palette
        if self._hover.value > 0.01:
            if self._danger:
                color = qcolor("#E5484D")
            else:
                color = rgba(palette.text, 0.09)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect.adjusted(1, 2, -1, -2), 6, 6)
        color = (
            qcolor("#FFFFFF")
            if self._danger and self._hover.value > 0.4
            else rgba(palette.text, 0.55 + 0.35 * self._hover.value)
        )
        target = QRectF(0, 0, 15, 15)
        target.moveCenter(rect.center())
        icons.draw(painter, self._icon_name, target, color)
        painter.end()


class TitleBar(QWidget):
    sidebar_toggled = Signal()
    back_requested = Signal()
    forward_requested = Signal()
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, window: FramelessWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self._maximized = False
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(4)

        self.sidebar_button = IconButton("sidebar", size=30, icon_size=17, tooltip="显示 / 隐藏边栏")
        self.sidebar_button.clicked.connect(self.sidebar_toggled)
        self.back_button = IconButton("chevron_left", size=30, icon_size=17, tooltip="后退 (Alt+Left)")
        self.back_button.clicked.connect(self.back_requested)
        self.forward_button = IconButton("chevron_right", size=30, icon_size=17, tooltip="前进 (Alt+Right)")
        self.forward_button.clicked.connect(self.forward_requested)
        self.back_button.setEnabled(False)
        self.forward_button.setEnabled(False)

        layout.addWidget(self.sidebar_button)
        layout.addSpacing(2)
        layout.addWidget(self.back_button)
        layout.addWidget(self.forward_button)
        layout.addStretch(1)

        self.title_label = QLabel("")
        self.title_label.setFont(theme().font(9.5, 600))
        self.title_label.setStyleSheet(f"color: {theme().palette.text_secondary};")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title_label, 0, Qt.AlignCenter)
        layout.addStretch(1)

        self.minimize_button = WindowButton("minimize", "最小化")
        self.maximize_button = WindowButton("maximize", "最大化")
        self.close_button = WindowButton("close", "关闭", danger=True)
        self.minimize_button.clicked.connect(self.minimize_requested)
        self.maximize_button.clicked.connect(self.maximize_requested)
        self.close_button.clicked.connect(self.close_requested)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            layout.addWidget(button)

        # NOTE: only wire the request signals here for standalone previews.
        # MainWindow connects the same signals to its own handlers, so binding
        # window.toggle_maximize here as well made every click toggle twice
        # (maximise -> restore in the same event), i.e. the button appeared dead.
        self.minimize_requested.connect(window.minimize)
        self.close_requested.connect(window.close_window)

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = maximized
        self.maximize_button.set_icon("restore" if maximized else "maximize")
        self.maximize_button.setToolTip("还原" if maximized else "最大化")

    def set_history(self, can_back: bool, can_forward: bool) -> None:
        self.back_button.setEnabled(can_back)
        self.forward_button.setEnabled(can_forward)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    # --------------------------------------------------------------- events
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolor(theme().palette.window))
        painter.drawRect(self.rect())
        painter.setPen(QPen(rgba(theme().palette.border, 0.55), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._is_drag_area(event.position().toPoint()):
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._is_drag_area(event.position().toPoint()):
            self._window.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _is_drag_area(self, pos) -> bool:
        child = self.childAt(pos)
        return child is None or child is self.title_label

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        super().mouseMoveEvent(event)


__all__ = ["TitleBar", "WindowButton"]
