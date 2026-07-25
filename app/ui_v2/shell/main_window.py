"""Third-stage UI V2 shell using one mock collection for every library page."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
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
        self.library_collection = LibraryCollectionAdapter(create_mock_tracks(1000), self)
        self.playlist_adapter = PlaylistAdapter(self.library_collection, self)
        self.library_adapter = LibraryAdapter(collection=self.library_collection, parent=self)
        self.navigation_adapter = NavigationAdapter(self.playlist_adapter, self)
        self.playback_adapter = PlaybackAdapter(self)
        self.playback_adapter.set_queue(self.library_collection.tracks())
        self.library_page = LibraryPage(self.library_adapter, self._theme, self)
        self.sidebar = NavigationSidebar(self.navigation_adapter, self._theme, self)
        self.router = ContentRouter(
            self.library_page,
            self.navigation_adapter,
            self.library_collection,
            self.playlist_adapter,
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
        self.root.setStyleSheet(build_stylesheet(self._theme))
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
        body = QWidget(self.root)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.router, 1)
        root_layout = QVBoxLayout(self.root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(body, 1)
        root_layout.addWidget(self.player_bar)
        self.setCentralWidget(self.root)

    def _connect_state(self) -> None:
        self.library_page.theme_changed.connect(self.set_theme)
        self.router.track_play_requested.connect(self._play_tracks)
        self.router.queue_requested.connect(self._play_queue)
        self.playback_adapter.track_changed.connect(self._on_playback_track_changed)
        self.library_collection.track_updated.connect(self.playback_adapter.update_track)
        self.library_collection.favorite_changed.connect(self._sync_favorite_from_library)
        self.playback_adapter.favorite_changed.connect(self._sync_favorite_from_player)

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

    def _on_playback_track_changed(self, track) -> None:
        track_id = track.id if track is not None else ""
        self.library_collection.set_playing_track(track_id)
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
