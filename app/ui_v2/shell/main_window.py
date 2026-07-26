"""Third-stage UI V2 shell using one mock collection for every library page."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.shell.content_router import ContentRouter
from app.ui_v2.shell.navigation_sidebar import NavigationSidebar
from app.ui_v2.shell.player_bar import PlayerBar
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme


class MainWindow(QMainWindow):
    """Composes cached V2 pages around shared mock music-library state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = get_theme("dark")
        self._immersive_shell_active = False
        self._immersive_normal_geometry: QRect | None = None
        self._immersive_transparency_enabled = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._immersive_transparency_supported = self.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self.library_collection = LibraryCollectionAdapter(create_mock_tracks(1000), self)
        self.playlist_adapter = PlaylistAdapter(self.library_collection, self)
        self.online_adapter = OnlineAdapter(
            self.library_collection, self.playlist_adapter, self
        )
        self.library_adapter = LibraryAdapter(collection=self.library_collection, parent=self)
        self.navigation_adapter = NavigationAdapter(self.playlist_adapter, self)
        self.playback_adapter = PlaybackAdapter(self)
        self.lyrics_adapter = LyricsAdapter(self)
        self.playback_adapter.set_queue(self.library_collection.tracks())
        self.library_page = LibraryPage(self.library_adapter, self._theme, self)
        self.sidebar = NavigationSidebar(self.navigation_adapter, self._theme, self)
        self.router = ContentRouter(
            self.library_page,
            self.navigation_adapter,
            self.library_collection,
            self.playlist_adapter,
            self.online_adapter,
            self.lyrics_adapter,
            self.playback_adapter,
            self._theme,
            self,
        )
        self.player_bar = PlayerBar(self.playback_adapter, self._theme, self)
        self._build_shell()
        self._connect_state()
        self.setWindowTitle("HushPlayer UI V2")
        self.setMinimumSize(860, 560)
        self.resize(1200, 760)
        self.set_theme(self._theme.mode)

    @property
    def theme(self) -> Theme:
        return self._theme

    def set_theme(self, mode: str) -> None:
        self._theme = get_theme(mode)
        self._apply_root_stylesheet()
        self.library_page.set_theme(self._theme)
        self.sidebar.set_theme(self._theme)
        self.router.set_theme(self._theme)
        self.player_bar.set_theme(self._theme)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = self.width() < 1100
        self.sidebar.set_compact(compact)
        self.player_bar.set_compact(compact)
        self.library_page.track_table.set_responsive_reference_width(self.width())
        self.router.set_responsive_reference_width(self.width())

    def _build_shell(self) -> None:
        self.root = QWidget(self)
        self.root.setObjectName("uiV2Root")
        self.body = QWidget(self.root)
        self._body_layout = QHBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_layout.addWidget(self.sidebar)
        self._body_layout.addWidget(self.router, 1)
        root_layout = QVBoxLayout(self.root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.body, 1)
        root_layout.addWidget(self.player_bar)
        self.setCentralWidget(self.root)

    def _connect_state(self) -> None:
        self.library_page.theme_changed.connect(self.set_theme)
        self.router.track_play_requested.connect(self._play_tracks)
        self.router.queue_requested.connect(self._play_queue)
        self.router.online_play_requested.connect(self._play_online_track)
        self.router.immersive_fullscreen_requested.connect(
            self.set_immersive_fullscreen
        )
        self.router.immersive_transparency_requested.connect(
            self.set_immersive_transparency
        )
        self.navigation_adapter.route_changed.connect(self._sync_immersive_shell)
        self.playback_adapter.track_changed.connect(self._on_playback_track_changed)
        self.playback_adapter.track_changed.connect(self.lyrics_adapter.set_track)
        self.playback_adapter.position_changed.connect(self.lyrics_adapter.set_position)
        self.lyrics_adapter.seek_requested.connect(self.playback_adapter.seek)
        self.player_bar.mock_action_requested.connect(self._on_player_bar_action)
        self.library_collection.track_updated.connect(self.playback_adapter.update_track)
        self.library_collection.favorite_changed.connect(self._sync_favorite_from_library)
        self.playback_adapter.favorite_changed.connect(self._sync_favorite_from_player)
        self._sync_immersive_shell(self.navigation_adapter.route)

    def set_immersive_fullscreen(self, enabled: bool) -> None:
        enabled = bool(enabled)
        page = self.router._pages.get("immersive_lyrics")
        if enabled:
            if not self.isFullScreen():
                self._immersive_normal_geometry = QRect(self.geometry())
                self.showFullScreen()
            if page is not None:
                page.set_host_fullscreen(True)
            return
        if self.isFullScreen():
            self.showNormal()
            if self._immersive_normal_geometry is not None:
                self.setGeometry(self._immersive_normal_geometry)
        if page is not None:
            page.set_host_fullscreen(False)

    def set_immersive_transparency(self, enabled: bool) -> None:
        self._immersive_transparency_enabled = bool(enabled) and self._immersive_shell_active
        self._apply_root_stylesheet()

    def _sync_immersive_shell(self, route_id: str) -> None:
        immersive = route_id == "immersive_lyrics"
        if immersive == self._immersive_shell_active:
            return
        self._immersive_shell_active = immersive
        self.sidebar.setVisible(not immersive)
        self.player_bar.setVisible(not immersive)
        if not immersive:
            self.set_immersive_fullscreen(False)
            self._immersive_transparency_enabled = False
        self._apply_root_stylesheet()

    def _apply_root_stylesheet(self) -> None:
        stylesheet = build_stylesheet(self._theme)
        if self._immersive_transparency_enabled and self._immersive_transparency_supported:
            stylesheet += "\nQWidget#uiV2Root { background: transparent; }\n"
        self.root.setStyleSheet(stylesheet)

    def _play_tracks(self, tracks, track_id: str) -> None:
        available = tuple(track for track in tracks if not track.is_missing)
        if not available:
            return
        self.playback_adapter.set_queue(available)
        self.playback_adapter.play_track(track_id)

    def _play_queue(self, tracks, shuffle: bool) -> None:
        available = tuple(track for track in tracks if not track.is_missing)
        if not available:
            return
        self.playback_adapter.set_queue(available)
        if self.playback_adapter.state.shuffle_enabled != shuffle:
            self.playback_adapter.toggle_shuffle()
        self.playback_adapter.play_track(available[0].id)

    def _play_online_track(self, track) -> None:
        self.playback_adapter.set_queue((track,))
        self.playback_adapter.play_track(track.id)

    def _on_playback_track_changed(self, track) -> None:
        track_id = track.id if track is not None else ""
        self.library_collection.set_playing_track(track_id)
        self.router.set_playing_track(track_id)
        if track is not None:
            self.library_collection.record_play(track.id)

    def _sync_favorite_from_library(self, track_id: str, favorite: bool) -> None:
        current = self.playback_adapter.state.current_track
        if current is not None and current.id == track_id:
            self.playback_adapter.set_current_favorite(favorite)

    def _sync_favorite_from_player(self, favorite: bool) -> None:
        current = self.playback_adapter.state.current_track
        if current is not None:
            self.library_collection.set_favorite(current.id, favorite)

    def _on_player_bar_action(self, action: str) -> None:
        if action == "lyrics":
            self.navigation_adapter.set_route("lyrics")
