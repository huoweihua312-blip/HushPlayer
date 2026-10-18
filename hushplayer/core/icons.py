"""内置矢量图标集。

图标以 24x24 网格的 SVG 片段描述，颜色通过 ``{c}`` 占位符注入，
渲染结果按 (名称, 颜色, 尺寸, DPR) 缓存，避免重复解析。
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import qcolor

_STROKE = 1.7

ICONS: dict[str, str] = {
    "play": '<path d="M8.2 5.6v12.8a.72.72 0 001.09.61l10.1-6.4a.72.72 0 000-1.22L9.29 5a.72.72 0 00-1.09.6z" fill="{c}" stroke="none"/>',
    "pause": '<rect x="7.2" y="5.4" width="3.4" height="13.2" rx="1.5" fill="{c}" stroke="none"/>'
    '<rect x="13.4" y="5.4" width="3.4" height="13.2" rx="1.5" fill="{c}" stroke="none"/>',
    "next": '<path d="M6.6 6.1v11.8a.7.7 0 001.06.6l9-5.9a.7.7 0 000-1.2l-9-5.9a.7.7 0 00-1.06.6z" fill="{c}" stroke="none"/>'
    '<rect x="16.5" y="5.6" width="2.5" height="12.8" rx="1.25" fill="{c}" stroke="none"/>',
    "prev": '<path d="M17.4 6.1v11.8a.7.7 0 01-1.06.6l-9-5.9a.7.7 0 010-1.2l9-5.9a.7.7 0 011.06.6z" fill="{c}" stroke="none"/>'
    '<rect x="5" y="5.6" width="2.5" height="12.8" rx="1.25" fill="{c}" stroke="none"/>',
    "shuffle": '<path d="M3.6 7.2h2.7c1.3 0 2.5.62 3.24 1.66l4.92 7.08c.74 1.04 1.94 1.66 3.24 1.66h2.7"/>'
    '<path d="M17.5 3.9l3.3 3.3-3.3 3.3"/><path d="M17.5 13.9l3.3 3.3-3.3 3.3"/>'
    '<path d="M3.6 16.8h2.7c1.3 0 2.5-.62 3.24-1.66l.98-1.41"/>'
    '<path d="M13.5 9.6l.96-1.38c.74-1.04 1.94-1.66 3.24-1.66h1.7"/>',
    "repeat": '<path d="M7.3 5.4h8.3A4.4 4.4 0 0120 9.8v1"/><path d="M16.7 18.6H8.4A4.4 4.4 0 014 14.2v-1"/>'
    '<path d="M9.2 2.6L6.4 5.4l2.8 2.8"/><path d="M14.8 21.4l2.8-2.8-2.8-2.8"/>',
    "repeat_one": '<path d="M7.3 5.4h8.3A4.4 4.4 0 0120 9.8v1"/><path d="M16.7 18.6H8.4A4.4 4.4 0 014 14.2v-1"/>'
    '<path d="M9.2 2.6L6.4 5.4l2.8 2.8"/><path d="M14.8 21.4l2.8-2.8-2.8-2.8"/>'
    '<path d="M11.1 10.5l1.5-1v5.2" stroke-width="1.8"/>',
    "heart": '<path d="M12 20.1c-.3 0-.6-.1-.85-.33C7.05 16.1 3.6 13 3.6 9.4c0-2.7 2.1-4.8 4.7-4.8 1.5 0 2.9.7 3.7 1.9.8-1.2 2.2-1.9 3.7-1.9 2.6 0 4.7 2.1 4.7 4.8 0 3.6-3.45 6.7-7.55 10.37-.25.23-.55.33-.85.33z"/>',
    "heart_fill": '<path d="M12 20.1c-.3 0-.6-.1-.85-.33C7.05 16.1 3.6 13 3.6 9.4c0-2.7 2.1-4.8 4.7-4.8 1.5 0 2.9.7 3.7 1.9.8-1.2 2.2-1.9 3.7-1.9 2.6 0 4.7 2.1 4.7 4.8 0 3.6-3.45 6.7-7.55 10.37-.25.23-.55.33-.85.33z" fill="{c}"/>',
    "volume": '<path d="M4 9.6h2.9l4.2-3.6a.6.6 0 011 .46v11.08a.6.6 0 01-1 .46l-4.2-3.6H4a.8.8 0 01-.8-.8v-3.2a.8.8 0 01.8-.8z" fill="{c}" stroke="none"/>'
    '<path d="M15.3 9.2a4 4 0 010 5.6"/><path d="M17.9 6.5a7.7 7.7 0 010 11"/>',
    "volume_mute": '<path d="M4 9.6h2.9l4.2-3.6a.6.6 0 011 .46v11.08a.6.6 0 01-1 .46l-4.2-3.6H4a.8.8 0 01-.8-.8v-3.2a.8.8 0 01.8-.8z" fill="{c}" stroke="none"/>'
    '<path d="M15.4 9.6l5 4.8"/><path d="M20.4 9.6l-5 4.8"/>',
    "search": '<circle cx="10.7" cy="10.7" r="6.1"/><path d="M15.3 15.3l4.2 4.2"/>',
    "plus": '<path d="M12 5.2v13.6"/><path d="M5.2 12h13.6"/>',
    "minus": '<path d="M5.4 12h13.2"/>',
    "close": '<path d="M6.4 6.4l11.2 11.2"/><path d="M17.6 6.4L6.4 17.6"/>',
    "minimize": '<path d="M5.4 12h13.2"/>',
    "maximize": '<rect x="5.6" y="5.6" width="12.8" height="12.8" rx="2.2"/>',
    "restore": '<rect x="4.6" y="8.6" width="10.8" height="10.8" rx="2"/>'
    '<path d="M8.6 8.6V6.2a1.6 1.6 0 011.6-1.6h6.6A1.6 1.6 0 0119.4 6.2v6.6a1.6 1.6 0 01-1.6 1.6h-2.4"/>',
    "chevron_down": '<path d="M6.8 9.8l5.2 5.2 5.2-5.2"/>',
    "chevron_up": '<path d="M6.8 14.2l5.2-5.2 5.2 5.2"/>',
    "chevron_left": '<path d="M14.4 6.8L9.2 12l5.2 5.2"/>',
    "chevron_right": '<path d="M9.6 6.8L14.8 12l-5.2 5.2"/>',
    "arrow_left": '<path d="M11.4 5.4L4.8 12l6.6 6.6"/><path d="M4.8 12h15"/>',
    "arrow_right": '<path d="M12.6 5.4L19.2 12l-6.6 6.6"/><path d="M4.2 12h15"/>',
    "home": '<path d="M4.3 10.5L12 4.1l7.7 6.4"/><path d="M6.4 9.3v8.7a1.5 1.5 0 001.5 1.5h8.2a1.5 1.5 0 001.5-1.5V9.3"/>'
    '<path d="M10.1 19.5v-4.6h3.8v4.6"/>',
    "music_note": '<path d="M9.4 18.2V6.3l9.2-2.1v11.7"/><ellipse cx="7" cy="18.5" rx="2.4" ry="2.1"/>'
    '<ellipse cx="16.2" cy="16.4" rx="2.4" ry="2.1"/>',
    "disc": '<circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="2.5"/>',
    "mic": '<rect x="9.2" y="3.4" width="5.6" height="10.4" rx="2.8"/><path d="M5.8 11.3a6.2 6.2 0 0012.4 0"/>'
    '<path d="M12 17.5v3.1"/>',
    "list": '<path d="M4.5 7.2h15"/><path d="M4.5 12h10.4"/><path d="M4.5 16.8h12.4"/>',
    "queue": '<rect x="3.6" y="4.8" width="16.8" height="14.4" rx="2.6"/><path d="M8.4 8.8h8.4"/>'
    '<path d="M8.4 12.4h5.4"/><path d="M16.2 15.2v4.4"/><path d="M13.9 17.4h4.6"/>',
    "settings": '<path d="M12.22 2.6h-.44a1.9 1.9 0 00-1.9 1.9v.2a1.9 1.9 0 01-.95 1.65l-.4.24a1.9 1.9 0 01-1.9 0l-.15-.08a1.9 1.9 0 00-2.6.7l-.22.38a1.9 1.9 0 00.7 2.6l.14.09a1.9 1.9 0 01.95 1.64v.48a1.9 1.9 0 01-.95 1.65l-.14.09a1.9 1.9 0 00-.7 2.6l.22.38a1.9 1.9 0 002.6.7l.15-.08a1.9 1.9 0 011.9 0l.4.24a1.9 1.9 0 01.95 1.65v.2a1.9 1.9 0 001.9 1.9h.44a1.9 1.9 0 001.9-1.9v-.2a1.9 1.9 0 01.95-1.65l.4-.24a1.9 1.9 0 011.9 0l.15.08a1.9 1.9 0 002.6-.7l.22-.38a1.9 1.9 0 00-.7-2.6l-.14-.09a1.9 1.9 0 01-.95-1.65v-.48a1.9 1.9 0 01.95-1.65l.14-.09a1.9 1.9 0 00.7-2.6l-.22-.38a1.9 1.9 0 00-2.6-.7l-.15.08a1.9 1.9 0 01-1.9 0l-.4-.24a1.9 1.9 0 01-.95-1.65v-.2a1.9 1.9 0 00-1.9-1.9z"/>'
    '<circle cx="12" cy="12" r="3"/>',
    "lyrics": '<path d="M4.6 6.6h9.8"/><path d="M4.6 11h7.2"/><path d="M4.6 15.4h10.6"/><path d="M4.6 19.8h5.6"/>'
    '<path d="M17.4 8.2c1.5 0 2.6 1.1 2.6 2.6s-1.1 2.6-2.6 2.6" stroke-width="1.9"/>',
    "immersive": '<path d="M9.2 4.4H4.4v4.8"/><path d="M14.8 4.4h4.8v4.8"/><path d="M14.8 19.6h4.8v-4.8"/>'
    '<path d="M9.2 19.6H4.4v-4.8"/>',
    "monitor": '<rect x="3.4" y="4.8" width="17.2" height="11.6" rx="2.3"/><path d="M8.4 19.6h7.2"/>'
    '<path d="M12 16.4v3.2"/>',
    "trash": '<path d="M4.6 7.4h14.8"/><path d="M9.4 7.4V5.8a1.4 1.4 0 011.4-1.4h2.4a1.4 1.4 0 011.4 1.4v1.6"/>'
    '<path d="M6.6 7.4l.8 11.1a1.6 1.6 0 001.6 1.5h6a1.6 1.6 0 001.6-1.5l.8-11.1"/>',
    "download": '<path d="M12 4.4v10.8"/><path d="M7.6 11l4.4 4.4 4.4-4.4"/><path d="M4.8 18.6h14.4"/>',
    "check": '<path d="M5.4 12.6l4.2 4.2 9-9.8"/>',
    "more": '<circle cx="5.8" cy="12" r="1.55" fill="{c}" stroke="none"/><circle cx="12" cy="12" r="1.55" fill="{c}" stroke="none"/>'
    '<circle cx="18.2" cy="12" r="1.55" fill="{c}" stroke="none"/>',
    "grid": '<rect x="4.4" y="4.4" width="6.2" height="6.2" rx="1.7"/><rect x="13.4" y="4.4" width="6.2" height="6.2" rx="1.7"/>'
    '<rect x="4.4" y="13.4" width="6.2" height="6.2" rx="1.7"/><rect x="13.4" y="13.4" width="6.2" height="6.2" rx="1.7"/>',
    "rows": '<path d="M4.6 6.8h14.8"/><path d="M4.6 12h14.8"/><path d="M4.6 17.2h14.8"/>',
    "refresh": '<path d="M19.5 12a7.5 7.5 0 11-2.2-5.3"/><path d="M20 4.6v4.3h-4.3"/>',
    "folder": '<path d="M3.8 7.4a2 2 0 012-2h3.2l2.1 2.5h7.1a2 2 0 012 2v8.1a2 2 0 01-2 2H5.8a2 2 0 01-2-2z"/>',
    "cloud": '<path d="M7.2 18.2h9.7a4.1 4.1 0 00.4-8.2 6.1 6.1 0 00-11.7 1.7 3.7 3.7 0 001.6 6.5z"/>',
    "globe": '<circle cx="12" cy="12" r="8.4"/><path d="M3.8 12h16.4"/>'
    '<path d="M12 3.6c2.4 2.4 3.6 5.2 3.6 8.4s-1.2 6-3.6 8.4c-2.4-2.4-3.6-5.2-3.6-8.4s1.2-6 3.6-8.4z"/>',
    "translate": '<path d="M4.4 6.4h8"/><path d="M8.4 4.3v2.1"/><path d="M10.7 6.4c0 3.7-2.5 6.6-6.3 7.8"/>'
    '<path d="M6.1 10.1c.8 2.1 2.5 3.5 4.7 4.1"/><path d="M12.6 19.6l3.9-9.4 3.9 9.4"/><path d="M14 16.5h5"/>',
    "sun": '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.9v2.2"/><path d="M12 18.9v2.2"/><path d="M4.6 4.6l1.6 1.6"/>'
    '<path d="M17.8 17.8l1.6 1.6"/><path d="M2.9 12H5"/><path d="M19 12h2.1"/><path d="M4.6 19.4l1.6-1.6"/><path d="M17.8 6.2l1.6-1.6"/>',
    "moon": '<path d="M20.2 14.3A8.5 8.5 0 019.7 3.8a8.5 8.5 0 1010.5 10.5z"/>',
    "system": '<rect x="3.4" y="5.6" width="17.2" height="10.4" rx="2.1"/><path d="M2.6 19.2h18.8"/>',
    "sidebar": '<rect x="3.6" y="4.6" width="16.8" height="14.8" rx="2.6"/><path d="M9.3 4.6v14.8"/>',
    "sort": '<path d="M7.4 4.8v14.4"/><path d="M4 15.4l3.4 3.8 3.4-3.8"/><path d="M14.8 6.6h5.4"/>'
    '<path d="M14.8 11.6h3.8"/><path d="M14.8 16.6h2.2"/>',
    "sparkle": '<path d="M11.4 3.8l1.75 4.7 4.7 1.75-4.7 1.75-1.75 4.7-1.75-4.7L4.9 10.25l4.7-1.75z"/>'
    '<path d="M18.2 14.8l.85 2.15 2.15.85-2.15.85-.85 2.15-.85-2.15-2.15-.85 2.15-.85z"/>',
    "queue_add": '<path d="M4.4 6.8h9.2"/><path d="M4.4 11.6h9.2"/><path d="M4.4 16.4h6"/>'
    '<path d="M17.4 11.2v7"/><path d="M13.9 14.7h7"/>',
    "equalizer": '<path d="M6.2 19V9.6"/><path d="M6.2 6.2v-.4"/><path d="M12 19V5"/><path d="M17.8 19v-5.4"/>'
    '<circle cx="6.2" cy="8.2" r="1.8"/><circle cx="12" cy="12.6" r="1.8"/><circle cx="17.8" cy="12.2" r="1.8"/>',
    "info": '<circle cx="12" cy="12" r="8.4"/><path d="M12 11.2v5.4"/><circle cx="12" cy="8.1" r="1" fill="{c}" stroke="none"/>',
    "warning": '<path d="M12 4.4l8.3 14.5H3.7z"/><path d="M12 9.7v4.1"/><circle cx="12" cy="16.5" r="1" fill="{c}" stroke="none"/>',
    "external": '<path d="M14.4 4.8H19V9.4"/><path d="M18.9 5L11 12.9"/>'
    '<path d="M18.2 14.2v3.9a1.9 1.9 0 01-1.9 1.9H5.7a1.9 1.9 0 01-1.9-1.9V7.4a1.9 1.9 0 011.9-1.9h3.9"/>',
    "pin": '<path d="M9.2 3.8h5.6"/><path d="M12 3.8v5.9"/><path d="M8.4 9.7h7.2l1.3 4.6H7.1z"/><path d="M12 14.3v5.9"/>',
    "lock": '<rect x="5" y="10.4" width="14" height="9.2" rx="2.3"/><path d="M8.4 10.4V8a3.6 3.6 0 017.2 0v2.4"/>',
    "unlock": '<rect x="5" y="10.4" width="14" height="9.2" rx="2.3"/><path d="M8.4 10.4V8a3.6 3.6 0 016.9-1.6"/>',
    "clock": '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.2V12l3.2 2.1"/>',
    "star": '<path d="M12 4.3l2.3 4.9 5.4.7-3.95 3.75.96 5.35L12 16.45l-4.71 2.55.96-5.35L4.3 9.9l5.4-.7z"/>',
    "wifi_off": '<path d="M3.6 8.8a14 14 0 014.2-2.7"/><path d="M12 4.2c3.2 0 6.2 1.1 8.4 3"/><path d="M7 12.2a9.4 9.4 0 013.3-1.6"/>'
    '<path d="M12 8.2c2.2 0 4.2.7 5.8 2"/><circle cx="12" cy="18.4" r="1.15" fill="{c}" stroke="none"/>'
    '<path d="M4.2 4.2l15.6 15.6"/>',
    "drag": '<circle cx="9" cy="6" r="1.3" fill="{c}" stroke="none"/><circle cx="15" cy="6" r="1.3" fill="{c}" stroke="none"/>'
    '<circle cx="9" cy="12" r="1.3" fill="{c}" stroke="none"/><circle cx="15" cy="12" r="1.3" fill="{c}" stroke="none"/>'
    '<circle cx="9" cy="18" r="1.3" fill="{c}" stroke="none"/><circle cx="15" cy="18" r="1.3" fill="{c}" stroke="none"/>',
    "log": '<rect x="4.4" y="3.6" width="15.2" height="16.8" rx="2.4"/><path d="M8.4 8.2h7.2"/>'
    '<path d="M8.4 12h7.2"/><path d="M8.4 15.8h4.4"/>',
    "palette": '<path d="M12 3.6a8.4 8.4 0 000 16.8c1.3 0 1.9-.9 1.9-1.9 0-.6-.2-1.1-.5-1.5-.3-.4-.5-.9-.5-1.4 0-1 .9-1.9 1.9-1.9h1.5a4.1 4.1 0 004.1-4.1A8.4 8.4 0 0012 3.6z"/>'
    '<circle cx="8.2" cy="9.4" r="1.1" fill="{c}" stroke="none"/><circle cx="12" cy="7.4" r="1.1" fill="{c}" stroke="none"/>'
    '<circle cx="15.8" cy="9.4" r="1.1" fill="{c}" stroke="none"/>',
    "headphones": '<path d="M4.4 15.4v-3a7.6 7.6 0 0115.2 0v3"/><rect x="3.2" y="13.6" width="3.8" height="6.4" rx="1.9"/>'
    '<rect x="17" y="13.6" width="3.8" height="6.4" rx="1.9"/>',
    "clock_alt": '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.6V12l3 1.9"/>',
    "minus_circle": '<circle cx="12" cy="12" r="8.4"/><path d="M8.2 12h7.6"/>',
}


def _svg_markup(name: str, color: str) -> bytes:
    body = ICONS[name].replace("{c}", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        f'fill="none" stroke="{color}" stroke-width="{_STROKE}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    ).encode("utf-8")


_pixmap_cache: dict[tuple[str, str, int, int], QPixmap] = {}
_renderer_cache: dict[tuple[str, str], QSvgRenderer] = {}


def color_key(color) -> str:
    """Normalise a colour argument (str or QColor) to an SVG-friendly ``#rrggbb``.

    SVG has no notion of an alpha channel in a hex colour, and ``QSvgRenderer``
    silently refuses to paint an 8-digit ``#aarrggbb`` value.  We therefore keep
    the RGB part here and apply transparency separately through the painter, see
    :func:`color_alpha`.
    """
    if isinstance(color, QColor):
        return color.name(QColor.HexRgb)
    text = str(color)
    if text.startswith("#") and len(text) == 9:
        return "#" + text[3:]
    return text


def color_alpha(color) -> float:
    """Opacity carried by a colour argument (1.0 for plain strings)."""
    if isinstance(color, QColor):
        return max(0.0, min(1.0, color.alphaF()))
    return 1.0


def _renderer(name: str, color: str) -> QSvgRenderer:
    color = color_key(color)
    key = (name, color)
    cached = _renderer_cache.get(key)
    if cached is not None:
        return cached
    renderer = QSvgRenderer(QByteArray(_svg_markup(name, color)))
    _renderer_cache[key] = renderer
    return renderer


def pixmap(name: str, color, size: int, dpr: float = 2.0) -> QPixmap:
    size = max(8, int(size))
    color = color_key(color)
    dpr_key = max(1, int(round(dpr)))
    key = (name, color, size, dpr_key)
    cached = _pixmap_cache.get(key)
    if cached is not None:
        return cached
    target = size * dpr_key
    pm = QPixmap(target, target)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setOpacity(color_alpha(color))
    _renderer(name, color).render(painter, QRectF(0, 0, target, target))
    painter.end()
    pm.setDevicePixelRatio(dpr_key)
    _pixmap_cache[key] = pm
    return pm


def icon(name: str, color=None, size: int = 20) -> QIcon:
    from .theme import theme

    color = color or theme().palette.text
    result = QIcon()
    for scale in (1, 2):
        result.addPixmap(pixmap(name, color, size, float(scale)))
    return result


def draw(painter: QPainter, name: str, rect: QRectF, color, opacity: float = 1.0) -> None:
    """在已有 painter 上绘制图标（用于自绘控件）。"""
    if rect.width() <= 0 or rect.height() <= 0:
        return
    painter.save()
    painter.setOpacity(painter.opacity() * opacity * color_alpha(color))
    _renderer(name, color).render(painter, rect)
    painter.restore()


def clear_cache() -> None:
    _pixmap_cache.clear()
    _renderer_cache.clear()


def icon_names() -> list[str]:
    return sorted(ICONS)


def scaled_pixmap(name: str, color: str, size: int, dpr: float = 2.0) -> QPixmap:
    pm = pixmap(name, color, size, dpr).copy()
    pm.setDevicePixelRatio(1.0)
    return pm.scaled(
        QSize(int(size * dpr), int(size * dpr)),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def tinted(color: str) -> str:
    return qcolor(color).name()
