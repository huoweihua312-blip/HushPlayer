"""Small DPI-friendly QPainter icons for UI V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtSvg import QSvgRenderer

from app.ui_v2.theme.tokens import Theme


@dataclass(frozen=True, slots=True)
class IconSizing:
    """Logical-pixel guidance only; does not resize widgets or change hit tests."""
    visual_size: int
    hit_area: int


def icon_sizing(theme: Theme, role: str = "normal") -> IconSizing:
    m = theme.metrics
    return {
        "small": IconSizing(m.icon_sm, m.icon_hit_area),
        "normal": IconSizing(m.icon_md, m.icon_hit_area),
        "playback": IconSizing(m.icon_playback, m.icon_hit_area),
        "primary_playback": IconSizing(m.icon_primary_playback, m.primary_playback_hit_area),
    }[role]


IconName = Literal[
    "brand",
    "favorite",
    "favorite_filled",
    "playing",
    "local",
    "online",
    "missing",
    "search",
    "sort_ascending",
    "sort_descending",
    "library",
    "recent",
    "artist",
    "album",
    "playlist",
    "playlist_more",
    "add",
    "lyrics",
    "desktop_lyrics",
    "lock",
    "unlock",
    "settings",
    "settings_light",
    "sun",
    "moon",
    "shuffle",
    "previous",
    "play",
    "pause",
    "next",
    "repeat",
    "repeat_one",
    "queue",
    "volume",
    "volume_mute",
    "chevron_down",
    "chevron_up",
    "chevron_right",
    "back",
    "forward",
    "browse",
    "more",
    "notification",
    "user",
    "window_minimize",
    "window_maximize",
    "window_restore",
    "window_close",
    "fullscreen",
    "exit_fullscreen",
    "translate",
    "immersive_settings",
]
IconState = Literal["normal", "hover", "selected", "disabled", "inverse"]


@dataclass(frozen=True, slots=True)
class IconPalette:
    normal: QColor
    hover: QColor
    selected: QColor
    disabled: QColor
    inverse: QColor


def palette_for(theme: Theme) -> IconPalette:
    c = theme.colors
    return IconPalette(
        normal=QColor(c.icon_default),
        hover=QColor(c.icon_hover),
        selected=QColor(c.icon_active),
        disabled=QColor(c.disabled_text),
        inverse=QColor(c.app_background),
    )


_ICON_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
_FLUENT_PLAYER_ASSET_DIR = _ICON_ASSET_DIR / "fluent_player"
_FLUENT_SETTINGS_ASSET_DIR = _ICON_ASSET_DIR / "fluent_settings"
_FLUENT_IMMERSIVE_ASSET_DIR = _ICON_ASSET_DIR / "fluent_immersive"
_PHOSPHOR_ASSET_DIR = _ICON_ASSET_DIR / "phosphor"
FLUENT_PLAYER_ASSETS: dict[str, str] = {
    "favorite": "heart.svg", "favorite_filled": "favorite_filled.svg",
    "shuffle": "shuffle.svg", "previous": "skip-back.svg", "play": "play.svg",
    "pause": "pause.svg", "next": "skip-forward.svg", "repeat": "repeat.svg",
    "repeat_one": "repeat-once.svg", "queue": "queue.svg", "lyrics": "subtitles.svg",
    "desktop_lyrics": "monitor-play.svg", "volume": "speaker-high.svg",
    "volume_mute": "speaker-slash.svg", "more": "dots-three.svg",
}
FLUENT_SETTINGS_ASSETS: dict[str, str] = {
    "general": "settings_20_regular.svg",
    "appearance": "paint_brush_20_regular.svg",
    "playback": "play_circle_20_regular.svg",
    "lyrics": "subtitles_20_regular.svg",
    "library": "library_20_regular.svg",
    "online_sources": "cloud_20_regular.svg",
    "cache": "database_20_regular.svg",
    "updates": "arrow_sync_20_regular.svg",
    "about": "info_20_regular.svg",
    "dismiss": "dismiss_20_regular.svg",
}
FLUENT_IMMERSIVE_ASSETS: dict[str, str] = {
    "now_playing": "playlist.svg",
    "lyrics": "subtitles.svg",
    "return_current": "arrow-clockwise.svg",
    "fullscreen": "corners-out.svg",
    "exit_fullscreen": "corners-in.svg",
    "translate": "translate.svg",
    "immersive_settings": "sliders-horizontal.svg",
}
_SVG_ASSET_NAMES: dict[str, str] = {
    "brand": "brand",
    "library": "library",
    "browse": "browse",
    "favorite": "favorite",
    "favorite_filled": "favorite",
    "playlist_more": "more-playlists",
    "settings": "settings",
    "settings_light": "settings-light",
    "sun": "sun",
    "moon": "moon",
    "back": "back",
    "forward": "forward",
    "search": "search",
    "notification": "notification",
    "user": "profile",
    "shuffle": "shuffle",
    "previous": "previous",
    "play": "play",
    "pause": "pause",
    "next": "next",
    "repeat": "repeat-all",
    "repeat_one": "repeat-one",
    "queue": "queue",
    "lyrics": "lyrics",
    "volume": "volume",
    "volume_mute": "volume",
    "more": "more",
}
_SVG_SOURCE_CACHE: dict[str, bytes] = {}
_SVG_PIXMAP_CACHE: dict[tuple[str, int, int, float, float], QPixmap] = {}
_FLUENT_PLAYER_PIXMAP_CACHE: dict[tuple[str, int, int, float, float], QPixmap] = {}
_FLUENT_SETTINGS_PIXMAP_CACHE: dict[tuple[str, int, int, float], QPixmap] = {}
_FLUENT_IMMERSIVE_PIXMAP_CACHE: dict[tuple[str, int, int, float], QPixmap] = {}

# Approved paths retain their 24px viewBox and designed breathing room. These
# factors compensate only for differing optical weight inside that canvas.
ICON_OPTICAL_SCALE: dict[str, float] = {
    "brand": 1.08,
    "library": 1.10,
    "browse": 1.05,
    "favorite": 1.04,
    "favorite_filled": 1.04,
    "playlist_more": 1.08,
    "settings": 1.04,
    "settings_light": 1.04,
    "sun": 1.04,
    "moon": 1.04,
    "back": 1.05,
    "forward": 1.05,
    "search": 1.04,
    "notification": 1.04,
    "user": 1.04,
    "shuffle": 1.08,
    "previous": 1.04,
    "play": 1.03,
    "pause": 1.03,
    "next": 1.04,
    "repeat": 1.08,
    "repeat_one": 1.08,
    "queue": 1.08,
    "lyrics": 1.08,
    "volume": 1.05,
    "volume_mute": 1.05,
    "more": 1.03,
}

# Custom fallback glyphs share the same optical language as the vendored
# Fluent set: a restrained outline at normal sizes, with a small minimum so
# 14–16 logical-pixel navigation icons do not dissolve after rasterization.
# The upper bound is intentional; without it, the old width*0.1 rule made
# larger toolbar glyphs visibly heavier than the 1.7–1.9 SVG paths.
ICON_STROKE_MIN = 1.25
ICON_STROKE_MAX = 1.9
ICON_STROKE_RATIO = 0.095


def clear_svg_icon_cache() -> None:
    """Discard colored SVG pixmaps after a display DPR changes."""

    _SVG_PIXMAP_CACHE.clear()
    _FLUENT_PLAYER_PIXMAP_CACHE.clear()
    _FLUENT_SETTINGS_PIXMAP_CACHE.clear()
    _FLUENT_IMMERSIVE_PIXMAP_CACHE.clear()


def _device_pixel_ratio() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return round(float(screen.devicePixelRatio()) if screen is not None else 1.0, 3)


def optical_scale_for(name: str) -> float:
    """Return the centre-preserving visual scale for one approved glyph."""

    return round(float(ICON_OPTICAL_SCALE.get(name, 1.0)), 3)


def icon_stroke_width(rect: QRectF) -> float:
    """Return the shared outline width for a custom vector fallback."""

    logical_size = max(1.0, min(float(rect.width()), float(rect.height())))
    width = logical_size * ICON_STROKE_RATIO
    return round(max(ICON_STROKE_MIN, min(ICON_STROKE_MAX, width)), 3)


def _svg_source(name: str, color: QColor) -> bytes:
    asset_name = _SVG_ASSET_NAMES[name]
    source = _SVG_SOURCE_CACHE.get(asset_name)
    if source is None:
        source = (_ICON_ASSET_DIR / f"{asset_name}.svg").read_bytes()
        _SVG_SOURCE_CACHE[asset_name] = source
    if name == "favorite_filled":
        source = source.replace(b'fill="none"', b'fill="currentColor"', 1)
    return source.replace(b"currentColor", color.name().encode("ascii"))


def _svg_pixmap(
    name: str,
    size: int,
    color: QColor,
    dpr: float | None = None,
    optical_scale: float | None = None,
) -> QPixmap:
    """Render one approved SVG once per icon ID, size, color, and device scale."""

    if name not in _SVG_ASSET_NAMES:
        return QPixmap()
    dpr = _device_pixel_ratio() if dpr is None else round(float(dpr), 3)
    render_scale = optical_scale_for(name) if optical_scale is None else round(float(optical_scale), 3)
    key = (name, max(1, int(size)), color.rgba(), dpr, render_scale)
    cached = _SVG_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    physical_size = max(1, round(size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_svg_source(name, color)))
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        render_size = physical_size * render_scale
        inset = (physical_size - render_size) / 2
        renderer.render(painter, QRectF(inset, inset, render_size, render_size))
        painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _SVG_PIXMAP_CACHE[key] = pixmap
    return pixmap


def _fluent_player_source(filename: str, color: QColor) -> bytes:
    """Load one vendored Fluent path and apply its semantic color at runtime."""

    source = (_PHOSPHOR_ASSET_DIR / filename).read_bytes()
    # The package leaves the path fill implicit.  Keep the vendored SVGs
    # untouched and inject the current token only in the renderer input.
    return source.replace(
        b"<path ",
        b'<path fill="' + color.name().encode("ascii") + b'" ',
        1,
    )


def _fluent_settings_source(filename: str, color: QColor) -> bytes:
    """Load one vendored Settings glyph and apply the current theme color."""

    phosphor_name = {"general": "gear.svg", "dismiss": "x.svg"}.get(filename, filename)
    source_path = _PHOSPHOR_ASSET_DIR / phosphor_name
    if not source_path.exists():
        source_path = _FLUENT_SETTINGS_ASSET_DIR / filename
    source = source_path.read_bytes()
    return source.replace(
        b"<path ",
        b'<path fill="' + color.name().encode("ascii") + b'" ',
        1,
    )


def _fluent_immersive_source(filename: str, color: QColor) -> bytes:
    """Load one vendored Immersive glyph and apply the current theme color."""

    source_path = _PHOSPHOR_ASSET_DIR / filename
    if not source_path.exists():
        source_path = _FLUENT_IMMERSIVE_ASSET_DIR / filename
    source = source_path.read_bytes()
    return source.replace(
        b"<path ",
        b'<path fill="' + color.name().encode("ascii") + b'" ',
    )


def _fluent_settings_pixmap(
    name: str,
    size: int,
    color: QColor,
    dpr: float | None = None,
) -> QPixmap:
    """Render one Settings glyph into a centered, DPI-aware canvas."""

    filename = FLUENT_SETTINGS_ASSETS.get(name)
    if filename is None:
        return QPixmap()
    dpr = _device_pixel_ratio() if dpr is None else round(float(dpr), 3)
    key = (filename, max(1, int(size)), color.rgba(), dpr)
    cached = _FLUENT_SETTINGS_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    physical_size = max(1, round(size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_fluent_settings_source(filename, color)))
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, physical_size, physical_size))
        painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _FLUENT_SETTINGS_PIXMAP_CACHE[key] = pixmap
    return pixmap


def _fluent_player_pixmap(
    name: str,
    size: int,
    color: QColor,
    dpr: float | None = None,
) -> QPixmap:
    """Render one local Phosphor glyph into a centered, DPI-aware canvas.

    The public helper name is retained for compatibility with existing
    callers; the actual asset source is now the unified Phosphor set.
    """

    legacy_filename = FLUENT_PLAYER_ASSETS.get(name)
    if legacy_filename is None:
        return QPixmap()
    dpr = _device_pixel_ratio() if dpr is None else round(float(dpr), 3)
    filename = FLUENT_PLAYER_ASSETS[name]
    cache_asset = "monitor-subtitles-composite" if name == "desktop_lyrics" else filename
    key = (cache_asset, max(1, int(size)), color.rgba(), dpr, 0.0)
    cached = _FLUENT_PLAYER_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    physical_size = max(1, round(size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    source = (_desktop_lyrics_source() if name == "desktop_lyrics"
              else (_PHOSPHOR_ASSET_DIR / filename).read_bytes())
    source = source.replace(b"<path ", b'<path fill="' + color.name().encode("ascii") + b'" ', 1)
    source = source.replace(b"currentColor", color.name().encode("ascii"))
    renderer = QSvgRenderer(QByteArray(source))
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, physical_size, physical_size))
        painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _FLUENT_PLAYER_PIXMAP_CACHE[key] = pixmap
    return pixmap


def _transport_glyph_pixmap(
    name: str,
    size: int,
    color: QColor,
    dpr: float | None = None,
) -> QPixmap:
    """Render the primary transport glyph as a compact filled shape.

    The vendored Phosphor play/pause assets are outline constructions.  The
    primary transport controls intentionally use a filled glyph while keeping
    the same semantic key, canvas size, and icon cache contract.
    """

    if name not in {"play", "pause"}:
        return QPixmap()
    dpr = _device_pixel_ratio() if dpr is None else round(float(dpr), 3)
    logical_size = max(1, int(size))
    key = (FLUENT_PLAYER_ASSETS[name], logical_size, color.rgba(), dpr, 1.0)
    cached = _FLUENT_PLAYER_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached

    physical_size = max(1, round(logical_size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    if name == "play":
        triangle = QRectF(
            physical_size * 0.30,
            physical_size * 0.14,
            physical_size * 0.56,
            physical_size * 0.72,
        )
        # The triangle's optical centre sits slightly right of the canvas
        # centre, matching the familiar play symbol without an outline.
        points = QPolygonF(
            (
                triangle.topLeft(),
                QPointF(triangle.right(), triangle.center().y()),
                triangle.bottomLeft(),
            )
        )
        painter.drawPolygon(points)
    else:
        bar_width = physical_size * 0.20
        bar_height = physical_size * 0.72
        top = physical_size * 0.14
        painter.drawRect(QRectF(physical_size * 0.25, top, bar_width, bar_height))
        painter.drawRect(QRectF(physical_size * 0.55, top, bar_width, bar_height))
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _FLUENT_PLAYER_PIXMAP_CACHE[key] = pixmap
    return pixmap


def _desktop_lyrics_source() -> bytes:
    """Compose existing official subpaths; keep upstream files untouched.

    The monitor's last subpath is its play triangle. Subtitles' first
    subpath is its frame. Retain the monitor frame/stand and subtitle text,
    moving the latter upward inside the screen. No new glyph path is drawn.
    """
    def path_data(filename: str) -> str:
        root = ElementTree.fromstring((_PHOSPHOR_ASSET_DIR / filename).read_bytes())
        return root.find('{http://www.w3.org/2000/svg}path').attrib['d']
    monitor = path_data('monitor-play.svg')
    subtitles = path_data('subtitles.svg')
    assert 'Zm-3.56' in monitor and 'ZM48,136' in subtitles, 'Unexpected upstream artwork'
    frame = monitor.split('Zm-3.56', 1)[0] + 'Z'
    text = 'M48,136' + subtitles.split('ZM48,136', 1)[1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" fill="currentColor">'
            f'<path d="{frame}"/><g transform="translate(0,-24)"><path d="{text}"/></g></svg>').encode()


def _fluent_immersive_pixmap(
    name: str,
    size: int,
    color: QColor,
    dpr: float | None = None,
) -> QPixmap:
    """Render one Immersive glyph into a centered, DPI-aware canvas."""

    filename = FLUENT_IMMERSIVE_ASSETS.get(name)
    if filename is None:
        return QPixmap()
    dpr = _device_pixel_ratio() if dpr is None else round(float(dpr), 3)
    key = (filename, max(1, int(size)), color.rgba(), dpr)
    cached = _FLUENT_IMMERSIVE_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    physical_size = max(1, round(size * dpr))
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_fluent_immersive_source(filename, color)))
    if renderer.isValid():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, physical_size, physical_size))
        painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _FLUENT_IMMERSIVE_PIXMAP_CACHE[key] = pixmap
    return pixmap


def fluent_icon(
    name: str,
    theme: Theme,
    state: IconState = "normal",
    size: int = 18,
    *,
    solid: bool = False,
) -> QIcon:
    """Resolve a local player glyph, with optional filled primary transport."""

    if name not in FLUENT_PLAYER_ASSETS:
        return QIcon()
    palette = palette_for(theme)
    color = (
        QColor(theme.colors.danger)
        if name == "favorite_filled" and state == "selected"
        else getattr(palette, state)
    )
    if solid and name in {"play", "pause"}:
        # Primary playback glyphs stay white in every enabled state so the
        # filled mark remains the stable focal point on both themes.
        if state != "disabled":
            color = QColor("#ffffff")
        result = QIcon()
        result.addPixmap(_transport_glyph_pixmap(name, size, color))
        return result
    result = QIcon()
    result.addPixmap(_fluent_player_pixmap(name, size, color))
    return result


def fluent_settings_icon(
    name: str,
    theme: Theme,
    state: IconState = "normal",
    size: int = 18,
) -> QIcon:
    """Return a vendored Fluent glyph used only by the Settings overlay."""

    if name not in FLUENT_SETTINGS_ASSETS:
        return QIcon()
    palette = palette_for(theme)
    color = getattr(palette, state)
    result = QIcon()
    result.addPixmap(_fluent_settings_pixmap(name, size, color))
    return result


def fluent_immersive_icon(
    name: str,
    theme: Theme,
    state: IconState = "normal",
    size: int = 18,
) -> QIcon:
    """Return a vendored Fluent glyph used only by the Immersive Player shell."""

    if name not in FLUENT_IMMERSIVE_ASSETS:
        return QIcon()
    palette = palette_for(theme)
    color = getattr(palette, state)
    result = QIcon()
    result.addPixmap(_fluent_immersive_pixmap(name, size, color))
    return result


def fluent_immersive_interactive_icon(
    name: str,
    theme: Theme,
    size: int = 18,
) -> QIcon:
    """Return an Immersive glyph with neutral off/hover and checked colors."""

    if name not in FLUENT_IMMERSIVE_ASSETS:
        return QIcon()
    palette = palette_for(theme)
    result = QIcon()
    result.addPixmap(
        _fluent_immersive_pixmap(name, size, palette.normal),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    result.addPixmap(
        _fluent_immersive_pixmap(name, size, palette.hover),
        QIcon.Mode.Active,
        QIcon.State.Off,
    )
    result.addPixmap(
        _fluent_immersive_pixmap(name, size, palette.hover),
        QIcon.Mode.Normal,
        QIcon.State.On,
    )
    result.addPixmap(
        _fluent_immersive_pixmap(name, size, palette.hover),
        QIcon.Mode.Active,
        QIcon.State.On,
    )
    result.addPixmap(
        _fluent_immersive_pixmap(name, size, palette.disabled),
        QIcon.Mode.Disabled,
        QIcon.State.Off,
    )
    return result


def fluent_settings_interactive_icon(
    name: str,
    theme: Theme,
    size: int = 18,
) -> QIcon:
    """Return a Settings glyph with neutral normal/hover/disabled states."""

    if name not in FLUENT_SETTINGS_ASSETS:
        return QIcon()
    palette = palette_for(theme)
    result = QIcon()
    result.addPixmap(
        _fluent_settings_pixmap(name, size, palette.normal),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    result.addPixmap(
        _fluent_settings_pixmap(name, size, palette.hover),
        QIcon.Mode.Active,
        QIcon.State.Off,
    )
    result.addPixmap(
        _fluent_settings_pixmap(name, size, palette.disabled),
        QIcon.Mode.Disabled,
        QIcon.State.Off,
    )
    return result


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
    pen = QPen(color, icon_stroke_width(rect))
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
    elif name in ("back", "forward"):
        left = name == "back"
        start = rect.left() + rect.width() * (0.64 if left else 0.36)
        end = rect.left() + rect.width() * (0.36 if left else 0.64)
        painter.drawLine(start, rect.top() + rect.height() * 0.22, end, rect.center().y())
        painter.drawLine(end, rect.center().y(), start, rect.bottom() - rect.height() * 0.22)
    elif name == "browse":
        side = rect.width() * 0.28
        radius = max(1.0, rect.width() * 0.05)
        for x_ratio in (0.13, 0.59):
            for y_ratio in (0.13, 0.59):
                painter.drawRoundedRect(
                    QRectF(rect.left() + rect.width() * x_ratio, rect.top() + rect.height() * y_ratio, side, side),
                    radius,
                    radius,
                )
    elif name == "library":
        # Paired book spines read as a library at small navigation sizes;
        # unlike a menu glyph, the silhouette remains distinct from playlist.
        left_book = QRectF(
            rect.left() + rect.width() * 0.12,
            rect.top() + rect.height() * 0.18,
            rect.width() * 0.32,
            rect.height() * 0.64,
        )
        right_book = QRectF(
            rect.left() + rect.width() * 0.5,
            rect.top() + rect.height() * 0.13,
            rect.width() * 0.3,
            rect.height() * 0.69,
        )
        painter.drawRoundedRect(left_book, rect.width() * 0.04, rect.width() * 0.04)
        painter.drawRoundedRect(right_book, rect.width() * 0.04, rect.width() * 0.04)
        painter.drawLine(
            right_book.left() + right_book.width() * 0.27,
            right_book.top() + right_book.height() * 0.12,
            right_book.left() + right_book.width() * 0.27,
            right_book.bottom() - right_book.height() * 0.12,
        )
    elif name == "recent":
        painter.drawEllipse(rect.adjusted(rect.width() * 0.13, rect.height() * 0.13, -rect.width() * 0.13, -rect.height() * 0.13))
        painter.drawLine(rect.center().x(), rect.center().y(), rect.center().x(), rect.top() + rect.height() * 0.3)
        painter.drawLine(rect.center().x(), rect.center().y(), rect.left() + rect.width() * 0.66, rect.center().y())
    elif name == "artist":
        painter.drawEllipse(QRectF(rect.left() + rect.width() * 0.35, rect.top() + rect.height() * 0.1, rect.width() * 0.3, rect.height() * 0.3))
        painter.drawArc(QRectF(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.39, rect.width() * 0.64, rect.height() * 0.48), 20 * 16, 140 * 16)
    elif name == "album":
        painter.drawEllipse(rect.adjusted(rect.width() * 0.1, rect.height() * 0.1, -rect.width() * 0.1, -rect.height() * 0.1))
        painter.drawEllipse(rect.adjusted(rect.width() * 0.41, rect.height() * 0.41, -rect.width() * 0.41, -rect.height() * 0.41))
    elif name in ("playlist", "playlist_more"):
        # A playlist has both rows and a musical note, avoiding a generic
        # three-line menu silhouette.  "更多歌单" adds an unambiguous chevron.
        for row, width in enumerate((0.42, 0.34)):
            y = rect.top() + rect.height() * (0.28 + row * 0.2)
            painter.drawLine(
                rect.left() + rect.width() * 0.1,
                y,
                rect.left() + rect.width() * (0.1 + width),
                y,
            )
        note_x = rect.left() + rect.width() * 0.68
        note_top = rect.top() + rect.height() * 0.18
        note_bottom = rect.top() + rect.height() * 0.7
        painter.drawLine(note_x, note_top, note_x, note_bottom)
        painter.drawLine(note_x, note_top, rect.left() + rect.width() * 0.88, rect.top() + rect.height() * 0.25)
        painter.drawEllipse(
            QRectF(
                rect.left() + rect.width() * 0.53,
                rect.top() + rect.height() * 0.62,
                rect.width() * 0.2,
                rect.height() * 0.18,
            )
        )
        if name == "playlist_more":
            painter.drawLine(
                rect.left() + rect.width() * 0.14,
                rect.top() + rect.height() * 0.73,
                rect.left() + rect.width() * 0.28,
                rect.top() + rect.height() * 0.87,
            )
            painter.drawLine(
                rect.left() + rect.width() * 0.28,
                rect.top() + rect.height() * 0.87,
                rect.left() + rect.width() * 0.42,
                rect.top() + rect.height() * 0.73,
            )
    elif name == "add":
        painter.drawLine(rect.left() + rect.width() * 0.5, rect.top() + rect.height() * 0.18, rect.left() + rect.width() * 0.5, rect.top() + rect.height() * 0.82)
        painter.drawLine(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.5, rect.left() + rect.width() * 0.82, rect.top() + rect.height() * 0.5)
    elif name == "lyrics":
        # Open text lines are deliberately distinct from both a document and
        # the queue list at 16–20px.
        for row, (start, width) in enumerate(((0.18, 0.64), (0.18, 0.46), (0.18, 0.58), (0.18, 0.34))):
            y = rect.top() + rect.height() * (0.24 + row * 0.18)
            painter.drawLine(rect.left() + rect.width() * start, y, rect.left() + rect.width() * (start + width), y)
    elif name == "desktop_lyrics":
        # Monitor frame plus two lyric rules, unlike the in-app text glyph.
        monitor = rect.adjusted(rect.width() * 0.1, rect.height() * 0.1, -rect.width() * 0.1, -rect.height() * 0.28)
        painter.drawRoundedRect(monitor, rect.width() * 0.06, rect.width() * 0.06)
        painter.drawLine(rect.center().x(), monitor.bottom(), rect.center().x(), rect.bottom() - rect.height() * 0.13)
        painter.drawLine(rect.left() + rect.width() * 0.3, rect.bottom() - rect.height() * 0.13, rect.right() - rect.width() * 0.3, rect.bottom() - rect.height() * 0.13)
        painter.drawLine(rect.left() + rect.width() * 0.27, monitor.top() + rect.height() * 0.28, rect.right() - rect.width() * 0.27, monitor.top() + rect.height() * 0.28)
    elif name in ("lock", "unlock"):
        body = QRectF(
            rect.left() + rect.width() * 0.18,
            rect.top() + rect.height() * 0.44,
            rect.width() * 0.64,
            rect.height() * 0.43,
        )
        painter.drawRoundedRect(body, rect.width() * 0.08, rect.width() * 0.08)
        shackle = QPainterPath()
        if name == "lock":
            shackle.moveTo(body.left() + body.width() * 0.2, body.top())
            shackle.lineTo(body.left() + body.width() * 0.2, rect.top() + rect.height() * 0.3)
            shackle.cubicTo(
                body.left() + body.width() * 0.2,
                rect.top() + rect.height() * 0.08,
                body.right() - body.width() * 0.2,
                rect.top() + rect.height() * 0.08,
                body.right() - body.width() * 0.2,
                rect.top() + rect.height() * 0.3,
            )
            shackle.lineTo(body.right() - body.width() * 0.2, body.top())
        else:
            shackle.moveTo(body.right() - body.width() * 0.2, body.top())
            shackle.lineTo(body.right() - body.width() * 0.2, rect.top() + rect.height() * 0.29)
            shackle.cubicTo(
                body.right() - body.width() * 0.2,
                rect.top() + rect.height() * 0.08,
                body.left() + body.width() * 0.2,
                rect.top() + rect.height() * 0.08,
                body.left() + body.width() * 0.2,
                rect.top() + rect.height() * 0.3,
            )
        painter.drawPath(shackle)
        painter.drawPoint(rect.center().x(), body.center().y())
    elif name == "settings":
        # Short, squared teeth and a double ring give this a true gear form
        # instead of the sunburst produced by free-standing radial strokes.
        tooth_width = rect.width() * 0.13
        tooth_height = rect.height() * 0.22
        for angle in range(0, 360, 45):
            painter.save()
            painter.translate(rect.center())
            painter.rotate(angle)
            painter.drawRoundedRect(
                QRectF(-tooth_width / 2, -rect.height() * 0.48, tooth_width, tooth_height),
                tooth_width * 0.18,
                tooth_width * 0.18,
            )
            painter.restore()
        painter.drawEllipse(
            rect.adjusted(
                rect.width() * 0.22,
                rect.height() * 0.22,
                -rect.width() * 0.22,
                -rect.height() * 0.22,
            )
        )
        painter.drawEllipse(
            rect.adjusted(
                rect.width() * 0.42,
                rect.height() * 0.42,
                -rect.width() * 0.42,
                -rect.height() * 0.42,
            )
        )
    elif name == "notification":
        bell = QRectF(
            rect.left() + rect.width() * 0.22,
            rect.top() + rect.height() * 0.16,
            rect.width() * 0.56,
            rect.height() * 0.62,
        )
        painter.drawArc(bell, 22 * 16, 136 * 16)
        painter.drawLine(bell.left(), bell.center().y(), bell.left(), bell.bottom())
        painter.drawLine(bell.right(), bell.center().y(), bell.right(), bell.bottom())
        painter.drawLine(rect.left() + rect.width() * 0.16, bell.bottom(), rect.right() - rect.width() * 0.16, bell.bottom())
        painter.drawPoint(rect.center().x(), rect.bottom() - rect.height() * 0.08)
    elif name == "user":
        painter.drawEllipse(QRectF(rect.left() + rect.width() * 0.36, rect.top() + rect.height() * 0.14, rect.width() * 0.28, rect.height() * 0.28))
        painter.drawArc(QRectF(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.42, rect.width() * 0.64, rect.height() * 0.48), 22 * 16, 136 * 16)
    elif name == "more":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = max(1.0, rect.width() * 0.095)
        for ratio in (0.25, 0.5, 0.75):
            painter.drawEllipse(QRectF(rect.left() + rect.width() * ratio - radius, rect.center().y() - radius, radius * 2, radius * 2))
    elif name == "window_minimize":
        painter.drawLine(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.7, rect.right() - rect.width() * 0.22, rect.top() + rect.height() * 0.7)
    elif name == "window_maximize":
        painter.drawRect(rect.adjusted(rect.width() * 0.22, rect.height() * 0.22, -rect.width() * 0.22, -rect.height() * 0.22))
    elif name == "window_restore":
        rear = rect.adjusted(rect.width() * 0.17, rect.height() * 0.17, -rect.width() * 0.35, -rect.height() * 0.35)
        front = rect.adjusted(rect.width() * 0.35, rect.height() * 0.35, -rect.width() * 0.17, -rect.height() * 0.17)
        painter.drawRect(rear)
        painter.drawRect(front)
    elif name == "window_close":
        painter.drawLine(rect.left() + rect.width() * 0.25, rect.top() + rect.height() * 0.25, rect.right() - rect.width() * 0.25, rect.bottom() - rect.height() * 0.25)
        painter.drawLine(rect.right() - rect.width() * 0.25, rect.top() + rect.height() * 0.25, rect.left() + rect.width() * 0.25, rect.bottom() - rect.height() * 0.25)
    elif name in ("fullscreen", "exit_fullscreen"):
        inset = rect.width() * 0.2
        if name == "fullscreen":
            for x1, y1, x2, y2 in ((inset, inset, inset * 2.1, inset), (rect.right() - inset, inset, rect.right() - inset * 2.1, inset), (inset, rect.bottom() - inset, inset * 2.1, rect.bottom() - inset), (rect.right() - inset, rect.bottom() - inset, rect.right() - inset * 2.1, rect.bottom() - inset)):
                painter.drawLine(x1, y1, x2, y2)
        else:
            painter.drawRect(rect.adjusted(rect.width() * .22, rect.height() * .22, -rect.width() * .22, -rect.height() * .22))
            painter.drawLine(rect.left() + rect.width() * .1, rect.top() + rect.height() * .1, rect.left() + rect.width() * .3, rect.top() + rect.height() * .1)
            painter.drawLine(rect.left() + rect.width() * .1, rect.top() + rect.height() * .1, rect.left() + rect.width() * .1, rect.top() + rect.height() * .3)
    elif name == "translate":
        painter.drawRect(rect.adjusted(rect.width() * .12, rect.height() * .16, -rect.width() * .12, -rect.height() * .16))
        painter.drawLine(rect.left() + rect.width() * .24, rect.top() + rect.height() * .36, rect.left() + rect.width() * .58, rect.top() + rect.height() * .36)
        painter.drawLine(rect.left() + rect.width() * .4, rect.top() + rect.height() * .28, rect.left() + rect.width() * .4, rect.top() + rect.height() * .62)
        painter.drawLine(rect.left() + rect.width() * .67, rect.top() + rect.height() * .44, rect.left() + rect.width() * .88, rect.top() + rect.height() * .78)
    elif name == "shuffle":
        # Two input paths cross and terminate in their own arrow heads.  This
        # deliberately avoids the single-turn arrow silhouette of a jump icon.
        left = rect.left() + rect.width() * 0.1
        join = rect.left() + rect.width() * 0.4
        right = rect.left() + rect.width() * 0.84
        top = rect.top() + rect.height() * 0.27
        bottom = rect.top() + rect.height() * 0.73
        painter.drawLine(left, top, join, top)
        painter.drawLine(join, top, right, bottom)
        painter.drawLine(right, bottom, right - rect.width() * 0.15, bottom - rect.height() * 0.16)
        painter.drawLine(right, bottom, right - rect.width() * 0.15, bottom + rect.height() * 0.16)
        painter.drawLine(left, bottom, join, bottom)
        painter.drawLine(join, bottom, right, top)
        painter.drawLine(right, top, right - rect.width() * 0.15, top - rect.height() * 0.16)
        painter.drawLine(right, top, right - rect.width() * 0.15, top + rect.height() * 0.16)
    elif name in ("previous", "next", "play"):
        path = QPainterPath()
        if name == "play":
            path.moveTo(rect.left() + rect.width() * 0.32, rect.top() + rect.height() * 0.18)
            path.lineTo(rect.left() + rect.width() * 0.78, rect.center().y())
            path.lineTo(rect.left() + rect.width() * 0.32, rect.top() + rect.height() * 0.82)
        elif name == "previous":
            path.moveTo(rect.left() + rect.width() * 0.68, rect.top() + rect.height() * 0.18)
            path.lineTo(rect.left() + rect.width() * 0.26, rect.center().y())
            path.lineTo(rect.left() + rect.width() * 0.68, rect.top() + rect.height() * 0.82)
            painter.drawLine(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.2, rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.8)
        else:
            path.moveTo(rect.left() + rect.width() * 0.32, rect.top() + rect.height() * 0.18)
            path.lineTo(rect.left() + rect.width() * 0.74, rect.center().y())
            path.lineTo(rect.left() + rect.width() * 0.32, rect.top() + rect.height() * 0.82)
            painter.drawLine(rect.left() + rect.width() * 0.82, rect.top() + rect.height() * 0.2, rect.left() + rect.width() * 0.82, rect.top() + rect.height() * 0.8)
        painter.setBrush(color)
        painter.drawPath(path)
    elif name == "pause":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(rect.left() + rect.width() * 0.25, rect.top() + rect.height() * 0.18, rect.width() * 0.17, rect.height() * 0.64), 2, 2)
        painter.drawRoundedRect(QRectF(rect.left() + rect.width() * 0.58, rect.top() + rect.height() * 0.18, rect.width() * 0.17, rect.height() * 0.64), 2, 2)
    elif name in ("repeat", "repeat_one"):
        # The canonical list-repeat mark is two connected horizontal arrows,
        # not a letter-like circular arc.
        left = rect.left() + rect.width() * 0.12
        right = rect.left() + rect.width() * 0.88
        top = rect.top() + rect.height() * 0.31
        bottom = rect.top() + rect.height() * 0.69
        painter.drawLine(left, top, right - rect.width() * 0.14, top)
        painter.drawLine(right - rect.width() * 0.14, top, right, rect.center().y())
        painter.drawLine(right, rect.center().y(), right - rect.width() * 0.14, bottom)
        painter.drawLine(right, bottom, left + rect.width() * 0.14, bottom)
        painter.drawLine(left + rect.width() * 0.14, bottom, left, rect.center().y())
        painter.drawLine(left, rect.center().y(), left + rect.width() * 0.14, top)
        if name == "repeat_one":
            one_pen = QPen(color, max(1.05, rect.width() * 0.072))
            one_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(one_pen)
            one_x = rect.center().x()
            painter.drawLine(one_x, rect.top() + rect.height() * 0.39, one_x, rect.top() + rect.height() * 0.61)
            painter.drawLine(one_x, rect.top() + rect.height() * 0.39, one_x - rect.width() * 0.06, rect.top() + rect.height() * 0.45)
    elif name == "queue":
        for row, width in enumerate((0.68, 0.52, 0.60)):
            y = rect.top() + rect.height() * (0.22 + row * 0.25)
            painter.drawLine(rect.left() + rect.width() * 0.12, y, rect.left() + rect.width() * (0.12 + width), y)
        cue = QPainterPath()
        cue.moveTo(rect.left() + rect.width() * 0.67, rect.bottom() - rect.height() * 0.25)
        cue.lineTo(rect.left() + rect.width() * 0.87, rect.bottom() - rect.height() * 0.13)
        cue.lineTo(rect.left() + rect.width() * 0.67, rect.bottom() - rect.height() * 0.01)
        painter.drawPath(cue)
    elif name in ("volume", "volume_mute"):
        speaker = QPainterPath()
        speaker.moveTo(rect.left() + rect.width() * 0.14, rect.top() + rect.height() * 0.42)
        speaker.lineTo(rect.left() + rect.width() * 0.35, rect.top() + rect.height() * 0.42)
        speaker.lineTo(rect.left() + rect.width() * 0.58, rect.top() + rect.height() * 0.22)
        speaker.lineTo(rect.left() + rect.width() * 0.58, rect.top() + rect.height() * 0.78)
        speaker.lineTo(rect.left() + rect.width() * 0.35, rect.top() + rect.height() * 0.58)
        speaker.lineTo(rect.left() + rect.width() * 0.14, rect.top() + rect.height() * 0.58)
        speaker.closeSubpath()
        painter.drawPath(speaker)
        if name == "volume_mute":
            painter.drawLine(rect.left() + rect.width() * 0.68, rect.top() + rect.height() * 0.34, rect.left() + rect.width() * 0.88, rect.top() + rect.height() * 0.66)
            painter.drawLine(rect.left() + rect.width() * 0.88, rect.top() + rect.height() * 0.34, rect.left() + rect.width() * 0.68, rect.top() + rect.height() * 0.66)
        else:
            painter.drawArc(QRectF(rect.left() + rect.width() * 0.5, rect.top() + rect.height() * 0.28, rect.width() * 0.36, rect.height() * 0.44), -55 * 16, 110 * 16)
    elif name in ("sort_ascending", "sort_descending"):
        descending = name == "sort_descending"
        for row, x_ratio in enumerate((0.17, 0.17, 0.17)):
            y = rect.top() + rect.height() * (0.25 + row * 0.25)
            painter.drawLine(rect.left() + rect.width() * x_ratio, y, rect.left() + rect.width() * (0.72 - row * 0.12), y)
        direction = 0.68 if descending else 0.32
        opposite = 0.32 if descending else 0.68
        painter.drawLine(rect.left() + rect.width() * 0.82, rect.top() + rect.height() * direction, rect.left() + rect.width() * 0.82, rect.top() + rect.height() * opposite)
        painter.drawLine(rect.left() + rect.width() * 0.7, rect.top() + rect.height() * (direction - 0.12 if descending else direction + 0.12), rect.left() + rect.width() * 0.82, rect.top() + rect.height() * direction)
        painter.drawLine(rect.left() + rect.width() * 0.94, rect.top() + rect.height() * (direction - 0.12 if descending else direction + 0.12), rect.left() + rect.width() * 0.82, rect.top() + rect.height() * direction)
    elif name in ("chevron_down", "chevron_up", "chevron_right"):
        path = QPainterPath()
        if name == "chevron_down":
            path.moveTo(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.36)
            path.lineTo(rect.center().x(), rect.top() + rect.height() * 0.64)
            path.lineTo(rect.right() - rect.width() * 0.22, rect.top() + rect.height() * 0.36)
        elif name == "chevron_up":
            path.moveTo(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.64)
            path.lineTo(rect.center().x(), rect.top() + rect.height() * 0.36)
            path.lineTo(rect.right() - rect.width() * 0.22, rect.top() + rect.height() * 0.64)
        else:
            path.moveTo(rect.left() + rect.width() * 0.36, rect.top() + rect.height() * 0.22)
            path.lineTo(rect.left() + rect.width() * 0.64, rect.center().y())
            path.lineTo(rect.left() + rect.width() * 0.36, rect.bottom() - rect.height() * 0.22)
        painter.drawPath(path)
    painter.restore()


def paint_icon(painter: QPainter, name: IconName, rect: QRectF, theme: Theme, state: IconState = "normal") -> None:
    """Paint an icon directly, selecting the color from its semantic state."""
    colors = palette_for(theme)
    color = getattr(colors, state)
    if name in ("translate", "fullscreen", "exit_fullscreen"):
        pixmap = _fluent_immersive_pixmap(name, max(1, round(max(rect.width(), rect.height()))), color)
        painter.drawPixmap(rect.toRect(), pixmap)
        return
    if name in FLUENT_PLAYER_ASSETS:
        size = max(1, round(max(rect.width(), rect.height())))
        pixmap = _fluent_player_pixmap(name, size, color)
        if not pixmap.isNull():
            painter.drawPixmap(rect.toRect(), pixmap)
            return
    if name in _SVG_ASSET_NAMES:
        size = max(1, round(max(rect.width(), rect.height())))
        pixmap = _svg_pixmap(name, size, color)
        if not pixmap.isNull():
            painter.drawPixmap(rect.toRect(), pixmap)
            return
    _paint_shape(painter, name, rect, color)


def icon(name: IconName, theme: Theme, state: IconState = "normal") -> QIcon:
    """Build a multi-size QIcon so toolbar controls remain crisp on high DPI."""
    result = QIcon()
    if name in ("translate", "fullscreen", "exit_fullscreen"):
        color = getattr(palette_for(theme), state)
        for size in (16, 18, 20, 24, 32, 48):
            result.addPixmap(_fluent_immersive_pixmap(name, size, color))
        return result
    if name in FLUENT_PLAYER_ASSETS:
        color = getattr(palette_for(theme), state)
        for size in (16, 18, 20, 24):
            result.addPixmap(_fluent_player_pixmap(name, size, color))
        return result
    if name in _SVG_ASSET_NAMES:
        color = getattr(palette_for(theme), state)
        for size in (15, 16, 17, 18, 19, 20, 24, 32, 48):
            result.addPixmap(_svg_pixmap(name, size, color))
        return result
    for size in (15, 16, 17, 18, 19, 20, 24, 32, 48):
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
