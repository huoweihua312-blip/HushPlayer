"""Approved Browse landing page backed by the existing shared collection."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QTimer, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.browse_discovery import BrowseDiscoveryAdapter, BrowseDiscoverySnapshot
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.theme.icons import fluent_settings_interactive_icon, icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.cover_card import CoverCard


class BrowseSection(QFrame):
    """One approved Browse heading plus a reusable horizontal CoverCard row."""

    HORIZONTAL_PADDING = 32
    CARD_ROW_SPACING = 14

    track_activated = Signal(object)
    play_requested = Signal(object)
    context_menu_requested = Signal(object, object)

    def __init__(self, title: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._cards: list[CoverCard] = []
        self.setObjectName("browseSection")
        self.setFixedHeight(284)

        self.heading = QWidget(self)
        self.heading.setObjectName("browseSectionHeading")
        self.heading.setFixedHeight(40)
        heading_layout = QHBoxLayout(self.heading)
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(0)
        self.title_label = QLabel(title, self.heading)
        self.title_label.setObjectName("browseSectionTitle")
        self.status_label = QLabel(self.heading)
        self.status_label.setObjectName("browseSectionStatus")
        self.status_label.setVisible(False)
        self.refresh_button = QToolButton(self.heading)
        self.refresh_button.setObjectName("browseRefreshButton")
        self.refresh_button.setAccessibleName("刷新推荐")
        self.refresh_button.setToolTip("刷新推荐")
        self.refresh_button.setAutoRaise(True)
        self.refresh_button.setVisible(False)
        self.online_search_button = QToolButton(self.heading)
        self.online_search_button.setObjectName("browseOnlineSearchButton")
        self.online_search_button.setText("去在线搜索")
        self.online_search_button.setAccessibleName("去在线搜索")
        self.online_search_button.setToolTip("打开在线搜索")
        self.online_search_button.setVisible(False)
        self.see_all_button = QToolButton(self.heading)
        self.see_all_button.setObjectName("browseSeeAll")
        self.see_all_button.setText("查看全部")
        self.see_all_button.setToolTip(f"查看全部{title}")
        # Browse sections currently have no route-specific destination. Do
        # not expose an enabled button that cannot perform an action.
        self.see_all_button.hide()
        heading_layout.addWidget(self.title_label)
        heading_layout.addSpacing(10)
        heading_layout.addWidget(self.status_label)
        heading_layout.addStretch(1)
        heading_layout.addWidget(self.refresh_button)
        heading_layout.addWidget(self.online_search_button)
        heading_layout.addWidget(self.see_all_button)

        self.row = QWidget(self)
        self.row.setObjectName("browseCardRow")
        self.row.setFixedHeight(CoverCard.CARD_HEIGHT)
        self.row_layout = QHBoxLayout(self.row)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setSpacing(self.CARD_ROW_SPACING)
        self.empty_label = QLabel("这里还没有可展示的歌曲", self.row)
        self.empty_label.setObjectName("browseSectionEmpty")
        self.empty_label.setVisible(False)
        self.row_layout.addWidget(self.empty_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.row_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
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
            f"QFrame#browseSection {{ background: {c.surface_primary}; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QLabel#browseSectionTitle {{ color: {c.text_primary}; font-size: {theme.fonts.section_title}px; font-weight: 700; }}"
            f"QLabel#browseSectionStatus {{ padding: 3px 8px; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.text_secondary}; font-size: {theme.fonts.card_meta}px; font-weight: 400; }}"
            f"QLabel#browseSectionEmpty {{ color: {c.text_tertiary}; font-size: {theme.fonts.secondary}px; font-weight: 400; }}"
            f"QToolButton#browseRefreshButton {{ min-width: 32px; min-height: 32px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; color: {c.text_secondary}; background: {c.surface_secondary}; }}"
            f"QToolButton#browseRefreshButton:hover {{ color: {c.primary_text}; background: {c.hover_background}; border-color: {c.border_strong}; }}"
            f"QToolButton#browseOnlineSearchButton {{ min-height: 32px; padding: 0 {theme.metrics.spacing_sm}px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; color: {c.secondary_text}; background: {c.surface_secondary}; font-size: {theme.fonts.card_meta}px; font-weight: 400; }}"
            f"QToolButton#browseOnlineSearchButton:hover {{ color: {c.primary_text}; background: {c.hover_background}; border-color: {c.border_strong}; }}"
            f"QToolButton#browseSeeAll {{ border: 0; padding: 0; color: {c.accent}; font-size: {theme.fonts.card_meta}px; font-weight: 400; background: transparent; }}"
            f"QToolButton#browseSeeAll:hover {{ color: {c.text_primary}; }}"
        )
        self.refresh_button.setIcon(fluent_settings_interactive_icon("updates", theme, size=18))
        self.refresh_button.setIconSize(QSize(18, 18))
        for card in self._cards:
            card.set_theme(theme)

    def set_status(self, text: str) -> None:
        value = str(text or "").strip()
        self.status_label.setText(value)
        self.status_label.setVisible(bool(value))

    def set_tracks(
        self,
        tracks: tuple[Track, ...],
        *,
        interactive: bool,
        inactive_tooltip: str,
    ) -> None:
        self.empty_label.setVisible(not bool(tracks))
        while len(self._cards) < len(tracks):
            card = CoverCard(self._theme, self.row)
            card.activated.connect(self.track_activated)
            card.play_requested.connect(self.play_requested)
            card.context_menu_requested.connect(self.context_menu_requested)
            self._cards.append(card)
            self.row_layout.insertWidget(self.row_layout.count() - 1, card)
        for index, card in enumerate(self._cards):
            visible = index < len(tracks)
            card.setVisible(visible)
            if visible:
                card.set_track(tracks[index])
                card.set_interactive(interactive, inactive_tooltip)


class BrowsePage(QWidget):
    """A cached Browse page backed by shared library and online projections."""

    track_play_requested = Signal(object, str)
    online_search_requested = Signal()

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        theme: Theme,
        parent: QWidget | None = None,
        *,
        playback_enabled: bool = True,
        playlists: PlaylistAdapter | None = None,
        online: OnlineAdapter | None = None,
        online_discovery=None,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self._theme = theme
        self._playback_enabled = bool(playback_enabled)
        self.playlists = playlists
        self.online_adapter = online
        self.discovery_adapter = (
            BrowseDiscoveryAdapter(
                collection,
                playlists,
                online,
                search_service=getattr(online_discovery, "recommendation_search_service", None),
                parent=self,
            )
            if playlists is not None
            else None
        )
        self._reference_width = 1200
        self._content_safe_bottom = theme.metrics.player_bar_height + theme.metrics.content_safe_bottom
        self._refresh_scheduled = False
        self._density_sync_scheduled = False
        self._is_shutdown = False
        self.setObjectName("browsePage")

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("browseScrollArea")
        self.scroll_area.setAccessibleName("浏览内容")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget(self.scroll_area)
        self.content.setObjectName("browseContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(
            theme.metrics.page_margin,
            theme.metrics.spacing_xl,
            theme.metrics.page_margin,
            self._content_safe_bottom,
        )
        self.content_layout.setSpacing(theme.metrics.spacing_lg + theme.metrics.spacing_xs)

        self.intro_surface = QFrame(self.content)
        self.intro_surface.setObjectName("browseIntroSurface")
        self.title_label = QLabel("浏览", self.intro_surface)
        self.title_label.setObjectName("browsePageTitle")
        self.detail_label = QLabel("最近添加、再次播放与新的发现，都在这里自然衔接。", self.intro_surface)
        self.detail_label.setObjectName("browsePageDetail")
        intro_layout = QVBoxLayout(self.intro_surface)
        intro_layout.setContentsMargins(20, 20, 20, 20)
        intro_layout.setSpacing(8)
        intro_layout.addWidget(self.title_label)
        intro_layout.addWidget(self.detail_label)
        self.content_layout.addWidget(self.intro_surface)

        self.sections = {
            "recent_added": BrowseSection("最近添加", theme, self.content),
            "recommended": BrowseSection("为你推荐", theme, self.content),
            "recent_played": BrowseSection("最近播放", theme, self.content),
        }
        for section in self.sections.values():
            section.play_requested.connect(self._request_track_play)
            section.track_activated.connect(self._request_track_play)
            section.context_menu_requested.connect(self._show_track_menu)
            self.content_layout.addWidget(section)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area)
        self.collection.tracks_changed.connect(self._schedule_refresh)
        self.collection.recent_changed.connect(self._schedule_refresh)
        recommended = self.sections["recommended"]
        if self.discovery_adapter is not None:
            recommended.refresh_button.setVisible(True)
            recommended.refresh_button.clicked.connect(self.discovery_adapter.refresh_online)
            recommended.online_search_button.clicked.connect(self.online_search_requested)
            self.discovery_adapter.snapshot_changed.connect(self._render_snapshot)
            self.discovery_adapter.status_changed.connect(
                lambda _status: self._sync_recommendation_heading()
            )
        self.set_theme(theme)
        self._last_target_card_count = self.target_card_count
        self.refresh_cards()

    @property
    def content_safe_bottom(self) -> int:
        return self._content_safe_bottom

    @property
    def target_card_count(self) -> int:
        """Use the reference density without allowing cards to become tiny."""

        if self._reference_width <= 960:
            target = 3
        elif self._reference_width < 1200:
            target = 4
        elif self._reference_width < 1440:
            target = 5
        elif self._reference_width < 1600:
            target = 6
        else:
            target = 7

        # The window width includes the sidebar and the vertical scrollbar.
        # Reduce density only when the actual viewport cannot hold the full
        # row, instead of allowing the last card to be clipped at the edge.
        viewport_width = self.scroll_area.viewport().width()
        if viewport_width > 0:
            available_row_width = viewport_width - (
                2 * self._theme.metrics.page_margin
                + BrowseSection.HORIZONTAL_PADDING
            )
            while target > 3:
                row_width = target * CoverCard.CARD_WIDTH + (target - 1) * BrowseSection.CARD_ROW_SPACING
                if row_width <= available_row_width:
                    break
                target -= 1
        return target

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QWidget#browsePage, QScrollArea#browseScrollArea, QWidget#browseContent {{ background: {c.content_background}; }}"
            f"QFrame#browseIntroSurface {{ background: {c.surface_primary}; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QLabel#browsePageTitle {{ color: {c.text_primary}; font-size: {theme.fonts.page_title}px; font-weight: 700; }}"
            f"QLabel#browsePageDetail {{ color: {c.secondary_text}; font-size: {theme.fonts.secondary}px; font-weight: 500; }}"
            f"QScrollArea#browseScrollArea QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px 4px 0; }}"
            f"QScrollArea#browseScrollArea QScrollBar::handle:vertical {{ background: {c.text_tertiary}; min-height: 36px; border-radius: 5px; }}"
            f"QScrollArea#browseScrollArea QScrollBar::handle:vertical:hover {{ background: {c.text_secondary}; }}"
            f"QScrollArea#browseScrollArea QScrollBar::add-line:vertical, QScrollArea#browseScrollArea QScrollBar::sub-line:vertical, QScrollArea#browseScrollArea QScrollBar::add-page:vertical, QScrollArea#browseScrollArea QScrollBar::sub-page:vertical {{ height: 0; background: transparent; }}"
        )
        for section in self.sections.values():
            section.set_theme(theme)
        self._sync_recommendation_heading()

    def set_content_safe_bottom(self, height: int) -> None:
        self._content_safe_bottom = max(0, int(height))
        margins = self.content_layout.contentsMargins()
        self.content_layout.setContentsMargins(
            margins.left(), margins.top(), margins.right(), self._content_safe_bottom
        )

    def shutdown(self) -> None:
        self._is_shutdown = True
        self._refresh_scheduled = False
        self._density_sync_scheduled = False
        if self.discovery_adapter is not None:
            self.discovery_adapter.shutdown()

    def _schedule_refresh(self) -> None:
        """Coalesce same-turn library signals into one landing-page refresh."""

        if self._is_shutdown or self._refresh_scheduled:
            return
        self._refresh_scheduled = True
        QTimer.singleShot(0, self._flush_scheduled_refresh)

    def _flush_scheduled_refresh(self) -> None:
        if not self._refresh_scheduled:
            return
        self._refresh_scheduled = False
        if not self._is_shutdown:
            self.refresh_cards()

    def set_responsive_reference_width(self, width: int) -> None:
        width = max(1, int(width))
        if width == self._reference_width:
            self._schedule_density_sync()
            return
        self._reference_width = width
        if self.discovery_adapter is not None:
            self.discovery_adapter.set_maximum(self.target_card_count)
        self.refresh_cards()
        self._schedule_density_sync()

    def _schedule_density_sync(self) -> None:
        if self._is_shutdown or self._density_sync_scheduled:
            return
        self._density_sync_scheduled = True
        QTimer.singleShot(0, self._sync_density)

    def _sync_density(self) -> None:
        self._density_sync_scheduled = False
        if self._is_shutdown:
            return
        target = self.target_card_count
        if target == self._last_target_card_count:
            return
        self._last_target_card_count = target
        self.refresh_cards()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_density_sync()

    def refresh_cards(self) -> None:
        # A direct refresh (resize, initial render, or explicit retry) makes a
        # queued signal refresh unnecessary.  The queued callback checks this
        # flag and exits without rebuilding the cards a second time.
        self._refresh_scheduled = False
        if self.discovery_adapter is not None:
            self.discovery_adapter.set_maximum(self.target_card_count)
            self.discovery_adapter.refresh()
            return
        self._render_tracks(
            self._legacy_recent_added(),
            self._legacy_recommended(),
            self._legacy_recent_played(),
        )

    def _render_snapshot(self, snapshot: BrowseDiscoverySnapshot) -> None:
        self._render_tracks(snapshot.recent_added, snapshot.recommended, snapshot.recent_played)
        self._sync_recommendation_heading()

    def _render_tracks(
        self,
        recent_added: tuple[Track, ...],
        recommended: tuple[Track, ...],
        recent_played: tuple[Track, ...],
    ) -> None:
        interactive = self._playback_enabled
        tooltip = "真实模式尚未接入播放" if not interactive else "播放"
        self.sections["recent_added"].set_tracks(
            recent_added, interactive=interactive, inactive_tooltip=tooltip
        )
        self.sections["recommended"].set_tracks(
            recommended, interactive=interactive, inactive_tooltip=tooltip
        )
        self.sections["recommended"].online_search_button.setVisible(
            self.discovery_adapter is not None and not recommended
        )
        self.sections["recent_played"].set_tracks(
            recent_played, interactive=interactive, inactive_tooltip=tooltip
        )

    def _sync_recommendation_heading(self) -> None:
        section = self.sections["recommended"]
        if self.discovery_adapter is None:
            section.set_status("")
            return
        reason = self.discovery_adapter.recommendation_reason
        status = self.discovery_adapter.online_status
        detail = " · ".join(value for value in (reason, status) if value)
        section.set_status(detail)

    def _legacy_tracks(self) -> tuple[Track, ...]:
        tracks = tuple(
            track
            for track in self.collection.tracks()
            if not track.is_missing
            and not track.is_loading
            and not (self.collection.read_only and track.is_online)
        )
        return tracks

    def _legacy_recent_added(self) -> tuple[Track, ...]:
        tracks = self._legacy_tracks()
        maximum = self.target_card_count
        return self._take_distinct(sorted(tracks, key=lambda track: track.added_at, reverse=True), maximum)

    def _legacy_recommended(self) -> tuple[Track, ...]:
        tracks = self._legacy_tracks()
        return self._take_distinct(
            sorted(tracks, key=lambda track: (self._recommendation_key(track), track.id)),
            self.target_card_count,
        )

    def _legacy_recent_played(self) -> tuple[Track, ...]:
        return self._recent_tracks(self._legacy_tracks(), self.target_card_count)

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

    def _show_track_menu(self, track: Track, position) -> None:
        if not isinstance(track, Track) or self.playlists is None:
            return
        menu = QMenu(self)
        play_action = menu.addAction(icon("play", self._theme), "播放")
        play_action.setEnabled(self._playback_enabled)
        play_action.triggered.connect(lambda: self._request_track_play(track))

        online_track = None
        if track.is_online and self.online_adapter is not None:
            online_track = self.online_adapter.ensure_actionable_track(track)

        if track.is_online and online_track is not None:
            menu.addSeparator()
            favorite_action = menu.addAction(
                icon("favorite", self._theme),
                "取消收藏" if track.is_favorite else "收藏",
            )
            favorite_action.triggered.connect(
                lambda: self.online_adapter.toggle_favorite(online_track.id)
            )
        elif not self.collection.read_only:
            menu.addSeparator()
            favorite_action = menu.addAction(
                icon("favorite", self._theme),
                "取消收藏" if track.is_favorite else "收藏",
            )
            favorite_action.triggered.connect(
                lambda: self.collection.set_favorite(track.id, not track.is_favorite)
            )

        add_menu = menu.addMenu(icon("add", self._theme), "加入歌单")
        playlist_count = 0
        for playlist in self.playlists.playlists():
            action = add_menu.addAction(playlist.name)
            playlist_count += 1
            if online_track is not None:
                action.triggered.connect(
                    lambda checked=False, playlist_id=playlist.id: self.online_adapter.request_add_to_playlist(
                        online_track.id,
                        playlist_id,
                    )
                )
            else:
                action.triggered.connect(
                    lambda checked=False, playlist_id=playlist.id: self.playlists.add_tracks(
                        playlist_id,
                        (track.id,),
                    )
                )
        add_menu.setEnabled(playlist_count > 0 and (online_track is not None or not self.collection.read_only))

        if not menu.isEmpty():
            menu.exec(position)
        menu.deleteLater()

    def _request_track_play(self, track: Track) -> None:
        if not self._playback_enabled:
            return
        tracks = list(self.collection.tracks())
        if track.id not in {item.id for item in tracks}:
            tracks.append(track)
        self.track_play_requested.emit(tuple(tracks), track.id)
