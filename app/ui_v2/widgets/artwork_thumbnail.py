"""Small painter-icon artwork surface for mock UI V2 tracks."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QWidget

from app.ui_v2.models.track import Track
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class ArtworkThumbnail(QLabel):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._track: Track | None = None
        self.setFixedSize(56, 56)
        self.setScaledContents(False)
        self.set_theme(theme)
        self.set_track(None)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"background: {theme.colors.elevated_background}; "
            f"border: 1px solid {theme.colors.border}; "
            f"border-radius: {theme.metrics.radius_md}px;"
        )
        self._refresh_artwork()

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self.setToolTip(track.album if track is not None else "没有正在播放的歌曲")
        self._refresh_artwork()

    def _refresh_artwork(self) -> None:
        icon_name = (
            "missing"
            if self._track is None
            else "online"
            if self._track.is_online
            else "local"
        )
        state = "disabled" if self._track is None else "selected"
        self.setPixmap(icon(icon_name, self._theme, state).pixmap(QSize(26, 26)))
