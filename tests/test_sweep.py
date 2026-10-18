"""Soft-edged lyric sweep (BUG-06 regression guard).

The karaoke highlight must advance at pixel granularity: an integer
"characters sung" estimate is exactly the defect this round removed, so these
tests assert that the accent area grows continuously with the clock position.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPixmap

from hushplayer.model.lyrics import Word
from hushplayer.ui.widgets.sweep import (
    FEATHER,
    paint_sweep,
    sweep_pixels_for_line,
)

ACCENT = "#C95770"
TEXT = "穿过无人的跑道"


def _render(progress: float) -> QPixmap:
    pixmap = QPixmap(600, 80)
    pixmap.fill(QColor("black"))
    painter = QPainter(pixmap)
    paint_sweep(
        painter,
        text=TEXT,
        font=QFont("Segoe UI", 28),
        color=ACCENT,
        x=10,
        baseline=60,
        progress=progress,
    )
    painter.end()
    return pixmap


def _accent_pixels(pixmap: QPixmap) -> int:
    image = pixmap.toImage()
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.red() > 140 and color.green() < 120 and color.blue() < 150:
                count += 1
    return count


def test_accent_area_grows_with_progress(qapp):
    empty = _accent_pixels(_render(0.0))
    half = _accent_pixels(_render(150.0))
    full = _accent_pixels(_render(1000.0))
    assert empty == 0
    assert 0 < half < full


def test_sweep_is_pixel_granular(qapp):
    widths = [_accent_pixels(_render(float(x))) for x in (100, 104, 108, 112)]
    assert widths == sorted(widths)
    assert len(set(widths)) >= 2, widths  # sub-character steps change the result


def test_sweep_pixels_uses_word_timeline():
    metrics = QFontMetricsF(QFont("Segoe UI", 28))
    text = "hello world"
    words = [
        Word("hello ", 0, 500),
        Word("world", 500, 1500),
    ]
    total = metrics.horizontalAdvance(text)
    first = metrics.horizontalAdvance("hello ")
    assert sweep_pixels_for_line(metrics, text, progress=0.0, words=words) == 0
    at_first = sweep_pixels_for_line(metrics, text, progress=0.0, words=words, position=500)
    assert abs(at_first - first) < 1.5
    mid = sweep_pixels_for_line(metrics, text, progress=0.0, words=words, position=1000)
    assert first < mid < total
    end = sweep_pixels_for_line(metrics, text, progress=0.0, words=words, position=1600)
    assert abs(end - total) < 1.5


def test_sweep_pixels_falls_back_to_line_ratio():
    metrics = QFontMetricsF(QFont("Segoe UI", 20))
    text = "plain line"
    total = metrics.horizontalAdvance(text)
    assert sweep_pixels_for_line(metrics, text, progress=0.0) == 0
    half = sweep_pixels_for_line(metrics, text, progress=0.5)
    assert abs(half - total * 0.5) < 1.0


def test_feather_is_positive():
    assert FEATHER > 0
