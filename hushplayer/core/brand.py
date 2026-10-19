"""Brand assets (BUG-07).

The product logo is user-owned artwork: until the official files land we must
not invent new marks, so every surface competes for one resolution order:

1. ``assets/brand/<name>`` -- the official, user-supplied files;
2. the generated placeholder that ships with the repository.

Drop the official files in and every surface (window icon, tray, sidebar mark,
about page, installer) picks them up on the next start, no code change needed.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .paths import resource_path

#: Official asset filenames, documented in assets/brand/README.md.
LOGO = "logo.png"
LOGO_LIGHT = "logo_light.png"
LOGO_DARK = "logo_dark.png"
LOGO_LIGHT_SVG = "logo_light.svg"
LOGO_DARK_SVG = "logo_dark.svg"
ICON = "icon.ico"
ICON_PNG = "icon.png"

_PLACEHOLDER_PNG = ("assets", "hushplayer.png")
_PLACEHOLDER_ICO = ("assets", "hushplayer.ico")


def brand_dir() -> Path:
    return resource_path("assets", "brand")


def _existing(*candidates: tuple[str, ...]) -> Path | None:
    for relative in candidates:
        path = resource_path(*relative)
        if path.is_file():
            return path
    return None


def _brand_file(name: str) -> Path | None:
    path = brand_dir() / name
    return path if path.is_file() else None


def has_official_logo() -> bool:
    """True when the user has supplied the real logo files."""
    return any(_brand_file(name) is not None for name in (LOGO, LOGO_LIGHT, LOGO_DARK, ICON, ICON_PNG))


def logo_path(mode: str = "dark") -> Path | None:
    """Path of the logo artwork appropriate for ``mode`` (``light``/``dark``).

    The original HushPlayer ships a vector mark (two colour variants) for the
    in-app surfaces and a multi-size ``.ico`` for the application icon; keep
    that split so the sidebar mark matches the old build exactly.
    """
    if mode == "light":
        order = (LOGO_LIGHT_SVG, LOGO_LIGHT, LOGO_DARK_SVG, LOGO)
    else:
        order = (LOGO_DARK_SVG, LOGO_DARK, LOGO_LIGHT_SVG, LOGO)
    for name in order:
        found = _brand_file(name)
        if found is not None:
            return found
    return _existing(_PLACEHOLDER_PNG)


def _render_logo(path: Path, target: int) -> QPixmap | None:
    """Render a logo file (svg or raster) into a transparent square pixmap."""
    if path.suffix.lower() == ".svg":
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return None
        pixmap = QPixmap(target, target)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = renderer.defaultSize()
        scale = min(target / max(1, size.width()), target / max(1, size.height()))
        width = size.width() * scale
        height = size.height() * scale
        rect = QRectF((target - width) / 2, (target - height) / 2, width, height)
        renderer.render(painter, rect)
        painter.end()
        return pixmap
    pixmap = QPixmap(str(path))
    return None if pixmap.isNull() else pixmap


def icon_path() -> Path | None:
    for name in (ICON, "HushPlayer.ico", ICON_PNG):
        found = _brand_file(name)
        if found is not None:
            return found
    return _existing(_PLACEHOLDER_ICO)


def logo_pixmap(size: int, mode: str = "dark", *, dpr: float = 2.0) -> QPixmap | None:
    path = logo_path(mode)
    if path is None:
        return None
    target = max(8, int(size * dpr))
    rendered = _render_logo(path, target)
    if rendered is None:
        return None
    scaled = rendered.scaled(
        QSize(target, target),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled


def logo_pixmap_cropped(size: int, mode: str = "dark", *, dpr: float = 2.0) -> QPixmap | None:
    """Logo scaled to fill a square (keeps transparent padding out of the mark)."""
    path = logo_path(mode)
    if path is None:
        return None
    target = max(8, int(size * dpr))
    pixmap = _render_logo(path, target)
    if pixmap is None:
        return None
    scaled = pixmap.scaled(
        QSize(target, target),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    cropped = scaled.copy(
        (scaled.width() - target) // 2,
        (scaled.height() - target) // 2,
        target,
        target,
    )
    cropped.setDevicePixelRatio(dpr)
    return cropped


def app_icon() -> QIcon:
    """Multi-size application icon (window, taskbar, tray, installer)."""
    icon = QIcon()
    ico = icon_path()
    if ico is not None:
        icon.addFile(str(ico))
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = logo_pixmap(size, "dark", dpr=1.0)
        if pixmap is not None:
            icon.addPixmap(pixmap)
    if icon.isNull():
        from . import icons

        for size in (16, 32, 64):
            icon.addPixmap(icons.pixmap("headphones", "#C95770", size, 1.0))
    return icon


def rounded_logo_pixmap(size: int, mode: str = "dark", *, radius: float = 0.30) -> QPixmap | None:
    """Logo clipped to a rounded square, for the sidebar and about card."""
    source = logo_pixmap_cropped(size, mode)
    if source is None:
        return None
    dpr = source.devicePixelRatio() or 1.0
    physical = int(round(size * dpr))
    out = QPixmap(physical, physical)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.addRoundedRect(
        0.0, 0.0, float(physical), float(physical), physical * radius, physical * radius
    )
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return out


__all__ = [
    "app_icon",
    "brand_dir",
    "has_official_logo",
    "icon_path",
    "logo_path",
    "logo_pixmap",
    "logo_pixmap_cropped",
    "rounded_logo_pixmap",
]


def tray_icon() -> QIcon:
    """Tray icon: the brand mark on a dark rounded tile, crisp down to 16 px."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pixmap = _tray_pixmap(size)
        if pixmap is not None:
            icon.addPixmap(pixmap)
    if icon.isNull():
        icon = app_icon()
    return icon


def _tray_pixmap(size: int) -> QPixmap | None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QPainter, QPainterPath

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    painter.fillPath(tile, QColor("#1C1B1D"))

    bright = QColor("#D9738A")
    deep = QColor("#A83E58")
    # Fewer, wider bars at small sizes keep the mark legible in the 16 px tray.
    if size >= 24:
        ratios = (0.42, 0.62, 0.86, 0.62, 0.42)
        colors = (bright, deep, bright, deep, bright)
        bar_w = size * 0.10
        gap = size * 0.055
    else:
        ratios = (0.46, 0.80, 0.46)
        colors = (deep, bright, deep)
        bar_w = size * 0.16
        gap = size * 0.09
    total = len(ratios) * bar_w + (len(ratios) - 1) * gap
    x = (size - total) / 2.0
    for ratio, color in zip(ratios, colors):
        height = size * ratio
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(x, (size - height) / 2.0, bar_w, height), bar_w / 2.0, bar_w / 2.0
        )
        x += bar_w + gap
    if size >= 24:
        painter.setBrush(QColor("#FFFFFF"))
        dot = size * 0.11
        painter.drawEllipse(
            QRectF((size - dot) / 2.0, (size - dot) / 2.0, dot, dot)
        )
    painter.end()
    return pixmap
