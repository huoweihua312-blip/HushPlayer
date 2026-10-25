"""A small, palette-driven hover tooltip.

Qt's own ``QToolTip`` follows the *system* colour scheme on Windows 11 in some
configurations, which produced dark tooltips with dark text in the light theme.
Drawing our own label keeps the contrast correct in both themes, and lets us
wrap long lines (source names can be very long) instead of running off-screen.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ...core.theme import css_rgba, theme

_TIP = None


def _tip_widget() -> "HoverTip":
    global _TIP
    if _TIP is None:
        _TIP = HoverTip()
    return _TIP


class HoverTip(QWidget):
    MAX_WIDTH = 420

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._label = QLabel(self)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(self.MAX_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 12, 8)
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(7000)
        self._timer.timeout.connect(self.hide)

    # ------------------------------------------------------------------ style
    def _restyle(self) -> None:
        palette = theme().palette
        self.setStyleSheet(
            "QWidget { background: %s; border: 1px solid %s; border-radius: 8px; }"
            "QLabel { color: %s; font-size: %dpx; background: transparent; border: none; }"
            % (
                css_rgba(palette.elevated, 0.98),
                css_rgba(palette.border, 0.9),
                css_rgba(palette.text, 0.95),
                theme().px(8.4),
            )
        )

    # -------------------------------------------------------------------- api
    def show_text(self, global_pos: QPoint, text: str) -> None:
        text = (text or "").strip()
        if not text:
            self.hide()
            return
        self._restyle()
        self._label.setText(text)
        self.adjustSize()

        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        width = min(self.sizeHint().width(), self.MAX_WIDTH)
        self.resize(width, self.sizeHint().height())
        x = min(max(area.left() + 4, global_pos.x() + 14), area.right() - width - 4)
        y = global_pos.y() + 20
        if y + self.height() > area.bottom() - 4:
            y = global_pos.y() - self.height() - 10
        self.move(x, max(area.top() + 4, y))
        self.show()
        self.raise_()
        self._timer.start()

    def hide_tip(self) -> None:
        self._timer.stop()
        self.hide()


def show_tip(global_pos: QPoint, text: str) -> None:
    _tip_widget().show_text(global_pos, text)


def hide_tip() -> None:
    if _TIP is not None:
        _TIP.hide_tip()


class ToolTipRouter(QObject):
    """Route every widget's native tooltip through :class:`HoverTip`.

    Qt's own tooltip is a plain rectangle drawn by the style — on Windows 11 it
    showed square corners and an OS-coloured border even in the dark theme, which
    the user spotted on the transport buttons ("外面还有边边角角").  Intercepting
    ``QEvent.ToolTip`` at the application level keeps a single themed look (the
    same rounded label the queue panel already uses) without touching every
    ``setToolTip`` call site.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            text = ""
            try:
                text = obj.toolTip() if hasattr(obj, "toolTip") else ""
            except Exception:  # noqa: BLE001
                text = ""
            if text:
                show_tip(QCursor.pos(), text)
            return True
        if kind in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            hide_tip()
        return False


_ROUTER: ToolTipRouter | None = None


def install_tooltip_router(app: QApplication) -> ToolTipRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = ToolTipRouter(app)
        app.installEventFilter(_ROUTER)
    return _ROUTER


def display_source(track) -> str:
    """Human label for a track's source; importers sometimes store raw ids."""
    name = (getattr(track, "source_name", "") or "").strip()
    if not name:
        return ""
    if name.startswith("user_source_") or name.startswith("user-source-"):
        return "自建音源"
    if len(name) > 18:
        return name[:17] + "…"
    return name


def tip_text(track) -> str:
    if track is None:
        return ""
    lines = [" · ".join(part for part in (track.title, track.artist, track.album) if part)]
    source = display_source(track) if getattr(track, "is_online", False) else ""
    if source:
        lines.append(f"来源：{source}")
    if getattr(track, "path", ""):
        lines.append(track.path)
    if getattr(track, "year", 0):
        lines.append(f"发行年份：{track.year}")
    return "\n".join(line for line in lines if line)
