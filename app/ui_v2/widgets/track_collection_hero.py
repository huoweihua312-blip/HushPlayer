"""Shared Hero header for local collection detail pages in UI V2."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QBoxLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.track import Track
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_atmosphere import AbstractArtwork


class TrackCollectionHero(QWidget):
    """One quiet artwork-and-actions header above a shared TrackTable."""

    play_requested = Signal()
    shuffle_requested = Signal()
    more_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.artwork = AbstractArtwork(theme, self)
        self.artwork.setObjectName("trackCollectionHeroArtwork")
        self.eyebrow_label = QLabel(self)
        self.title_label = QLabel(self)
        self.meta_label = QLabel(self)
        self.play_button = QToolButton(self)
        self.shuffle_button = QToolButton(self)
        self.more_button = QToolButton(self)
        self.back_button = QToolButton(self)
        self.back_button.hide()
        self.play_button.clicked.connect(self.play_requested)
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        self.more_button.clicked.connect(self.more_requested)
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        self._actions_layout.addWidget(self.back_button)
        self._actions_layout.addWidget(self.play_button)
        self._actions_layout.addWidget(self.shuffle_button)
        self._actions_layout.addWidget(self.more_button)
        self._actions_layout.addStretch(1)
        self._details_layout = QVBoxLayout()
        self._details_layout.setContentsMargins(0, 0, 0, 0)
        self._details_layout.setSpacing(5)
        self._details_layout.addStretch(1)
        self._details_layout.addWidget(self.eyebrow_label)
        self._details_layout.addWidget(self.title_label)
        self._details_layout.addWidget(self.meta_label)
        self._details_layout.addSpacing(12)
        self._details_layout.addLayout(self._actions_layout)
        self._details_layout.addStretch(1)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(24)
        self._layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._layout.addLayout(self._details_layout, 1)
        self.setObjectName("trackCollectionHero")
        self.set_theme(theme)
        self.set_content("歌单", "尚未选择内容", (), "歌单")

    def set_content(
        self,
        title: str,
        metadata: str,
        tracks: Iterable[Track] = (),
        eyebrow: str = "歌单",
    ) -> None:
        materialized = tuple(tracks)
        representative = next((track for track in materialized if not track.is_missing), None)
        self.artwork.set_track(representative)
        self.eyebrow_label.setText(eyebrow)
        self.title_label.setText(title)
        self.title_label.setToolTip(title)
        self.meta_label.setText(metadata)
        self.meta_label.setToolTip(metadata)

    def set_back_action(self, label: str | None) -> None:
        visible = bool(label)
        self.back_button.setVisible(visible)
        self.back_button.setText(label or "")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.artwork.set_theme(theme)
        colors = theme.colors
        metrics = theme.metrics
        self.eyebrow_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 600; color: {colors.accent};"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title + 8}px; font-weight: 600; color: {colors.primary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {colors.secondary_text};"
        )
        self.play_button.setText("播放")
        self.play_button.setIcon(icon("play", theme, "selected"))
        self.shuffle_button.setText("随机播放")
        self.shuffle_button.setIcon(icon("shuffle", theme, "selected"))
        self.more_button.setText("更多")
        self.play_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shuffle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for button in (self.play_button, self.shuffle_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
                f"border: 0; border-radius: {metrics.radius_sm}px; background: {colors.accent}; color: {colors.content_background}; }}"
                f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
                f"QToolButton:pressed {{ background: {colors.accent_pressed}; }}"
            )
        for button in (self.more_button, self.back_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_sm}px; "
                f"border: 0; border-radius: {metrics.radius_sm}px; color: {colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; }}"
            )
        self._apply_responsive_layout()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        compact = self.width() > 0 and self.width() < 780
        extent = 190 if compact else 240
        self.artwork.setFixedSize(extent, extent)
        self._layout.setDirection(
            QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        )
        self._layout.setSpacing(16 if compact else 24)
        self.setMinimumHeight(extent)
