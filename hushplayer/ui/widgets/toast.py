"""In-window toast notifications."""

from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from ...core.icons import draw as draw_icon
from ...core.theme import qcolor, rgba, theme


class Toast(QWidget):
    closed = Signal(object)

    def __init__(self, text: str, kind: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._kind = kind
        self._opacity = 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        font = theme().font(9.2, 500)
        metrics = QFontMetrics(font)
        width = min(560, metrics.horizontalAdvance(text) + 54)
        self.setFixedSize(max(120, width), 38)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(theme().duration(180))
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    def set_text(self, text: str) -> None:
        self._text = text
        metrics = QFontMetrics(theme().font(9.2, 500))
        width = min(560, metrics.horizontalAdvance(text) + 54)
        self.setFixedSize(max(120, width), self.height())
        self.update()

    def appear(self) -> None:
        self.show()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def dismiss(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._finish)
        self._fade.start()

    def _finish(self) -> None:
        self.closed.emit(self)
        self.hide()
        self.deleteLater()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.dismiss()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        background = qcolor(palette.elevated if palette.is_dark else "#FFFFFF")
        painter.setPen(QPen(rgba(palette.text, 0.10), 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        icon_name = {"success": "check", "error": "warning", "warning": "warning"}.get(self._kind, "info")
        color = {
            "success": palette.success,
            "error": palette.danger,
            "warning": palette.warning,
        }.get(self._kind, palette.accent)
        draw_icon(
            painter,
            icon_name,
            QRectF(16, (self.height() - 15) / 2, 15, 15),
            qcolor(color),
        )
        painter.setFont(theme().font(9.2, 500))
        painter.setPen(QPen(rgba(palette.text, 0.92)))
        painter.drawText(
            QRectF(40, 0, self.width() - 58, self.height()),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            QFontMetrics(theme().font(9.2, 500)).elidedText(
                self._text, Qt.ElideRight, self.width() - 58
            ),
        )
        painter.end()


class ToastHost(QWidget):
    """Overlay manager; call :meth:`show_message` from anywhere."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._toasts: list[Toast] = []
        self._offset_bottom = 110
        self._last_toast: Toast | None = None
        self._last_kind = ""
        self._last_at = 0.0

    def set_bottom_offset(self, offset: int) -> None:
        self._offset_bottom = offset
        self._relayout()

    def show_message(self, text: str, kind: str = "info", *, timeout: int = 2800) -> Toast:
        now = time.monotonic()
        # Three lines of "source unavailable / switched / playing" used to
        # stack on top of the bar; keep one live line per kind instead.
        if (
            self._last_toast is not None
            and self._last_kind == kind
            and now - self._last_at < 0.9
            and self._last_toast in self._toasts
        ):
            self._last_toast.set_text(text)
            self._last_at = now
            self._relayout()
            return self._last_toast
        toast = Toast(text, kind, self)
        toast.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        toast.closed.connect(self._on_closed)
        self._toasts.append(toast)
        while len(self._toasts) > 3:
            oldest = self._toasts.pop(0)
            oldest.hide()
            oldest.deleteLater()
        toast.appear()
        self._relayout()
        QTimer.singleShot(max(800, timeout), toast.dismiss)
        self._last_toast = toast
        self._last_kind = kind
        self._last_at = now
        return toast

    def _on_closed(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._relayout()

    def _relayout(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(0, 0, parent.width(), parent.height())
        y = parent.height() - self._offset_bottom
        for toast in reversed(self._toasts):
            x = int((self.width() - toast.width()) / 2)
            toast.move(x, int(y - toast.height()))
            toast.raise_()
            y -= toast.height() + 8

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()


__all__ = ["Toast", "ToastHost"]
