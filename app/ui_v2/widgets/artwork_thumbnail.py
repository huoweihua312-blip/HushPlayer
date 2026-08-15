"""Small painter-icon artwork surface for mock UI V2 tracks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.placeholder_cover import cover_pixmap
from app.ui_v2.widgets.track_display import display_track_text


_ARTWORK_CACHE: dict[tuple[str, str, int, int], QPixmap] = {}
_ARTWORK_SOURCE_CACHE: dict[
    tuple[str, str, str, int, int], tuple[str, QPixmap]
] = {}
_ARTWORK_SOURCE_CACHE_LIMIT = 128


def artwork_pixmap_for_track(track: Track | None, width: int, height: int) -> QPixmap:
    """Return real track artwork when available, otherwise the one formal fallback."""

    width = max(1, int(width))
    height = max(1, int(height))
    if track is None:
        return cover_pixmap("hushplayer", width, height)

    data = bytes(track.artwork_data or b"")
    source_cache_key = (
        track.stable_id,
        str(track.artwork_path or ""),
        str(track.artwork_key or ""),
        len(data),
        id(data) if data else 0,
    )
    cached_source = _ARTWORK_SOURCE_CACHE.get(source_cache_key)
    if cached_source is not None:
        source_key, source = cached_source
    else:
        source_key = ""
        source = QPixmap()
        if data:
            source_key = hashlib.sha256(data).hexdigest()[:20]
            source.loadFromData(data)
        if source.isNull() and track.artwork_path:
            path = Path(track.artwork_path)
            if path.is_file():
                source_key = f"file:{path}"
                source.load(str(path))
        if not source.isNull():
            _ARTWORK_SOURCE_CACHE[source_cache_key] = (source_key, source)
            if len(_ARTWORK_SOURCE_CACHE) > _ARTWORK_SOURCE_CACHE_LIMIT:
                oldest_key = next(iter(_ARTWORK_SOURCE_CACHE))
                _ARTWORK_SOURCE_CACHE.pop(oldest_key, None)
    if source.isNull():
        return cover_pixmap(track.stable_id, width, height)

    cache_key = (track.stable_id, source_key, width, height)
    cached = _ARTWORK_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached
    scaled = source.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    if scaled.size() != source.size() or scaled.width() != width or scaled.height() != height:
        left = max(0, (scaled.width() - width) // 2)
        top = max(0, (scaled.height() - height) // 2)
        scaled = scaled.copy(left, top, width, height)
    _ARTWORK_CACHE[cache_key] = scaled
    return scaled


class ArtworkThumbnail(QLabel):
    def __init__(
        self,
        theme: Theme,
        parent: QWidget | None = None,
        *,
        size: int = 48,
        clip_artwork: bool = False,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._track: Track | None = None
        self._size = max(32, int(size))
        self._clip_artwork = bool(clip_artwork)
        self._artwork_pixmap = QPixmap()
        self.setFixedSize(self._size, self._size)
        self.setScaledContents(False)
        self.set_theme(theme)
        self.set_track(None)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._clip_artwork:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setStyleSheet("background: transparent; border: 0;")
        else:
            self.setStyleSheet(
                f"background: {theme.colors.surface_secondary}; "
                f"border: 0; "
                f"border-radius: 5px;"
            )
        # Theme changes only restyle the surface.  The artwork pixmap itself
        # is theme-independent, so keep it in place to avoid decoding covers
        # again while a library or favorites page is repainting.
        if self._track is None:
            self._refresh_artwork()
        else:
            self.update()

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self.setToolTip(
            display_track_text(track)[2] if track is not None else "没有正在播放的歌曲"
        )
        self._refresh_artwork()

    def set_display_size(self, size: int) -> None:
        """Resize this presentation surface without replacing its Track."""

        self._size = max(32, int(size))
        self.setFixedSize(self._size, self._size)
        self._refresh_artwork()

    def _refresh_artwork(self) -> None:
        pixmap = (
            artwork_pixmap_for_track(self._track, self._size, self._size)
            if self._track is not None
            else self._empty_pixmap()
        )
        self._artwork_pixmap = pixmap
        self.setPixmap(pixmap)
        self.update()

    def _corner_radius(self) -> float:
        """Use the approved responsive radius for the large artwork surface."""

        if self._size <= 230:
            return 15.0
        if self._size <= 340:
            return 19.0
        return 21.0

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._clip_artwork:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        bounds = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(bounds, self._corner_radius(), self._corner_radius())
        painter.setClipPath(path)
        pixmap = self._artwork_pixmap
        if not pixmap.isNull():
            target_size = self.size()
            scaled = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            source_x = max(0, (scaled.width() - target_size.width()) // 2)
            source_y = max(0, (scaled.height() - target_size.height()) // 2)
            source = scaled.rect().adjusted(
                source_x,
                source_y,
                source_x - scaled.width() + target_size.width(),
                source_y - scaled.height() + target_size.height(),
            )
            painter.drawPixmap(self.rect(), scaled, source)
        painter.end()

    def _empty_pixmap(self) -> QPixmap:
        """A deliberately quiet, but visible, no-track artwork surface."""

        pixmap = QPixmap(self._size, self._size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(self._theme.colors.border_strong), 1))
        painter.setBrush(QColor(self._theme.colors.surface_selected))
        inset = 0.5
        extent = self._size - 1
        radius = max(5, self._size // 9)
        painter.drawRoundedRect(QRectF(inset, inset, extent, extent), radius, radius)
        painter.setPen(QPen(QColor(self._theme.colors.text_tertiary), 1.25))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ring = self._size * 0.27
        painter.drawEllipse(QRectF(self._size * 0.27, self._size * 0.27, ring * 2, ring * 2))
        dot = max(3, self._size // 12)
        painter.drawEllipse(QRectF(self._size * 0.46, self._size * 0.46, dot, dot))
        painter.end()
        return pixmap
