"""封面取色与沉浸式环境光背景。

只做一次性的小图统计（24×24），不跑实时模糊，避免高负载。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient

from ..core.theme import mix

_CACHE: dict[tuple[int, str], "Mood"] = {}
_MAX_CACHE = 48


@dataclass(frozen=True)
class Mood:
    base: QColor
    glow_a: QColor
    glow_b: QColor
    accent: QColor
    light: bool = False

    def to_css(self) -> str:
        return f"{self.base.name()}|{self.glow_a.name()}|{self.glow_b.name()}|{self.accent.name()}"


NEUTRAL_DARK = Mood(
    base=QColor("#111114"),
    glow_a=QColor("#3a2530"),
    glow_b=QColor("#22242e"),
    accent=QColor("#C95770"),
)


def _vibrant(color: QColor, *, saturation: float = 1.25, value: float = 1.15) -> QColor:
    hue, sat, val, alpha = color.getHslF()
    if hue < 0:
        hue = 0.97
    sat = max(0.0, min(1.0, sat * saturation))
    val = max(0.0, min(1.0, val * value))
    return QColor.fromHslF(hue, sat, val, alpha)


def mood_for_pixmap(pixmap: QPixmap | None) -> Mood:
    """从封面提取一组柔和的背景色。"""
    if pixmap is None or pixmap.isNull():
        return NEUTRAL_DARK
    key = (pixmap.cacheKey(), "mood")
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    if image.isNull():
        return NEUTRAL_DARK
    small = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    buckets: dict[int, list[tuple[float, float, float, float]]] = {}
    total = 0
    for y in range(small.height()):
        for x in range(small.width()):
            color = QColor.fromRgba(small.pixel(x, y))
            hue_f, sat, val, _alpha = color.getHslF()
            if sat < 0.18 or val < 0.12:
                continue
            bucket = int(hue_f * 12) % 12 if hue_f >= 0 else 0
            buckets.setdefault(bucket, []).append((hue_f, sat, val, 0.5 + sat))
            total += 1
            if total > 1200:
                break

    if not buckets:
        mood = NEUTRAL_DARK
        _remember(key, mood)
        return mood

    ranked = sorted(
        buckets.items(),
        key=lambda item: sum(entry[3] for entry in item[1]) / max(1, len(item[1])),
        reverse=True,
    )
    primary_hue, primary_sat, primary_val = _average(ranked[0][1])
    primary = QColor.fromHslF(primary_hue, max(0.25, primary_sat), max(0.35, primary_val))
    if len(ranked) > 1:
        second_hue, second_sat, second_val = _average(ranked[1][1])
        secondary = QColor.fromHslF(second_hue, max(0.22, second_sat), max(0.3, second_val))
    else:
        secondary = mix(primary, QColor("#2b2f3a"), 0.55)

    base = mix(primary, QColor("#0a0a0d"), 0.87)
    glow_a = _vibrant(primary, saturation=1.1, value=1.05)
    glow_b = _vibrant(secondary, saturation=1.0, value=0.95)
    accent = _vibrant(primary, saturation=1.3, value=1.3)
    mood = Mood(base=base, glow_a=glow_a, glow_b=glow_b, accent=accent)
    _remember(key, mood)
    return mood


def _average(entries: list[tuple[float, float, float, float]]) -> tuple[float, float, float]:
    weight = 0.0
    hues = []
    sats = 0.0
    vals = 0.0
    for hue, sat, val, w in entries:
        hues.append((hue, w))
        sats += sat * w
        vals += val * w
        weight += w
    weight = max(1e-6, weight)
    # 色相取加权圆周平均，避免 0/1 边界跳变
    import math

    x = sum(math.cos(2 * math.pi * hue) * w for hue, w in hues) / weight
    y = sum(math.sin(2 * math.pi * hue) * w for hue, w in hues) / weight
    hue = (math.atan2(y, x) / (2 * math.pi)) % 1.0
    return hue, sats / weight, vals / weight


def _remember(key: tuple[int, str], mood: Mood) -> None:
    if len(_CACHE) > _MAX_CACHE:
        _CACHE.clear()
    _CACHE[key] = mood


def clear_mood_cache() -> None:
    _CACHE.clear()


def paint_ambient(
    painter: QPainter,
    rect: QRectF,
    mood: Mood,
    *,
    opacity: float = 1.0,
    coverage: float = 0.85,
) -> None:
    """绘制连续、柔和的封面氛围光（无实时模糊）。"""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setOpacity(opacity)

    base = QLinearGradient(rect.topLeft(), rect.bottomRight())
    base.setColorAt(0.0, mix(mood.base, mood.glow_b, 0.18))
    base.setColorAt(0.55, mood.base)
    base.setColorAt(1.0, mix(mood.base, QColor("#000000"), 0.28))
    painter.fillRect(rect, base)

    radius = max(rect.width(), rect.height()) * coverage
    glow = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.78),
        radius * 0.9,
    )
    glow.setColorAt(0.0, _with_alpha(mood.glow_a, 0.52))
    glow.setColorAt(0.45, _with_alpha(mood.glow_a, 0.10))
    glow.setColorAt(1.0, _with_alpha(mood.glow_a, 0.0))
    painter.fillRect(rect, glow)

    glow2 = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.88, rect.top() + rect.height() * 0.12),
        radius * 0.75,
    )
    glow2.setColorAt(0.0, _with_alpha(mood.glow_b, 0.22))
    glow2.setColorAt(0.5, _with_alpha(mood.glow_b, 0.06))
    glow2.setColorAt(1.0, _with_alpha(mood.glow_b, 0.0))
    painter.fillRect(rect, glow2)

    vignette = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.78)
    vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
    vignette.setColorAt(0.62, QColor(0, 0, 0, 0))
    vignette.setColorAt(1.0, QColor(0, 0, 0, 140))
    painter.fillRect(rect, vignette)
    painter.restore()


def _with_alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(max(0.0, min(1.0, alpha)))
    return out


def mood_for_track(track) -> Mood:
    if track is None:
        return NEUTRAL_DARK
    try:
        from .context import ctx

        return mood_for_pixmap(ctx().covers.pixmap(track, 96))
    except Exception:
        return NEUTRAL_DARK
