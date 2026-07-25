"""Small DPI-friendly QPainter icons for UI V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from app.ui_v2.theme.tokens import Theme


IconName = Literal[
    "favorite",
    "favorite_filled",
    "playing",
    "local",
    "online",
    "missing",
    "search",
    "sort_ascending",
    "sort_descending",
]
IconState = Literal["normal", "hover", "selected", "disabled"]


@dataclass(frozen=True, slots=True)
class IconPalette:
    normal: QColor
    hover: QColor
    selected: QColor
    disabled: QColor


def palette_for(theme: Theme) -> IconPalette:
    c = theme.colors
    return IconPalette(
        normal=QColor(c.secondary_text),
        hover=QColor(c.primary_text),
        selected=QColor(c.accent),
        disabled=QColor(c.disabled_text),
    )


def _heart_path(rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    left, top, width, height = rect.left(), rect.top(), rect.width(), rect.height()
    path.moveTo(left + width * 0.5, top + height * 0.88)
    path.cubicTo(left + width * 0.42, top + height * 0.8, left + width * 0.1, top + height * 0.59, left + width * 0.1, top + height * 0.34)
    path.cubicTo(left + width * 0.1, top + height * 0.14, left + width * 0.26, top + height * 0.06, left + width * 0.39, top + height * 0.13)
    path.cubicTo(left + width * 0.45, top + height * 0.16, left + width * 0.48, top + height * 0.22, left + width * 0.5, top + height * 0.25)
    path.cubicTo(left + width * 0.52, top + height * 0.22, left + width * 0.55, top + height * 0.16, left + width * 0.61, top + height * 0.13)
    path.cubicTo(left + width * 0.74, top + height * 0.06, left + width * 0.9, top + height * 0.14, left + width * 0.9, top + height * 0.34)
    path.cubicTo(left + width * 0.9, top + height * 0.59, left + width * 0.58, top + height * 0.8, left + width * 0.5, top + height * 0.88)
    path.closeSubpath()
    return path


def _paint_shape(painter: QPainter, name: IconName, rect: QRectF, color: QColor) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, max(1.35, rect.width() * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name in ("favorite", "favorite_filled"):
        path = _heart_path(rect)
        painter.setBrush(color if name == "favorite_filled" else Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    elif name == "playing":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for x, ratio in ((0.18, 0.42), (0.43, 0.78), (0.68, 0.58)):
            height = rect.height() * ratio
            bar = QRectF(rect.left() + rect.width() * x, rect.center().y() - height / 2, rect.width() * 0.14, height)
            painter.drawRoundedRect(bar, rect.width() * 0.07, rect.width() * 0.07)
    elif name == "local":
        body = rect.adjusted(rect.width() * 0.1, rect.height() * 0.25, -rect.width() * 0.1, -rect.height() * 0.12)
        painter.drawRoundedRect(body, rect.width() * 0.08, rect.width() * 0.08)
        painter.drawLine(rect.left() + rect.width() * 0.27, rect.top() + rect.height() * 0.25, rect.left() + rect.width() * 0.4, rect.top() + rect.height() * 0.12)
        painter.drawLine(rect.left() + rect.width() * 0.4, rect.top() + rect.height() * 0.12, rect.left() + rect.width() * 0.62, rect.top() + rect.height() * 0.12)
    elif name == "online":
        cloud = QPainterPath()
        cloud.moveTo(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.71)
        cloud.cubicTo(rect.left() + rect.width() * 0.01, rect.top() + rect.height() * 0.62, rect.left() + rect.width() * 0.1, rect.top() + rect.height() * 0.38, rect.left() + rect.width() * 0.32, rect.top() + rect.height() * 0.4)
        cloud.cubicTo(rect.left() + rect.width() * 0.39, rect.top() + rect.height() * 0.08, rect.left() + rect.width() * 0.77, rect.top() + rect.height() * 0.12, rect.left() + rect.width() * 0.78, rect.top() + rect.height() * 0.43)
        cloud.cubicTo(rect.left() + rect.width() * 1.02, rect.top() + rect.height() * 0.44, rect.left() + rect.width() * 1.02, rect.top() + rect.height() * 0.75, rect.left() + rect.width() * 0.77, rect.top() + rect.height() * 0.75)
        cloud.lineTo(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.75)
        painter.drawPath(cloud)
    elif name == "missing":
        painter.drawRoundedRect(rect.adjusted(rect.width() * 0.17, rect.height() * 0.08, -rect.width() * 0.17, -rect.height() * 0.08), rect.width() * 0.08, rect.width() * 0.08)
        painter.drawLine(rect.center().x(), rect.top() + rect.height() * 0.28, rect.center().x(), rect.top() + rect.height() * 0.57)
        painter.drawPoint(rect.center().x(), rect.top() + rect.height() * 0.72)
    elif name == "search":
        painter.drawEllipse(rect.adjusted(rect.width() * 0.1, rect.height() * 0.1, -rect.width() * 0.38, -rect.height() * 0.38))
        painter.drawLine(rect.left() + rect.width() * 0.59, rect.top() + rect.height() * 0.59, rect.left() + rect.width() * 0.86, rect.top() + rect.height() * 0.86)
    else:
        descending = name == "sort_descending"
        for row, x_ratio in enumerate((0.17, 0.17, 0.17)):
            y = rect.top() + rect.height() * (0.25 + row * 0.25)
            painter.drawLine(rect.left() + rect.width() * x_ratio, y, rect.left() + rect.width() * (0.72 - row * 0.12), y)
        direction = 0.68 if descending else 0.32
        opposite = 0.32 if descending else 0.68
        painter.drawLine(rect.left() + rect.width() * 0.82, rect.top() + rect.height() * direction, rect.left() + rect.width() * 0.82, rect.top() + rect.height() * opposite)
        painter.drawLine(rect.left() + rect.width() * 0.7, rect.top() + rect.height() * (direction - 0.12 if descending else direction + 0.12), rect.left() + rect.width() * 0.82, rect.top() + rect.height() * direction)
        painter.drawLine(rect.left() + rect.width() * 0.94, rect.top() + rect.height() * (direction - 0.12 if descending else direction + 0.12), rect.left() + rect.width() * 0.82, rect.top() + rect.height() * direction)
    painter.restore()


def paint_icon(painter: QPainter, name: IconName, rect: QRectF, theme: Theme, state: IconState = "normal") -> None:
    """Paint an icon directly, selecting the color from its semantic state."""
    colors = palette_for(theme)
    _paint_shape(painter, name, rect, getattr(colors, state))


def icon(name: IconName, theme: Theme, state: IconState = "normal") -> QIcon:
    """Build a multi-size QIcon so toolbar controls remain crisp on high DPI."""
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        paint_icon(painter, name, QRectF(1, 1, size - 2, size - 2), theme, state)
        painter.end()
        result.addPixmap(pixmap)
    return result


def favorite(theme: Theme, state: IconState = "normal") -> QIcon:
    return icon("favorite", theme, state)


def favorite_filled(theme: Theme, state: IconState = "selected") -> QIcon:
    return icon("favorite_filled", theme, state)


def playing(theme: Theme, state: IconState = "selected") -> QIcon:
    return icon("playing", theme, state)


def local(theme: Theme, state: IconState = "normal") -> QIcon:
    return icon("local", theme, state)


def online(theme: Theme, state: IconState = "normal") -> QIcon:
    return icon("online", theme, state)


def missing(theme: Theme, state: IconState = "disabled") -> QIcon:
    return icon("missing", theme, state)


def search(theme: Theme, state: IconState = "normal") -> QIcon:
    return icon("search", theme, state)


def sort_ascending(theme: Theme, state: IconState = "normal") -> QIcon:
    return icon("sort_ascending", theme, state)


def sort_descending(theme: Theme, state: IconState = "normal") -> QIcon:
    return icon("sort_descending", theme, state)
