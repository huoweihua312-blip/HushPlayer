"""Compact identity header for Artist detail pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui_v2.models.artist import ArtistAggregate
from app.ui_v2.models.track import format_duration
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artist_action_row import ArtistActionRow
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel


class ArtistHero(QWidget):
    """Artwork, identity metadata, and inline Artist actions."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.artwork = ArtworkThumbnail(theme, self, size=176)
        self.artwork.setObjectName("artistHeroArtwork")
        self.eyebrow_label = QLabel("艺人", self)
        self.name_label = ElidedLabel(self)
        self.meta_label = ElidedLabel(self)
        self.duration_label = ElidedLabel(self)
        self.action_row = ArtistActionRow(theme, self)
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(6)
        details.addStretch(1)
        details.addWidget(self.eyebrow_label)
        details.addWidget(self.name_label)
        details.addWidget(self.meta_label)
        details.addWidget(self.duration_label)
        details.addSpacing(10)
        details.addWidget(self.action_row)
        details.addStretch(1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(details, 1)
        self.setObjectName("artistHero")
        self.setMinimumHeight(190)
        self.set_theme(theme)
        self.artist_aggregate = ArtistAggregate(None, (), (), 0, 0, 0)
        self.set_aggregate(self.artist_aggregate, "未知艺人")

    def set_aggregate(
        self,
        aggregate: ArtistAggregate,
        display_name: str = "未知艺人",
    ) -> None:
        self.artist_aggregate = aggregate
        representative = next((track for track in aggregate.tracks if not track.is_missing), None)
        self.artwork.set_track(representative)
        if not aggregate.exists:
            self.name_label.set_full_text(display_name)
            self.meta_label.set_full_text("")
            self.duration_label.set_full_text("")
            self.action_row.setVisible(False)
            return
        self.name_label.set_full_text(display_name)
        self.meta_label.set_full_text(
            f"{aggregate.track_count} 首歌曲 · {aggregate.album_count} 张专辑"
        )
        self.duration_label.set_full_text(
            f"总时长 {format_duration(aggregate.total_duration_ms)}"
            if aggregate.total_duration_ms > 0
            else ""
        )
        self.action_row.setVisible(True)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.artwork.set_theme(theme)
        self.eyebrow_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 600; color: {colors.accent};"
        )
        self.name_label.setStyleSheet(
            f"font-size: {max(32, theme.fonts.page_title - 2)}px; font-weight: 600; color: {colors.primary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {colors.secondary_text};"
        )
        self.duration_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {colors.subtle_text};"
        )
        self.action_row.set_theme(theme)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        size = 124 if compact else 176
        self.artwork.set_display_size(size)
        self.artwork.setFixedSize(size, size)
        self.setMinimumHeight(size + 12)
        self.action_row.set_compact(compact)
        self.duration_label.setVisible(not compact)
