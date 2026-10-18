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

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap

from .paths import resource_path

#: Official asset filenames, documented in assets/brand/README.md.
LOGO = "logo.png"
LOGO_LIGHT = "logo_light.png"
LOGO_DARK = "logo_dark.png"
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


def has_official_logo() -> bool:
    """True when the user has supplied the real logo files."""
    return any(
        _existing(("assets", "brand", name)) is not None
        for name in (LOGO, LOGO_LIGHT, LOGO_DARK, ICON, ICON_PNG)
    )


def logo_path(mode: str = "dark") -> Path | None:
    """Path of the logo artwork appropriate for ``mode`` (``light``/``dark``)."""
    preferred = LOGO_LIGHT if mode == "light" else LOGO_DARK
    return _existing(
        ("assets", "brand", preferred),
        ("assets", "brand", LOGO),
        _PLACEHOLDER_PNG,
    )


def icon_path() -> Path | None:
    return _existing(
        ("assets", "brand", ICON),
        _PLACEHOLDER_ICO,
    )


def logo_pixmap(size: int, mode: str = "dark", *, dpr: float = 2.0) -> QPixmap | None:
    path = logo_path(mode)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    target = max(8, int(size * dpr))
    scaled = pixmap.scaled(
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
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    target = max(8, int(size * dpr))
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
