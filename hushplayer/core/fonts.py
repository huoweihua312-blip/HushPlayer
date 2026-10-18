"""Bundled typeface loading (MiSans, same family as the original HushPlayer).

The fonts are shipped as application resources only — never installed into
Windows. See ``assets/fonts/MiSans-NOTICE.md`` and the bundled licence PDF.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from .logging_setup import get_logger
from .paths import resource_path

__all__ = ["PREFERRED_FAMILIES", "load_bundled_fonts", "loaded_families"]

log = get_logger(__name__)

PREFERRED_FAMILIES = ("MiSans", "MiSans Semibold", "Microsoft YaHei UI", "Segoe UI")

_FONT_FILES = (
    "MiSans-Regular.ttf",
    "MiSans-Semibold.ttf",
    "MiSans-Bold.ttf",
)

_loaded: list[str] = []


def _fonts_dir() -> Path:
    return resource_path("assets", "fonts")


def load_bundled_fonts() -> list[str]:
    """Register the bundled faces with Qt; safe to call more than once."""
    global _loaded
    if _loaded:
        return list(_loaded)
    if os.environ.get("HUSHPLAYER_NO_BUNDLED_FONTS") == "1":
        return []
    folder = _fonts_dir()
    families: list[str] = []
    for name in _FONT_FILES:
        path = folder / name
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log.warning("字体加载失败：%s", path)
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))
    _loaded = sorted({family for family in families if family})
    if _loaded:
        log.info("已加载内置字体：%s", ", ".join(_loaded))
    return list(_loaded)


def loaded_families() -> list[str]:
    return list(_loaded)
