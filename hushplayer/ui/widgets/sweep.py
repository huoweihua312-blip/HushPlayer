"""Soft-edged karaoke sweep painting.

The lyric highlight used to be a hard clip rectangle: the accent colour simply
stopped at a character boundary, so with ~100 ms position updates the sweep moved
in visible steps (BUG-06). Painting through an alpha gradient mask keeps the text
shaping intact while giving the sweep a continuous, feathered edge.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)

#: Width of the soft transition at the sweep edge, in logical pixels.
FEATHER = 3.0


def paint_sweep(
    painter: QPainter,
    *,
    text: str,
    font: QFont,
    color: QColor,
    x: float,
    baseline: float,
    progress: float,
    feather: float = FEATHER,
) -> bool:
    """Draw ``text`` in ``color`` but only the part left of ``progress`` pixels.

    Returns ``True`` when something was painted. ``progress`` is measured in
    logical pixels from the start of the string and may be fractional, which is
    what makes the highlight advance continuously instead of per glyph.
    """
    if not text or progress <= 0:
        return False
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text)
    if width <= 0:
        return False
    progress = min(progress, width)
    height = metrics.height()
    ascent = metrics.ascent()

    device = painter.device()
    dpr = max(1.0, device.devicePixelRatioF() if device is not None else 1.0)
    pix_w = max(2.0, width + feather * 2.0 + 2.0)
    pix_h = max(2.0, height + 2.0)
    pixmap = QPixmap(int(round(pix_w * dpr)), int(round(pix_h * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    inner = QPainter(pixmap)
    inner.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    inner.setFont(font)
    inner.setPen(QPen(color))
    inner.drawText(QPointF(feather, ascent + 1.0), text)

    # Keep only the left part, with a soft ramp around the sweep position.
    hard = max(0.0, progress - feather)
    total = max(1.0, progress + feather)
    mask = QLinearGradient(0.0, 0.0, total, 0.0)
    mask.setColorAt(0.0, QColor(0, 0, 0, 255))
    mask.setColorAt(min(1.0, hard / total), QColor(0, 0, 0, 255))
    mask.setColorAt(1.0, QColor(0, 0, 0, 0))
    inner.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    inner.fillRect(QRectF(0.0, 0.0, pix_w, pix_h), mask)
    inner.end()

    painter.drawPixmap(QPointF(x - feather, baseline - ascent - 1.0), pixmap)
    return True


def sweep_pixels_for_line(
    metrics: QFontMetricsF,
    text: str,
    *,
    progress: float,
    words=None,
    position: int = 0,
) -> float:
    """Pixel offset of the sweep for a lyric line.

    ``words`` (with real per-word timings) wins over the line-level ``progress``
    so Chinese character timings and English word timings both animate smoothly.
    """
    width = metrics.horizontalAdvance(text)
    if width <= 0:
        return 0.0
    if not words:
        return width * max(0.0, min(1.0, progress))
    consumed = 0.0
    for word in words:
        word_width = metrics.horizontalAdvance(word.text)
        if position >= word.end_ms:
            consumed += word_width
            continue
        if position <= word.start_ms:
            break
        span = max(1, word.end_ms - word.start_ms)
        consumed += word_width * max(0.0, min(1.0, (position - word.start_ms) / span))
        break
    return consumed


__all__ = ["paint_sweep", "sweep_pixels_for_line", "FEATHER"]
