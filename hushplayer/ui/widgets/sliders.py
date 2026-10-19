"""Seek bar and volume slider, drawn by hand for a precise look."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core.theme import mix, qcolor, rgba, theme
from ...model.track import format_duration


class SeekBar(QWidget):
    seek_requested = Signal(int)
    drag_started = Signal()
    drag_finished = Signal()
    hover_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("播放进度")
        self._duration = 0
        self._position = 0
        self._dragging = False
        self._drag_value = 0
        self._hover = 0.0
        self._hover_x: float | None = None
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_hover_value)
        self.setFixedHeight(20)
        self.setMinimumWidth(120)
        self.setMaximumWidth(theme().scaled(420, factor=0.6))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------ api
    def set_duration(self, duration_ms: int) -> None:
        self._duration = max(0, int(duration_ms))
        self.update()

    def set_position(self, position_ms: int) -> None:
        if self._dragging:
            return
        self._position = max(0, int(position_ms))
        self.update()

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def position(self) -> int:
        return self._drag_value if self._dragging else self._position

    def _track_rect(self) -> QRectF:
        return QRectF(6, self.height() / 2 - 2, max(0, self.width() - 12), 4)

    def _value_to_x(self, value: int) -> float:
        rect = self._track_rect()
        if self._duration <= 0:
            return rect.left()
        ratio = max(0.0, min(1.0, value / self._duration))
        return rect.left() + rect.width() * ratio

    def _x_to_value(self, x: float) -> int:
        rect = self._track_rect()
        if rect.width() <= 0 or self._duration <= 0:
            return 0
        ratio = max(0.0, min(1.0, (x - rect.left()) / rect.width()))
        return int(round(ratio * self._duration))

    def _on_hover_value(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _animate(self, target: float) -> None:
        if theme().reduce_motion:
            self._on_hover_value(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    # --------------------------------------------------------------- events
    def enterEvent(self, event) -> None:  # noqa: N802
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._dragging:
            self._hover_x = None
            self._animate(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._duration > 0:
            self._dragging = True
            self._drag_value = self._x_to_value(event.position().x())
            self.drag_started.emit()
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._hover_x = event.position().x()
        if self._dragging:
            self._drag_value = self._x_to_value(self._hover_x)
            self.hover_changed.emit(self._drag_value)
        else:
            self.hover_changed.emit(self._x_to_value(self._hover_x))
        self._animate(1.0)
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            value = self._drag_value
            self.seek_requested.emit(value)
            self.drag_finished.emit()
            if not self.underMouse():
                self._hover_x = None
                self._animate(0.0)
            self.update()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._duration <= 0:
            return
        delta = 5000 if event.angleDelta().y() > 0 else -5000
        self.seek_requested.emit(max(0, min(self._duration, self._position + delta)))
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._duration <= 0:
            return super().keyPressEvent(event)
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            delta = -5000 if event.key() == Qt.Key_Left else 5000
            self.seek_requested.emit(max(0, min(self._duration, self._position + delta)))
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._track_rect()
        height = 4 + 2 * self._hover
        rect = QRectF(rect.left(), self.height() / 2 - height / 2, rect.width(), height)

        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(palette.text, 0.11))
        painter.drawRoundedRect(rect, height / 2, height / 2)

        position = self._drag_value if self._dragging else self._position
        played_width = self._value_to_x(position) - rect.left()
        if played_width > 0:
            played = QRectF(rect.left(), rect.top(), played_width, rect.height())
            gradient = QLinearGradient(played.topLeft(), played.topRight())
            start = qcolor(palette.accent)
            end = mix(palette.accent, palette.text, 0.18)
            gradient.setColorAt(0.0, start)
            gradient.setColorAt(1.0, end)
            painter.setBrush(gradient)
            painter.drawRoundedRect(played, height / 2, height / 2)

        knob_visible = self._hover > 0.05 or self._dragging
        if knob_visible and self._duration > 0:
            x = self._value_to_x(position)
            radius = 5.5 + 1.5 * self._hover
            painter.setBrush(qcolor(palette.accent_text) if palette.is_dark else QColor(255, 255, 255))
            shadow = QColor(0, 0, 0, 60)
            painter.setPen(QPen(shadow, 1))
            painter.drawEllipse(QPointF(x, self.height() / 2), radius, radius)
            painter.setPen(Qt.NoPen)
            painter.setBrush(qcolor(palette.accent))
            painter.drawEllipse(QPointF(x, self.height() / 2), radius - 1.6, radius - 1.6)

        # hover time bubble
        if self._hover_x is not None and self._duration > 0 and not self._dragging:
            value = self._x_to_value(self._hover_x)
            text = format_duration(value)
            font = theme().font(8.0, 600)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            width = metrics.horizontalAdvance(text) + 12
            bubble = QRectF(
                min(max(self._hover_x - width / 2, 0), self.width() - width),
                self.height() / 2 - 30,
                width,
                18,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.88))
            painter.drawRoundedRect(bubble, 5, 5)
            painter.setPen(QPen(qcolor(palette.window)))
            painter.drawText(bubble, Qt.AlignCenter, text)
        painter.end()


class VolumeSlider(QWidget):
    value_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("音量")
        self._value = 1.0
        self._hover = 0.0
        self._dragging = False
        self.setFixedSize(86, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self._value) > 0.001:
            self._value = value
            self.update()

    @property
    def value(self) -> float:
        return self._value

    def _rect(self) -> QRectF:
        return QRectF(2, self.height() / 2 - 2, self.width() - 4, 4)

    def _value_at(self, x: float) -> float:
        rect = self._rect()
        return max(0.0, min(1.0, (x - rect.left()) / max(1.0, rect.width())))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = 1.0
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if not self._dragging:
            self._hover = 0.0
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._apply(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._apply(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = 0.05 if event.angleDelta().y() > 0 else -0.05
        self._value = max(0.0, min(1.0, self._value + delta))
        self.value_changed.emit(self._value)
        self.update()
        event.accept()

    def _apply(self, x: float) -> None:
        value = self._value_at(x)
        self._value = value
        self.value_changed.emit(value)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(rgba(palette.text, 0.13))
        painter.drawRoundedRect(rect, 2, 2)
        filled = QRectF(rect.left(), rect.top(), rect.width() * self._value, rect.height())
        painter.setBrush(rgba(palette.text, 0.55 + 0.25 * self._hover))
        painter.drawRoundedRect(filled, 2, 2)
        if self._hover > 0.2 or self._dragging:
            x = rect.left() + rect.width() * self._value
            painter.setBrush(qcolor(palette.text))
            painter.drawEllipse(QPointF(x, self.height() / 2), 4.2, 4.2)
        painter.end()


__all__ = ["SeekBar", "VolumeSlider"]
