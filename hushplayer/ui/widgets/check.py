"""Self-drawn check box.

Qt's native ``QCheckBox`` indicator inherits the platform style and cannot be
styled reliably through QSS (the check glyph disappears once the indicator is
painted by us), so the import wizard and the close prompt use this widget
instead.  It follows the same visual language as the rest of HushPlayer:
16px rounded square, berry fill when checked, hand-drawn tick.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy

from ...core.theme import rgba, theme
from .common import HoverAnimation


class CheckBox(QAbstractButton):
    """A compact check box with an inline label."""

    toggled_by_user = Signal(bool)

    def __init__(self, text: str = "", *, parent=None, size: int = 16) -> None:
        super().__init__(parent)
        self._text = text
        self._size = size
        self._hover = HoverAnimation(self, 110)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setAccessibleName(text)
        self.toggled.connect(self._on_toggled)

    # ------------------------------------------------------------------ api
    def text(self) -> str:  # noqa: A003 - mirrors QAbstractButton
        return self._text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._text = text
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self):  # noqa: N802
        metrics = self.fontMetrics()
        gap = theme().scaled(8, factor=0.7)
        height = max(self._size, metrics.height())
        width = self._size + gap + metrics.horizontalAdvance(self._text)
        return self.minimumSizeHint().expandedTo(
            self._sized(width + 2, height)
        )

    def minimumSizeHint(self):  # noqa: N802
        metrics = self.fontMetrics()
        gap = theme().scaled(8, factor=0.7)
        height = max(self._size, metrics.height())
        width = self._size + gap + metrics.horizontalAdvance(self._text)
        return self._sized(width + 2, height)

    @staticmethod
    def _sized(width: int, height: int):
        from PySide6.QtCore import QSize

        return QSize(int(width), int(height))

    # --------------------------------------------------------------- events
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover.set_end(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover.set_end(0.0)
        super().leaveEvent(event)

    def _on_toggled(self, checked: bool) -> None:
        self.toggled_by_user.emit(checked)
        self.update()

    # -------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        box = QRectF(0.5, (self.height() - self._size) / 2.0, self._size, self._size)
        radius = theme().scaled(5, factor=0.6)
        hover = self._hover.value

        if self.isChecked():
            fill = rgba(palette.accent_hover if hover > 0.5 else palette.accent, 1.0)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(box, radius, radius)
            pen = QPen(rgba("#FFFFFF", 0.96), max(1.6, self._size * 0.11))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            left = box.left() + box.width() * 0.24
            right = box.left() + box.width() * 0.78
            mid_y = box.top() + box.height() * 0.53
            painter.drawPolyline(
                [
                    QPointF(left, mid_y),
                    QPointF(box.left() + box.width() * 0.42, box.top() + box.height() * 0.70),
                    QPointF(right, box.top() + box.height() * 0.32),
                ]
            )
        else:
            border = palette.accent if hover > 0.5 else palette.border_strong
            painter.setPen(QPen(rgba(border, 1.0), 1.2))
            painter.setBrush(rgba(palette.surface_alt, 1.0))
            painter.drawRoundedRect(box, radius, radius)

        if self._text:
            gap = theme().scaled(8, factor=0.7)
            text_rect = QRectF(
                box.right() + gap,
                0,
                self.width() - box.width() - gap,
                self.height(),
            )
            painter.setPen(rgba(palette.text, 0.92))
            painter.drawText(
                text_rect,
                Qt.AlignVCenter | Qt.AlignLeft,
                self._text,
            )

        if self.hasFocus() and not self.isChecked():
            painter.setPen(QPen(rgba(palette.accent, 0.75), 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                box.adjusted(-2, -2, 2, 2), radius + 2, radius + 2
            )
        painter.end()
