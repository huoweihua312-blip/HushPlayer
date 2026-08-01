"""Third-stage UI V2 shell using one mock collection for every library page."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.navigation_adapter import NavigationAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.adapters.real_library_adapter import (
    RealLibraryAdapter,
    ui_v2_data_mode,
)
from app.ui_v2.adapters.settings_adapter import SettingsAdapter
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.shell.content_router import ContentRouter
from app.ui_v2.shell.navigation_sidebar import NavigationSidebar
from app.ui_v2.shell.player_bar import PlayerBar
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme


class ShellPresentationMode(str, Enum):
    NORMAL = "normal"
    IMMERSIVE = "immersive"
    IMMERSIVE_FULLSCREEN = "immersive_fullscreen"


class MainWindow(QMainWindow):
    """Composes cached V2 pages around one mock or read-only library source."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = get_theme("dark")
        self._immersive_shell_active = False
        self._immersive_normal_geometry: QRect | None = None
        self._immersive_transparency_enabled = False
        self._presentation_mode = ShellPresentationMode.NORMAL
        self._normal_window_flags = self.windowFlags()
        self._transparent_frame_active = False
        self._transparent_normal_geometry: QRect | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._immersive_transparency_supported = self.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self.data_mode = ui_v2_data_mode()
        is_real_library = self.data_mode == "real"
        self.library_collection = LibraryCollectionAdapter(
            () if is_real_library else create_mock_tracks(1000),
            self,
            read_only=is_real_library,
        )
        self.playlist_adapter = PlaylistAdapter(
            self.library_collection,
            self,
            seed_mock=not is_real_library,
            read_only=is_real_library,
        )
        self.online_adapter = OnlineAdapter(
            self.library_collection, self.playlist_adapter, self
        )
        self.library_adapter = LibraryAdapter(collection=self.library_collection, parent=self)
        self.navigation_adapter = NavigationAdapter(
            self.playlist_adapter,
            self,
            include_online=not is_real_library,
        )
        self.playback_adapter = PlaybackAdapter(self)
        self.lyrics_adapter = LyricsAdapter(self)
        self.immersive_lyrics_options = ImmersiveLyricsOptions(theme=self._theme.mode)
        self.settings_adapter = SettingsAdapter(
            self.lyrics_adapter, self.immersive_lyrics_options, self
        )
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
            self.settings_adapter,
            self.immersive_lyrics_options,
            self._theme,
            self,
        )
        self.player_bar = PlayerBar(self.playback_adapter, self._theme, self)
        self.player_bar.set_read_only(is_real_library)
        self.real_library_adapter = (
            RealLibraryAdapter(
                self.library_collection,
                self.playlist_adapter,
                self,
            )
            if is_real_library
            else None
        )
        self._build_shell()
        self._connect_state()
        self.setWindowTitle("HushPlayer")
        self.setMinimumSize(860, 560)
        self.resize(1200, 760)
        self.set_theme(self._theme.mode)
        if self.real_library_adapter is not None:
            self.real_library_adapter.state_changed.connect(self._on_real_library_state)
            self.library_page.empty_state.action_requested.connect(
                self.real_library_adapter.refresh
            )
            self.real_library_adapter.load()

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def presentation_mode(self) -> ShellPresentationMode:
        return self._presentation_mode

    @property
    def transparency_debug_state(self) -> dict[str, object]:
        return {
            "main_window_id": id(self),
            "top_level_count": len([widget for widget in QApplication.topLevelWidgets() if isinstance(widget, MainWindow)]),
            "main_translucent": self.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
            "central_auto_fill": self.root.autoFillBackground(),
            "root_window_alpha": self.root.palette().color(QPalette.ColorRole.Window).alpha(),
            "body_window_alpha": self.body.palette().color(QPalette.ColorRole.Window).alpha(),
            "content_window_alpha": self.content_container.palette().color(QPalette.ColorRole.Window).alpha(),
            "background_mode": getattr(self.router._pages.get("immersive_lyrics"), "background_mode", "artwork"),
            "background_opacity": getattr(self.router._pages.get("immersive_lyrics"), "background_opacity_percent", 100),
            "window_flags": int(self.windowFlags()),
        }

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

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.real_library_adapter is not None:
            self.real_library_adapter.shutdown()
        super().closeEvent(event)

    def _build_shell(self) -> None:
        self.root = QWidget(self)
        self.root.setObjectName("uiV2Root")
        self.body = QWidget(self.root)
        self.body.setObjectName("uiV2Body")
        self._body_layout = QHBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self.sidebar_container = QWidget(self.body)
        self.sidebar_container.setObjectName("uiV2SidebarContainer")
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(self.sidebar)
        self.content_container = QWidget(self.body)
        self.content_container.setObjectName("uiV2ContentContainer")
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.router.setObjectName("uiV2ContentRouter")
        content_layout.addWidget(self.router)
        self._body_layout.addWidget(self.sidebar_container)
        self._body_layout.addWidget(self.content_container, 1)
        self.player_bar_container = QWidget(self.root)
        self.player_bar_container.setObjectName("uiV2PlayerBarContainer")
        player_layout = QVBoxLayout(self.player_bar_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(0)
        player_layout.addWidget(self.player_bar)
        self._root_layout = QVBoxLayout(self.root)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self._root_layout.addWidget(self.body, 1)
        self._root_layout.addWidget(self.player_bar_container)
        self.setCentralWidget(self.root)
        self._shell_surface_states = tuple(
            (widget, QPalette(widget.palette()), widget.autoFillBackground())
            for widget in (self.root, self.body, self.content_container, self.router)
        )

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
        self.settings_adapter.theme_preview_changed.connect(self.set_theme)
        self.settings_adapter.immersive_preview_changed.connect(
            self.router.apply_immersive_options
        )
        self.settings_adapter.motion_preview_changed.connect(
            self.router.set_reduce_motion_preview
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
            self._set_presentation_mode(ShellPresentationMode.IMMERSIVE_FULLSCREEN)
            if page is not None:
                page.set_host_fullscreen(True)
            return
        if self.isFullScreen():
            self.showNormal()
            if self._immersive_normal_geometry is not None:
                self.setGeometry(self._immersive_normal_geometry)
        if page is not None:
            page.set_host_fullscreen(False)
        if self._immersive_shell_active:
            self._set_presentation_mode(ShellPresentationMode.IMMERSIVE)

    def set_immersive_transparency(self, enabled: bool) -> None:
        self._immersive_transparency_enabled = bool(enabled) and self._immersive_shell_active
        self._set_shell_transparency(self._immersive_transparency_enabled)
        self._apply_root_stylesheet()

    def _sync_immersive_shell(self, route_id: str) -> None:
        immersive = route_id == "immersive_lyrics"
        if immersive == self._immersive_shell_active:
            return
        self._immersive_shell_active = immersive
        if immersive:
            page = self.router._pages.get("immersive_lyrics")
            self._immersive_transparency_enabled = bool(
                page is not None and getattr(page, "background_mode", "artwork") == "transparent"
            )
            self._set_presentation_mode(ShellPresentationMode.IMMERSIVE)
        else:
            self.set_immersive_fullscreen(False)
            self._immersive_transparency_enabled = False
            self._set_presentation_mode(ShellPresentationMode.NORMAL)
        self._set_shell_transparency(self._immersive_transparency_enabled)
        self._apply_root_stylesheet()

    def _set_presentation_mode(self, mode: ShellPresentationMode) -> None:
        self._presentation_mode = mode
        immersive = mode is not ShellPresentationMode.NORMAL
        self.sidebar.setVisible(not immersive)
        self.sidebar_container.setVisible(not immersive)
        self.player_bar.setVisible(not immersive)
        self.player_bar_container.setVisible(not immersive)
        if immersive:
            self.sidebar_container.setMinimumWidth(0)
            self.sidebar_container.setMaximumWidth(0)
            self._body_layout.setStretch(0, 0)
            self._body_layout.setSpacing(0)
            self._root_layout.setContentsMargins(0, 0, 0, 0)
        else:
            self.sidebar_container.setMinimumWidth(0)
            self.sidebar_container.setMaximumWidth(16_777_215)
            self._body_layout.setStretch(0, 0)
            self._body_layout.setStretch(1, 1)
            self._body_layout.setSpacing(0)
            self._root_layout.setContentsMargins(0, 0, 0, 0)
        self.body.updateGeometry()
        self.root.updateGeometry()

    def _set_shell_transparency(self, enabled: bool) -> None:
        for widget, normal_palette, normal_auto_fill in self._shell_surface_states:
            if enabled:
                transparent_palette = QPalette(widget.palette())
                transparent = QColor(0, 0, 0, 0)
                transparent_palette.setColor(QPalette.ColorRole.Window, transparent)
                transparent_palette.setColor(QPalette.ColorRole.Base, transparent)
                widget.setPalette(transparent_palette)
                widget.setAutoFillBackground(False)
                widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            else:
                widget.setPalette(normal_palette)
                widget.setAutoFillBackground(normal_auto_fill)
                widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._set_transparent_window_frame(enabled and self._immersive_transparency_supported)

    def _set_transparent_window_frame(self, enabled: bool) -> None:
        # The offscreen/minimal plugins have no native frame and forcibly place
        # top-level widgets at (0, 0).  Keep the same window instance there;
        # Windows uses the frameless transition below for real per-pixel alpha.
        if QGuiApplication.platformName().lower() in {"offscreen", "minimal"}:
            self._transparent_frame_active = False
            return
        if bool(enabled) == self._transparent_frame_active:
            return
        if enabled:
            self._transparent_normal_geometry = QRect(self.geometry())
        geometry = QRect(self._transparent_normal_geometry or self.geometry())
        fullscreen = self.isFullScreen()
        was_visible = self.isVisible()
        flags = self._normal_window_flags | Qt.WindowType.FramelessWindowHint if enabled else self._normal_window_flags
        self.setWindowFlags(flags)
        self._transparent_frame_active = bool(enabled)
        if fullscreen:
            self.showFullScreen()
        elif was_visible:
            self.show()
            self.setGeometry(geometry)
            self.raise_()
            self.activateWindow()
            QTimer.singleShot(
                0,
                lambda saved=QRect(geometry): self._restore_transparent_frame_geometry(saved),
            )
        if not enabled:
            self._transparent_normal_geometry = None

    def _restore_transparent_frame_geometry(self, geometry: QRect) -> None:
        """Finalize a same-window native frame transition after Qt recreates its handle."""
        if not self.isFullScreen():
            self.setGeometry(geometry)
            self.raise_()
            self.activateWindow()

    def _apply_root_stylesheet(self) -> None:
        stylesheet = build_stylesheet(self._theme)
        if self._immersive_transparency_enabled and self._immersive_transparency_supported:
            stylesheet += (
                "\nQWidget#uiV2Root, QWidget#uiV2Body, QWidget#uiV2ContentContainer, "
                "QStackedWidget#uiV2ContentRouter { background: transparent; }\n"
            )
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
        if self.library_collection.read_only:
            return
        current = self.playback_adapter.state.current_track
        if current is not None:
            self.library_collection.set_favorite(current.id, favorite)

    def _on_real_library_state(self, state: str, detail: str) -> None:
        if state == "loading":
            self.library_page.empty_state.set_action("")
            self.library_page.set_view_state("loading", detail)
            return
        if state == "error":
            self.library_page.empty_state.set_action("重试")
            self.library_page.set_view_state("error", detail)
            return
        self.library_page.empty_state.set_action("")
        self.library_page.set_view_state(
            "content" if state == "loaded" else "empty",
            detail,
        )

    def _on_player_bar_action(self, action: str) -> None:
        if action == "lyrics":
            self.navigation_adapter.set_route("lyrics")
