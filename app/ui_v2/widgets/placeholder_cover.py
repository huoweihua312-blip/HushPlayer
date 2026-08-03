"""Stable, local placeholder-cover lookup with a small display-size pixmap cache."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


_COVER_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "placeholder_covers"
_COVER_NAMES = tuple(f"cover{number:02d}.svg" for number in range(1, 25))
_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def placeholder_cover_path(stable_id: str) -> Path:
    """Return the deterministic approved local cover for a stable track identity."""

    digest = hashlib.sha256(str(stable_id or "hushplayer").encode("utf-8")).digest()
    return _COVER_DIRECTORY / _COVER_NAMES[digest[0] % len(_COVER_NAMES)]


def placeholder_cover_index(stable_id: str) -> int:
    """Expose the stable 1-based asset index for tests and diagnostic views."""

    return _COVER_NAMES.index(placeholder_cover_path(stable_id).name) + 1


def cover_pixmap(stable_id: str, width: int, height: int) -> QPixmap:
    """Decode an approved cover only for a requested visible display size."""

    path = placeholder_cover_path(stable_id)
    key = (str(path), max(1, int(width)), max(1, int(height)))
    cached = _PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        pixmap = pixmap.scaled(
            key[1],
            key[2],
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
    _PIXMAP_CACHE[key] = pixmap
    return pixmap
