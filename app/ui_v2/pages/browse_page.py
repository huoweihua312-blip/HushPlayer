"""Approved Browse landing page backed by the existing shared collection."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.cover_card import CoverCard


class BrowseSection(QFrame):
    """One approved Browse heading plus a reusable horizontal CoverCard row."""

    track_activated = Signal(object)
    play_requested = Signal(object)

    def __init__(self, title: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._cards: list[CoverCard] = []
        self.setObjectName("browseSection")
        self.setFixedHeight(244)

        self.heading = QWidget(self)
        self.heading.setObjectName("browseSectionHeading")
        self.heading.setFixedHeight(34)
        heading_layout = QHBoxLayout(self.heading)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(0)
        self.title_label = QLabel(title, self.heading)
        self.title_label.setObjectName("browseSectionTitle")
        self.see_all_button = QToolButton(self.heading)
        self.see_all_button.setObjectName("browseSeeAll")
        self.see_all_button.setText("查看全部")
        self.see_all_button.setToolTip(f"查看全部{title}")
        heading_layout.addWidget(self.title_label)
        heading_layout.addStretch(1)
        heading_layout.addWidget(self.see_all_button)

        self.row = QWidget(self)
        self.row.setObjectName("browseCardRow")
        self.row.setFixedHeight(210)
        self.row_layout = QHBoxLayout(self.row)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setSpacing(20)
        self.row_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.heading)
        layout.addWidget(self.row)
        self.set_theme(theme)

    @property
    def cards(self) -> tuple[CoverCard, ...]:
        return tuple(self._cards)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QFrame#browseSection {{ background: transparent; border: 0; }}"
            f"QLabel#browseSectionTitle {{ color: {c.text_primary}; font-size: {theme.fonts.section_title}px; font-weight: 600; }}"
            f"QToolButton#browseSeeAll {{ border: 0; padding: 0; color: {c.accent}; font-size: {theme.fonts.card_meta}px; background: transparent; }}"
            f"QToolButton#browseSeeAll:hover {{ color: {c.text_primary}; }}"
        )
        for card in self._cards:
            card.set_theme(theme)

    def set_tracks(
        self,
        tracks: tuple[Track, ...],
        *,
        interactive: bool,
        inactive_tooltip: str,
    ) -> None:
        while len(self._cards) < len(tracks):
            card = CoverCard(self._theme, self.row)
            card.activated.connect(self.track_activated)
            card.play_requested.connect(self.play_requested)
            self._cards.append(card)
            self.row_layout.insertWidget(self.row_layout.count() - 1, card)
        for index, card in enumerate(self._cards):
            visible = index < len(tracks)
            card.setVisible(visible)
            if visible:
                card.set_track(tracks[index])
                card.set_interactive(interactive, inactive_tooltip)


class BrowsePage(QWidget):
    """A cached, local-only Browse page that never rebuilds collection adapters."""

    track_play_requested = Signal(object, str)

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        theme: Theme,
        parent: QWidget | None = None,
        *,
        playback_enabled: bool = True,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self._theme = theme
        self._playback_enabled = bool(playback_enabled)
        self._reference_width = 1200
        self._content_safe_bottom = theme.metrics.player_bar_height + theme.metrics.content_safe_bottom
        self.setObjectName("browsePage")

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("browseScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget(self.scroll_area)
        self.content.setObjectName("browseContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(30, 26, 40, self._content_safe_bottom)
        self.content_layout.setSpacing(0)

        self.title_label = QLabel("浏览", self.content)
        self.title_label.setObjectName("browsePageTitle")
        self.title_label.setFixedHeight(45)
        self.content_layout.addWidget(self.title_label)
        self.content_layout.addSpacing(30)

        self.sections = {
            "recent_added": BrowseSection("最近添加", theme, self.content),
            "recommended": BrowseSection("为你推荐", theme, self.content),
            "recent_played": BrowseSection("最近播放", theme, self.content),
        }
        for position, section in enumerate(self.sections.values()):
            section.play_requested.connect(self._request_track_play)
            section.track_activated.connect(self._request_track_play)
            self.content_layout.addWidget(section)
            if position < len(self.sections) - 1:
                self.content_layout.addSpacing(30)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area)
        self.collection.tracks_changed.connect(self.refresh_cards)
        self.collection.recent_changed.connect(self.refresh_cards)
        self.set_theme(theme)
        self.refresh_cards()

    @property
    def content_safe_bottom(self) -> int:
        return self._content_safe_bottom

    @property
    def target_card_count(self) -> int:
        """Use the reference density without allowing cards to become tiny."""

        if self._reference_width <= 960:
            return 3
        if self._reference_width >= 1400:
            return 7
        return 5

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QWidget#browsePage, QScrollArea#browseScrollArea, QWidget#browseContent {{ background: {c.app_background}; }}"
            f"QLabel#browsePageTitle {{ color: {c.text_primary}; font-size: {theme.fonts.page_title}px; font-weight: 700; }}"
        )
        for section in self.sections.values():
            section.set_theme(theme)

    def set_content_safe_bottom(self, height: int) -> None:
        self._content_safe_bottom = max(0, int(height))
        margins = self.content_layout.contentsMargins()
        self.content_layout.setContentsMargins(
            margins.left(), margins.top(), margins.right(), self._content_safe_bottom
        )

    def set_responsive_reference_width(self, width: int) -> None:
        width = max(1, int(width))
        if width == self._reference_width:
            return
        self._reference_width = width
        self.refresh_cards()

    def refresh_cards(self) -> None:
        tracks = tuple(
            track
            for track in self.collection.tracks()
            if not track.is_missing
            and not track.is_loading
            and not (self.collection.read_only and track.is_online)
        )
        maximum = self.target_card_count
        recent_added = self._take_distinct(
            sorted(tracks, key=lambda track: track.added_at, reverse=True), maximum
        )
        recommended = self._take_distinct(
            sorted(tracks, key=lambda track: (self._recommendation_key(track), track.id)), maximum
        )
        recent_played = self._recent_tracks(tracks, maximum)
        interactive = self._playback_enabled
        tooltip = "真实模式尚未接入播放" if not interactive else "播放"
        self.sections["recent_added"].set_tracks(
            recent_added, interactive=interactive, inactive_tooltip=tooltip
        )
        self.sections["recommended"].set_tracks(
            recommended, interactive=interactive, inactive_tooltip=tooltip
        )
        self.sections["recent_played"].set_tracks(
            recent_played, interactive=interactive, inactive_tooltip=tooltip
        )

    def _recent_tracks(self, tracks: tuple[Track, ...], maximum: int) -> tuple[Track, ...]:
        by_id = {track.id: track for track in tracks}
        from_statistics = tuple(
            by_id[entry.track_id]
            for entry in self.collection.recent_entries()
            if entry.track_id in by_id
        )
        if from_statistics:
            return from_statistics[:maximum]
        return self._take_distinct(
            sorted(tracks, key=lambda track: (self._recent_fallback_key(track), track.id)), maximum
        )

    @staticmethod
    def _take_distinct(tracks, maximum: int) -> tuple[Track, ...]:
        selected: list[Track] = []
        stable_ids: set[str] = set()
        for track in tracks:
            if track.stable_id in stable_ids:
                continue
            selected.append(track)
            stable_ids.add(track.stable_id)
            if len(selected) >= maximum:
                break
        return tuple(selected)

    @staticmethod
    def _recommendation_key(track: Track) -> bytes:
        return hashlib.sha256(f"hushplayer:recommended:{track.stable_id}".encode("utf-8")).digest()

    @staticmethod
    def _recent_fallback_key(track: Track) -> bytes:
        return hashlib.sha256(f"hushplayer:recent:{track.stable_id}".encode("utf-8")).digest()

    def _request_track_play(self, track: Track) -> None:
        if not self._playback_enabled:
            return
        self.track_play_requested.emit(self.collection.tracks(), track.id)
