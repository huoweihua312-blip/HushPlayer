"""Shared Hero header for local collection detail pages in UI V2."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
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
        self._reference_width = 0
        self.artwork = AbstractArtwork(theme, self)
        self.artwork.setObjectName("trackCollectionHeroArtwork")
        self.eyebrow_label = QLabel(self)
        self.title_label = QLabel(self)
        self.meta_label = QLabel(self)
        self.play_button = QToolButton(self)
        self.shuffle_button = QToolButton(self)
        self.more_button = QToolButton(self)
        self.back_button = QToolButton(self)
        self.play_button.setAccessibleName("播放")
        self.shuffle_button.setAccessibleName("随机播放")
        self.back_button.hide()
        # The generic collection hero has no formal More action. Keep the
        # handle for compatibility, but do not expose a no-op control.
        self.more_button.hide()
        self.play_button.clicked.connect(self.play_requested)
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        self._actions_layout.addWidget(self.back_button)
        self._actions_layout.addWidget(self.play_button)
        self._actions_layout.addWidget(self.shuffle_button)
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
        self._layout.setContentsMargins(24, 20, 24, 20)
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
        self.setStyleSheet(
            f"QWidget#trackCollectionHero {{ background: {colors.surface_primary}; border: 1px solid {colors.border}; "
            f"border-radius: {metrics.radius_lg}px; }}"
        )
        self.eyebrow_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 600; color: {colors.accent};"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.hero_title}px; font-weight: 600; color: {colors.primary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {colors.secondary_text};"
        )
        self.play_button.setText("播放")
        # The filled action uses the inverse icon color so the play glyph does
        # not disappear into the Quiet Orbit accent surface.
        self.play_button.setIcon(icon("play", theme, "inverse"))
        self.shuffle_button.setText("随机播放")
        self.shuffle_button.setIcon(icon("shuffle", theme, "normal"))
        self.more_button.setText("更多")
        self.play_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shuffle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for button in (self.play_button, self.shuffle_button):
            button.setIconSize(QSize(metrics.icon_sm, metrics.icon_sm))
            button.setMinimumHeight(metrics.control_height)
        self.play_button.setMinimumWidth(92)
        self.shuffle_button.setMinimumWidth(116)
        self.play_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid transparent; border-radius: {metrics.radius_md}px; "
            f"background: {colors.accent}; color: {colors.content_background}; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
            f"QToolButton:pressed {{ background: {colors.accent_pressed}; }}"
            f"QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border-color: {colors.focus_ring}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: {colors.surface_secondary}; }}"
        )
        self.shuffle_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 1px solid {colors.border}; border-radius: {metrics.radius_md}px; "
            f"background: {colors.surface_secondary}; color: {colors.primary_text}; }}"
            f"QToolButton:hover {{ background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
            f"QToolButton:pressed {{ background: {colors.selected_background}; }}"
            f"QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border-color: {colors.focus_ring}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: transparent; border-color: {colors.border}; }}"
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
        reference = self._reference_width or self.width()
        if reference < 950:
            extent = 82
        elif reference < 1220:
            extent = 118
        else:
            extent = 156
        self.artwork.setFixedSize(extent, extent)
        self._layout.setDirection(QBoxLayout.Direction.LeftToRight)
        self._layout.setSpacing(13 if reference < 950 else 17 if reference < 1220 else 22)
        self.setMinimumHeight(extent + 40)

    def set_responsive_reference_width(self, width: int) -> None:
        """Apply the content-page Hero scale without changing its layout role."""

        self._reference_width = max(1, int(width))
        self._apply_responsive_layout()
