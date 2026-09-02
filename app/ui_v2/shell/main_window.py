"""Third-stage UI V2 shell using one mock collection for every library page."""

from __future__ import annotations

import ctypes
from dataclasses import replace
from enum import Enum
import math
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QUrl,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QMouseEvent,
    QImage,
    QBrush,
    QPainter,
    QPainterPath,
    QPalette,
    QPixmap,
    QRadialGradient,
    QRegion,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.core.app_paths import AppPaths
from app.core.version import APP_VERSION
from app.services.app_update_service import AppUpdateService, UpdateManifest
from app.services.cache_maintenance import clear_missing_cache_files
from app.services.library_repository import LibraryRepository
from app.services.music_folder_scan import MusicFolderImportService
from app.services.online_discovery_runtime import OnlineDiscoveryRuntime
from app.services.remote_track_store import RemoteTrackStore
from app.startup_diagnostics import StartupDiagnostics
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
from app.ui_v2.adapters.legacy_settings_bridge import (
    LegacySettingsBridge,
    SettingsBridgeError,
    normalize_immersive_background_visual_mode,
)
from app.ui_v2.mock.track_factory import create_mock_tracks
from app.ui_v2.pages.all_songs_page import AllSongsPage
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.models.desktop_lyrics_settings import (
    DESKTOP_LYRICS_QUICK_SETTING_KEYS,
)
from app.ui_v2.models.settings_snapshot import SettingsSnapshot
from app.ui_v2.models.track import Track, artwork_url_from_payload
from app.ui_v2.shell.close_behavior_controller import CloseBehaviorController
from app.ui_v2.shell.content_router import ContentRouter
from app.ui_v2.shell.desktop_lyrics_window import DesktopLyricsWindow
from app.ui_v2.shell.navigation_sidebar import NavigationSidebar
from app.ui_v2.shell.player_bar import PlayerBar
from app.ui_v2.dialogs.update_dialog import UpdateDialog
from app.ui_v2.widgets.custom_title_bar import CustomTitleBar
from app.ui_v2.widgets.desktop_lyrics_quick_settings import DesktopLyricsQuickSettingsPopover
from app.ui_v2.widgets.online_recovery_dialog import OnlineRecoveryCandidateDialog
from app.ui_v2.widgets.settings_overlay import SettingsOverlay
from app.ui_v2.widgets.track_action_dialogs import (
    PlaylistSelectionDialog,
    TrackInfoDialog,
)
from app.ui_v2.theme.styles import (
    build_application_palette,
    build_dialog_stylesheet,
    build_stylesheet,
)
from app.ui_v2.theme.tokens import Theme, get_theme


_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DEFAULT = 0
_DWMWCP_ROUND = 2
_AUTO_RECOVERY_FAILURE_STATES = frozenset(
    {
        "source_unavailable",
        "resolve_failed",
        "permission_denied",
        "playback_error",
    }
)
_DESKTOP_LYRICS_CONTINUOUS_PREVIEW_KEYS = frozenset(
    {"floating_lyrics_font_size", "floating_lyrics_width"}
)
_REAL_LIBRARY_IMMEDIATE_PROJECTION_LIMIT = 12


class ShellPresentationMode(str, Enum):
    NORMAL = "normal"
    IMMERSIVE = "immersive"
    IMMERSIVE_FULLSCREEN = "immersive_fullscreen"


def _resolve_data_mode(value: str | None) -> str:
    if value is None:
        return ui_v2_data_mode()
    mode = str(value or "").strip().casefold()
    if mode not in {"mock", "real"}:
        raise ValueError(f"Unsupported UI V2 data mode: {value!r}")
    return mode


class ThemeRevealOverlay(QWidget):
    """Temporary old-theme layer used by the opt-in transition demo."""

    finished = Signal()
    _DURATION_MS = 1200
    _FEATHER_PX = 110

    def __init__(self, snapshot: QPixmap, origin: QPoint, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("themeRevealOverlay")
        self.setStyleSheet(
            "QWidget#themeRevealOverlay { background: transparent; border: 0; }"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self._snapshot = snapshot
        self._origin = QPoint(origin)
        self._radius = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(
            math.hypot(float(self.width()), float(self.height())) + self._FEATHER_PX
        )
        self._animation.setDuration(self._DURATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_radius)
        self._animation.finished.connect(self._finish)

    def start(self) -> None:
        self.show_ready()
        self.start_animation()

    def show_ready(self) -> None:
        self.raise_()
        self.show()
        self.repaint()

    def start_animation(self) -> None:
        if self._animation.state() == QAbstractAnimation.State.Running:
            return
        self._animation.start()

    def _set_radius(self, value) -> None:
        self._radius = float(value or 0.0)
        self.update()

    def _finish(self) -> None:
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._snapshot.isNull():
            return
        if self._radius <= 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(self.rect(), self._snapshot)
            return
        feather = min(self._FEATHER_PX, max(24.0, self._radius * 0.24))
        inner_ratio = max(0.0, (self._radius - feather) / self._radius)
        image = QImage(
            self.size(),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.GlobalColor.transparent)
        image_painter = QPainter(image)
        image_painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        image_painter.drawPixmap(image.rect(), self._snapshot)
        image_painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_DestinationIn
        )
        inverse_gradient = QRadialGradient(
            QPointF(float(self._origin.x()), float(self._origin.y())),
            self._radius,
        )
        inverse_gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        inverse_gradient.setColorAt(inner_ratio, QColor(0, 0, 0, 0))
        inverse_gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
        image_painter.fillRect(image.rect(), QBrush(inverse_gradient))
        image_painter.end()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(self.rect(), image)


class MainWindow(QMainWindow):
    """Composes cached V2 pages around one mock or read-only library source."""

    _WINDOW_CORNER_RADIUS = 16
    _THEME_REVEAL_APPLY_DELAY_MS = 16

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        data_mode: str | None = None,
        settings_path: Path | str | None = None,
        repository: LibraryRepository | None = None,
        remote_tracks: RemoteTrackStore | None = None,
        playback_adapter: PlaybackAdapter | None = None,
        lyrics_adapter: LyricsAdapter | None = None,
        online_discovery: OnlineDiscoveryRuntime | None = None,
        force_dark_theme: bool = False,
        close_behavior_controller: CloseBehaviorController | None = None,
        startup_diagnostics: StartupDiagnostics | None = None,
    ) -> None:
        super().__init__(parent)
        self._startup_diagnostics = startup_diagnostics
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.data_mode = _resolve_data_mode(data_mode)
        self._force_dark_theme = bool(force_dark_theme)
        settings_override = os.environ.get("HUSHPLAYER_UI_V2_SETTINGS_PATH", "").strip()
        if settings_path is not None:
            resolved_settings_path = Path(settings_path)
        elif settings_override:
            resolved_settings_path = Path(settings_override)
        elif self.data_mode != "real":
            resolved_settings_path = (
                Path(tempfile.gettempdir())
                / "HushPlayer-ui-v2"
                / f"settings-{os.getpid()}.json"
            )
        else:
            resolved_settings_path = AppPaths.resolve().data_dir / "settings.json"
        self.update_service = AppUpdateService(self)
        self.update_service.updateAvailable.connect(self._on_update_available)
        self.update_service.noUpdate.connect(self._on_update_no_update)
        self.update_service.checkFailed.connect(self._on_update_check_failed)
        self.update_service.installerLaunched.connect(
            self._on_update_installer_launched
        )
        self.update_service.updaterLaunched.connect(
            self._on_update_installer_launched
        )
        settings_actions = {
            "check_updates": self._check_for_updates,
            "open_settings_path": self._open_settings_path,
        }
        if self.data_mode == "real":
            settings_actions.update(
                {
                    "scan_music_folders": self._scan_music_folders,
                    "clear_missing_cache": self._clear_missing_cache,
                    "open_audio_cache_directory": self._open_audio_cache_directory,
                    "clear_incomplete_audio_cache": self._clear_incomplete_audio_cache,
                    "clear_all_audio_cache": self._clear_all_audio_cache,
                }
            )
        self.settings_bridge = LegacySettingsBridge(
            settings_path=resolved_settings_path,
            apply_callback=self._apply_settings_snapshot,
            action_callbacks=settings_actions,
            parent=self,
        )
        self._settings_snapshot = self.settings_bridge.read_snapshot()
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("main_window.settings_snapshot")
        application = QApplication.instance()
        if application is None:
            raise RuntimeError("HushPlayer requires a QApplication before creating MainWindow.")
        self.close_behavior_controller = close_behavior_controller or CloseBehaviorController(
            application,
            resolved_settings_path,
            icon=application.windowIcon(),
            parent=application,
        )
        self.close_behavior_controller.register_window(self)
        self.close_behavior_controller.desktop_lyrics_unlock_requested.connect(
            self._unlock_desktop_lyrics_from_tray
        )
        self._user_close_requested = False
        self._close_finalized = False
        self._startup_scan_timer: QTimer | None = None
        self._real_library_projection_generation = 0
        self.desktop_lyrics_window: DesktopLyricsWindow | None = None
        self.desktop_lyrics_settings_popover: DesktopLyricsQuickSettingsPopover | None = None
        self._desktop_lyrics_settings_pending_snapshot: SettingsSnapshot | None = None
        self._desktop_lyrics_settings_preview_timer = QTimer(self)
        self._desktop_lyrics_settings_preview_timer.setSingleShot(True)
        self._desktop_lyrics_settings_preview_timer.setInterval(40)
        self._desktop_lyrics_settings_preview_timer.timeout.connect(
            self._apply_pending_desktop_lyrics_preview
        )
        self._desktop_lyrics_settings_save_timer = QTimer(self)
        self._desktop_lyrics_settings_save_timer.setSingleShot(True)
        self._desktop_lyrics_settings_save_timer.setInterval(250)
        self._desktop_lyrics_settings_save_timer.timeout.connect(
            self._save_pending_desktop_lyrics_settings
        )
        self._desktop_lyrics_auto_opened = False
        self._pending_import_status = ""
        appearance_mode = str(
            self.settings_bridge.value(self._settings_snapshot, "appearance_mode")
            or "dark"
        )
        self._theme = get_theme(
            "dark"
            if self._force_dark_theme or appearance_mode != "light"
            else "light"
        )
        self._theme_reveal_enabled = True
        self._animate_next_theme_change = False
        self._theme_reveal_overlay: ThemeRevealOverlay | None = None
        self._theme_apply_generation = 0
        self._theme_apply_phase = 0
        self._theme_apply_in_progress = False
        self._immersive_shell_active = False
        self._immersive_normal_geometry: QRect | None = None
        self._immersive_transparency_enabled = False
        self._presentation_mode = ShellPresentationMode.NORMAL
        self._normal_window_flags = self.windowFlags()
        self._transparent_frame_active = False
        self._transparent_normal_geometry: QRect | None = None
        self._resize_edges = Qt.Edge(0)
        self._resize_origin = QPoint()
        self._resize_geometry = QRect()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._immersive_transparency_supported = self.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        is_real_library = self.data_mode == "real"
        if is_real_library:
            resolved_paths = AppPaths.resolve()
            repository = repository or LibraryRepository(
                resolved_paths.data_dir / "library.json",
                resolved_paths.data_dir / "playlists.json",
                resolved_paths.data_dir / "stats.json",
            )
            remote_tracks = remote_tracks or RemoteTrackStore(
                resolved_paths.data_dir / "remote_tracks.json"
            )
            self.online_discovery = online_discovery or OnlineDiscoveryRuntime(
                resolved_paths,
                repository,
                remote_tracks,
                self,
            )
            if self.online_discovery.parent() is None:
                self.online_discovery.setParent(self)
            self.music_import_service = MusicFolderImportService(
                resolved_paths.data_dir / "library.json",
                resolved_paths.data_dir / "pending_imports.json",
                self,
            )
            self.music_import_service.completed.connect(self._on_music_import_completed)
        else:
            self.online_discovery = None
            self.music_import_service = None
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("main_window.service_graph")
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
        if self.online_discovery is not None:
            # Playlist CRUD writes through the one bridge that already owns
            # the formal playlists.json contract; the library projection stays
            # read-only and keeps its existing playback semantics.
            self.playlist_adapter.set_mutation_backend(self.online_discovery.bridge)
            self.library_collection.set_favorite_mutation_backend(
                self._persist_favorite_membership
            )
        self.online_adapter = OnlineAdapter(
            self.library_collection,
            self.playlist_adapter,
            self,
            discovery=self.online_discovery,
        )
        self.library_adapter = LibraryAdapter(collection=self.library_collection, parent=self)
        self.navigation_adapter = NavigationAdapter(
            self.playlist_adapter,
            self,
            include_online=True,
            include_pending=False,
        )
        self.playback_adapter = playback_adapter or PlaybackAdapter(self)
        if playback_adapter is not None and playback_adapter.parent() is None:
            playback_adapter.setParent(self)
        if self.online_discovery is not None and self.playback_adapter.controller is not None:
            self.playback_adapter.controller.set_online_resolver(
                self.online_discovery.playback_resolver
            )
            self.playback_adapter.controller.set_online_audio_cache(
                self.online_discovery.online_audio_cache,
                cache_allowed=self.online_discovery.online_source_allows_audio_cache,
            )
        self.lyrics_adapter = lyrics_adapter or LyricsAdapter(
            self,
            lyrics_service=(
                self.online_discovery.lyrics_service
                if is_real_library and self.online_discovery is not None
                else None
            ),
            lyrics_cache_dir=(
                self.online_discovery.paths.cache_dir / "lyrics"
                if is_real_library and self.online_discovery is not None
                else None
            ),
            lyrics_bindings_path=(
                self.online_discovery.paths.data_dir / "lyrics_bindings.json"
                if is_real_library and self.online_discovery is not None
                else None
            ),
        )
        if lyrics_adapter is not None and lyrics_adapter.parent() is None:
            lyrics_adapter.setParent(self)
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("main_window.adapters")
        self.immersive_lyrics_options = ImmersiveLyricsOptions(theme=self._theme.mode)
        self._apply_settings_values(self._settings_snapshot.to_dict())
        self.playback_adapter.set_volume(
            int(self.settings_bridge.value(self._settings_snapshot, "volume") or 65)
        )
        self.playback_adapter.set_queue(self.library_collection.tracks())
        self.library_page = AllSongsPage(self.library_adapter, self._theme, self)
        self.library_page.set_playback_enabled(
            not is_real_library or self.playback_adapter.has_real_backend
        )
        self.sidebar = NavigationSidebar(self.navigation_adapter, self._theme, self)
        self.router = ContentRouter(
            self.library_page,
            self.navigation_adapter,
            self.library_collection,
            self.playlist_adapter,
            self.online_adapter,
            self.lyrics_adapter,
            self.playback_adapter,
            self.immersive_lyrics_options,
            self._theme,
            self,
            settings_bridge=self.settings_bridge,
            settings_apply_callback=self._apply_settings_snapshot,
            pending_import_service=self.music_import_service,
        )
        self.player_bar = PlayerBar(self.playback_adapter, self._theme, self)
        self.player_bar.set_read_only(
            is_real_library,
            allow_playback=self.playback_adapter.has_real_backend,
            allow_favorite=self.library_collection.can_mutate_favorites,
        )
        self.real_library_adapter = (
            RealLibraryAdapter(
                self.library_collection,
                self.playlist_adapter,
                self,
                repository=repository,
                remote_tracks=remote_tracks,
            )
            if is_real_library
            else None
        )
        self._build_shell()
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("main_window.pages_and_player")
        self.settings_overlay: SettingsOverlay | None = None
        self._update_dialog: UpdateDialog | None = None
        self._pending_recovery_tracks: dict[int, Track] = {}
        self._track_info_dialog: TrackInfoDialog | None = None
        self._automatic_recovery_identities: set[str] = set()
        self._keyboard_focus_navigation = False
        QApplication.instance().installEventFilter(self)
        self._connect_state()
        self.setWindowTitle("HushPlayer UI V2")
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)
        self.set_theme(self._theme.mode)
        self._update_window_shape()
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("main_window.shell_ready")
        if self.real_library_adapter is not None:
            self.real_library_adapter.state_changed.connect(self._on_real_library_state)
            self.real_library_adapter.data_loaded.connect(self._on_real_library_loaded)
            self.library_page.empty_state.action_requested.connect(
                self._on_library_empty_action
            )
            # The snapshot work is already on a worker thread. Queue its
            # first start until the shell has had one event-loop turn so the
            # main window can paint before disk projection begins.
            # Use a second zero-timeout turn so the runner's first-paint
            # callback can run before even the worker thread is started.
            QTimer.singleShot(
                0,
                lambda: QTimer.singleShot(0, self._start_real_library_load),
            )
            if self._startup_diagnostics is not None:
                self._startup_diagnostics.mark("main_window.library_load_queued")
            self.online_adapter.remote_collection_changed.connect(
                self.real_library_adapter.refresh
            )
            if bool(
                self.settings_bridge.value(
                    self._settings_snapshot,
                    "auto_scan_music_folders_on_startup",
                )
            ):
                self._startup_scan_timer = QTimer(self)
                self._startup_scan_timer.setSingleShot(True)
                self._startup_scan_timer.setInterval(1_800)
                self._startup_scan_timer.timeout.connect(
                    self._auto_scan_music_folders_on_startup
                )
                self._startup_scan_timer.start()

    def _start_real_library_load(self) -> None:
        """Start the first library snapshot after the initial shell can paint."""

        if self._close_finalized or self.real_library_adapter is None:
            return
        self.real_library_adapter.load()

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def presentation_mode(self) -> ShellPresentationMode:
        return self._presentation_mode

    @property
    def immersive_shell(self):
        """Return the one cached immersive shell, when it has been created."""

        return self.router._pages.get("immersive_lyrics") if hasattr(self, "router") else None

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

    def set_theme(
        self,
        mode: str,
        *,
        reveal_overlay: ThemeRevealOverlay | None = None,
    ) -> None:
        target_theme = get_theme("light" if mode == "light" else "dark")
        animate = bool(
            reveal_overlay is not None
            or (
                self._animate_next_theme_change
                and self._theme_reveal_enabled
                and self.isVisible()
                and target_theme.mode != self._theme.mode
            )
        )
        if animate and reveal_overlay is None:
            reveal_overlay = self._prepare_theme_reveal()
        self._animate_next_theme_change = False
        self._theme_apply_generation += 1
        generation = self._theme_apply_generation
        self._theme_apply_in_progress = False
        if reveal_overlay is None and self._theme_reveal_overlay is not None:
            self._cancel_theme_reveal()

        self._theme = target_theme
        stylesheet = build_stylesheet(self._theme)
        if reveal_overlay is not None:
            try:
                self._apply_theme_global_styles_synchronously(
                    stylesheet,
                    application_scope=False,
                )
            except Exception:
                self._cancel_theme_reveal()
                raise
            if self._theme_reveal_overlay is not reveal_overlay:
                self._show_theme_reveal(reveal_overlay)
            self._theme_apply_in_progress = True
            self._theme_apply_phase = 0
            reveal_overlay.start_animation()
            QTimer.singleShot(
                0,
                lambda generation=generation, theme=self._theme: self._run_theme_apply_phase(
                    generation, theme
                ),
            )
            return
        self._apply_theme_synchronously(
            stylesheet,
            application_scope=not self.isVisible(),
        )

    def _apply_theme_global_styles(
        self,
        stylesheet: str,
        *,
        application_scope: bool,
    ) -> None:
        """Apply shared rules to the app at startup or to this shell at runtime."""

        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(build_application_palette(self._theme))
        if application_scope:
            app.setStyleSheet(stylesheet)
        else:
            self.setStyleSheet(stylesheet)
        app.setProperty("hushUiFlavor", "ui-v2")
        app.setProperty("hushUiV2ThemeMode", self._theme.mode)
        self._apply_root_stylesheet()

    def _apply_theme_global_styles_synchronously(
        self,
        stylesheet: str,
        *,
        application_scope: bool,
    ) -> None:
        """Apply global rules while suppressing the intermediate repaint."""

        was_enabled = self.updatesEnabled()
        root_was_enabled = self.root.updatesEnabled()
        self.setUpdatesEnabled(False)
        self.root.setUpdatesEnabled(False)
        try:
            self._apply_theme_global_styles(
                stylesheet,
                application_scope=application_scope,
            )
        finally:
            self.root.setUpdatesEnabled(root_was_enabled)
            self.setUpdatesEnabled(was_enabled)
            self.update()
            self.root.update()

    def _apply_theme_component_phase(self, phase: int, theme: Theme) -> None:
        """Apply one small UI group so animation frames can be processed between groups."""

        if phase == 0:
            self.title_bar.set_theme(theme)
        elif phase == 1:
            self.library_page.set_theme(theme)
        elif phase == 2:
            self.sidebar.set_theme(theme)
        elif phase == 3:
            self.router.set_theme(theme)
        elif phase == 4:
            self.player_bar.set_theme(theme)
        elif phase == 5:
            if self.desktop_lyrics_window is not None:
                self.desktop_lyrics_window.set_theme(theme)
            if self.desktop_lyrics_settings_popover is not None:
                self.desktop_lyrics_settings_popover.set_theme(theme)
            if self.settings_overlay is not None:
                self.settings_overlay.set_theme(theme)
            if self._track_info_dialog is not None:
                self._track_info_dialog.set_theme(theme)
            if self._update_dialog is not None:
                self._update_dialog.setStyleSheet(build_dialog_stylesheet(theme))
            self.router.set_content_safe_bottom(
                theme.metrics.player_bar_height + theme.metrics.content_safe_bottom
            )
            if not self._immersive_transparency_enabled:
                self._shell_surface_states = tuple(
                    (widget, QPalette(widget.palette()), widget.autoFillBackground())
                    for widget in (self.root, self.body, self.content_container, self.router)
                )

    def _apply_theme_synchronously(
        self,
        stylesheet: str,
        *,
        application_scope: bool,
    ) -> None:
        """Apply all theme layers in one pass for startup and non-animated changes."""

        was_enabled = self.updatesEnabled()
        root_was_enabled = self.root.updatesEnabled()
        self.setUpdatesEnabled(False)
        self.root.setUpdatesEnabled(False)
        try:
            self._apply_theme_global_styles(
                stylesheet,
                application_scope=application_scope,
            )
            for phase in range(6):
                self._apply_theme_component_phase(phase, self._theme)
        finally:
            self.root.setUpdatesEnabled(root_was_enabled)
            self.setUpdatesEnabled(was_enabled)
            self.update()
            self.root.update()

    def _run_theme_apply_phase(self, generation: int, theme: Theme) -> None:
        if (
            generation != self._theme_apply_generation
            or not self._theme_apply_in_progress
            or self._close_finalized
        ):
            return
        phase = self._theme_apply_phase
        was_enabled = self.updatesEnabled()
        root_was_enabled = self.root.updatesEnabled()
        self.setUpdatesEnabled(False)
        self.root.setUpdatesEnabled(False)
        try:
            self._apply_theme_component_phase(phase, theme)
        except Exception as error:
            self._theme_apply_in_progress = False
            self._cancel_theme_reveal()
            QToolTip.showText(
                self.title_bar.theme_button.mapToGlobal(
                    self.title_bar.theme_button.rect().bottomLeft()
                ),
                f"主题切换失败：{error}",
                self.title_bar.theme_button,
            )
            return
        finally:
            self.root.setUpdatesEnabled(root_was_enabled)
            self.setUpdatesEnabled(was_enabled)
            self.update()
            self.root.update()
        self._theme_apply_phase += 1
        if self._theme_apply_phase < 6:
            QTimer.singleShot(
                0,
                lambda generation=generation, theme=theme: self._run_theme_apply_phase(
                    generation, theme
                ),
            )
        else:
            self._theme_apply_in_progress = False

    def toggle_theme(self) -> None:
        """Persist an explicit Light/Dark choice through the existing bridge."""

        target = "light" if self._theme.mode == "dark" else "dark"
        self._animate_next_theme_change = self._theme_reveal_enabled
        if self.settings_overlay is not None and self.settings_overlay.isVisible():
            try:
                self.settings_overlay.set_appearance_mode(target)
            except Exception:
                self._animate_next_theme_change = False
                raise
            return
        snapshot = self._settings_snapshot.with_updates({"appearance_mode": target})
        if self._queue_theme_reveal_apply(snapshot):
            return
        try:
            saved = self.settings_bridge.save_snapshot(snapshot)
        except Exception:
            self._animate_next_theme_change = False
            raise
        self._settings_snapshot = saved

    def _queue_theme_reveal_apply(self, snapshot: SettingsSnapshot) -> bool:
        """Start the reveal before synchronous theme persistence runs."""

        if not (
            self._theme_reveal_enabled
            and self.isVisible()
            and self._theme_reveal_overlay is None
        ):
            return False
        overlay = self._prepare_theme_reveal()
        if overlay is None:
            return False
        self._animate_next_theme_change = False
        self._show_theme_reveal(overlay)
        # Start the animation before the queued settings write and theme
        # polish. The first event-loop turn can now observe a running
        # transition instead of waiting for the synchronous style refresh.
        overlay.start_animation()
        QTimer.singleShot(
            self._THEME_REVEAL_APPLY_DELAY_MS,
            lambda snapshot=snapshot: self._apply_queued_theme_snapshot(snapshot),
        )
        return True

    def _apply_queued_theme_snapshot(self, snapshot: SettingsSnapshot) -> None:
        try:
            overlay = self._theme_reveal_overlay
            if overlay is None:
                return
            saved = self.settings_bridge.save_snapshot(snapshot, apply=False)
            self._settings_snapshot = saved
            self._apply_settings_snapshot(
                saved.to_dict(),
                theme_reveal_overlay=overlay,
            )
        except Exception as error:
            self._animate_next_theme_change = False
            self._cancel_theme_reveal()
            QToolTip.showText(
                self.title_bar.theme_button.mapToGlobal(
                    self.title_bar.theme_button.rect().bottomLeft()
                ),
                f"主题切换失败：{error}",
                self.title_bar.theme_button,
            )

    def _cancel_theme_reveal(self) -> None:
        self._theme_apply_generation += 1
        self._theme_apply_in_progress = False
        overlay = self._theme_reveal_overlay
        self._theme_reveal_overlay = None
        if overlay is not None:
            overlay._animation.stop()
            overlay.hide()
            overlay.deleteLater()
        self.title_bar.theme_button.setEnabled(True)

    def _prepare_theme_reveal(self) -> ThemeRevealOverlay | None:
        if self._theme_reveal_overlay is not None:
            self._theme_reveal_overlay.deleteLater()
            self._theme_reveal_overlay = None
        snapshot = self.grab()
        if snapshot.isNull():
            return None
        theme_button = self.title_bar.theme_button
        origin = theme_button.mapTo(self, theme_button.rect().center())
        return ThemeRevealOverlay(snapshot, origin, self)

    def _show_theme_reveal(self, overlay: ThemeRevealOverlay) -> None:
        self._attach_theme_reveal(overlay)
        overlay.show_ready()

    def _attach_theme_reveal(self, overlay: ThemeRevealOverlay) -> None:
        self._theme_reveal_overlay = overlay
        overlay.finished.connect(self._on_theme_reveal_finished)
        self.title_bar.theme_button.setEnabled(False)

    def _on_theme_reveal_finished(self) -> None:
        self._theme_reveal_overlay = None
        self.title_bar.theme_button.setEnabled(True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # The centered transport rail needs its compact width before the
        # window becomes visibly crowded. Keep the favorite action and
        # utility controls inside their own regions at common 1024px widths.
        compact = self.width() <= 1080
        self.sidebar.set_compact(compact)
        self.player_bar.set_compact(compact)
        self.title_bar.set_compact(compact)
        self.library_page.track_table.set_responsive_reference_width(self.width())
        self.router.set_responsive_reference_width(self.width())
        if self.settings_overlay is not None:
            self.settings_overlay.set_responsive_reference_width(self.width())
            self.settings_overlay.sync_geometry(self.body.rect())
        self._update_window_shape()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._desktop_lyrics_auto_opened:
            return
        self._desktop_lyrics_auto_opened = True
        if bool(
            self.settings_bridge.value(
                self._settings_snapshot,
                "floating_lyrics_auto_open",
            )
        ):
            QTimer.singleShot(
                0,
                lambda: QTimer.singleShot(0, self._show_desktop_lyrics),
            )

    def _update_window_shape(self) -> None:
        """Clip the normal window to a rounded shell while preserving full-screen geometry."""

        if QGuiApplication.platformName().lower() in {"offscreen", "minimal"}:
            return
        rounded = not self.isMaximized() and not self.isFullScreen()
        if self.width() <= 0 or self.height() <= 0:
            return
        if self._set_windows_corner_preference(rounded):
            self.clearMask()
            return
        if not rounded:
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect()),
            self._WINDOW_CORNER_RADIUS,
            self._WINDOW_CORNER_RADIUS,
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _set_windows_corner_preference(self, rounded: bool) -> bool:
        """Ask Windows 11/DWM for an antialiased corner treatment when available."""

        if os.name != "nt":
            return False
        try:
            preference = ctypes.c_int(
                _DWMWCP_ROUND if rounded else _DWMWCP_DEFAULT
            )
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()),
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except (AttributeError, OSError, TypeError, ValueError):
            return False
        return int(result) == 0

    def request_user_close(self) -> None:
        """Route the custom title-bar X through the close behavior controller."""

        if self._close_finalized:
            return
        self._user_close_requested = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._user_close_requested:
            self._user_close_requested = False
            if not self.close_behavior_controller.handle_close(self, event):
                return
        self._finalize_close()
        super().closeEvent(event)

    def _finalize_close(self) -> None:
        if self._close_finalized:
            return
        if self._desktop_lyrics_settings_pending_snapshot is not None:
            self._desktop_lyrics_settings_preview_timer.stop()
            self._desktop_lyrics_settings_save_timer.stop()
            self._save_pending_desktop_lyrics_settings()
        self._close_finalized = True
        QApplication.instance().removeEventFilter(self)
        if self.desktop_lyrics_settings_popover is not None:
            self.desktop_lyrics_settings_popover.hide()
        if self.settings_overlay is not None and self.settings_overlay.isVisible():
            self.settings_overlay.cancel_and_close()
        if self.desktop_lyrics_window is not None:
            self.desktop_lyrics_window.close()
        if self.real_library_adapter is not None:
            self.real_library_adapter.shutdown()
        if self._startup_scan_timer is not None:
            self._startup_scan_timer.stop()
        if self.music_import_service is not None:
            self.music_import_service.shutdown()
        browse_page = getattr(self.router, "browse_page", None)
        if browse_page is not None and hasattr(browse_page, "shutdown"):
            browse_page.shutdown()
        self.online_adapter.shutdown()
        if self.online_discovery is not None:
            self.online_discovery.shutdown()
        self.update_service.shutdown()
        immersive_page = self.router._pages.get("immersive_lyrics")
        if immersive_page is not None and hasattr(immersive_page, "shutdown"):
            immersive_page.shutdown()
        controller = self.playback_adapter.controller
        if controller is not None:
            controller.shutdown()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Provide native-feeling edge resizing for the frameless approved shell."""

        if isinstance(watched, QAbstractButton):
            if event.type() == QEvent.Type.MouseButtonPress:
                self._keyboard_focus_navigation = False
                self._set_button_keyboard_focus(watched, False)
            elif event.type() == QEvent.Type.KeyPress:
                if event.key() in {
                    Qt.Key.Key_Tab,
                    Qt.Key.Key_Backtab,
                }:
                    self._keyboard_focus_navigation = True
            elif event.type() == QEvent.Type.FocusIn:
                self._set_button_keyboard_focus(
                    watched,
                    self._keyboard_focus_navigation,
                )

        if event.type() == QEvent.Type.KeyPress and self._handle_immersive_key_event(event):
            return True
        if not isinstance(event, QMouseEvent) or self.isMaximized() or self.isFullScreen():
            return super().eventFilter(watched, event)
        if not isinstance(watched, QWidget) or watched.window() is not self:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            edges = self._resize_edges_for(event.globalPosition().toPoint())
            if edges:
                self._resize_edges = edges
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geometry = QRect(self.geometry())
                event.accept()
                return True
        elif event.type() == QEvent.Type.MouseMove:
            if self._resize_edges:
                self._resize_from_pointer(event.globalPosition().toPoint())
                event.accept()
                return True
            self.setCursor(self._cursor_for_edges(self._resize_edges_for(event.globalPosition().toPoint())))
        elif event.type() == QEvent.Type.MouseButtonRelease and self._resize_edges:
            self._resize_edges = Qt.Edge(0)
            self.unsetCursor()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _set_button_keyboard_focus(button: QAbstractButton, visible: bool) -> None:
        value = "true" if visible else "false"
        if button.property("hushKeyboardFocus") == value:
            return
        button.setProperty("hushKeyboardFocus", value)
        style = button.style()
        style.unpolish(button)
        style.polish(button)
        button.update()

    def _handle_immersive_key_event(self, event) -> bool:
        """Handle unmodified immersive controls only while this window is foreground."""

        if self._presentation_mode is ShellPresentationMode.NORMAL:
            return False
        application = QApplication.instance()
        if application is None:
            return False
        platform = QGuiApplication.platformName().lower()
        if platform not in {"offscreen", "minimal"}:
            if not self.isActiveWindow() or application.activeWindow() is not self:
                return False
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        page = self.router._pages.get("immersive_lyrics")
        if page is None:
            return False
        key = event.key()
        if key == Qt.Key.Key_Escape:
            page.handle_escape()
            event.accept()
            return True
        if page.settings_panel.isVisible() or page.queue_panel.isVisible():
            return False
        if isinstance(application.focusWidget(), QAbstractSlider):
            return False
        if key == Qt.Key.Key_Space:
            self.playback_adapter.toggle_playback()
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            delta = 5 if key == Qt.Key.Key_Up else -5
            self.playback_adapter.set_volume(
                self.playback_adapter.state.volume + delta
            )
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            delta = -5_000 if key == Qt.Key.Key_Left else 5_000
            state = self.playback_adapter.state
            self.playback_adapter.seek(state.position_ms + delta)
        else:
            return False
        event.accept()
        return True

    def _resize_edges_for(self, global_position: QPoint) -> Qt.Edge:
        frame = self.frameGeometry()
        margin = 6
        edges = Qt.Edge(0)
        if abs(global_position.x() - frame.left()) <= margin:
            edges |= Qt.Edge.LeftEdge
        elif abs(global_position.x() - frame.right()) <= margin:
            edges |= Qt.Edge.RightEdge
        if abs(global_position.y() - frame.top()) <= margin:
            edges |= Qt.Edge.TopEdge
        elif abs(global_position.y() - frame.bottom()) <= margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for_edges(edges: Qt.Edge) -> Qt.CursorShape:
        if edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        if edges in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeVerCursor
        if edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeFDiagCursor
        if edges:
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def _resize_from_pointer(self, global_position: QPoint) -> None:
        delta = global_position - self._resize_origin
        geometry = QRect(self._resize_geometry)
        if self._resize_edges & Qt.Edge.LeftEdge:
            geometry.setLeft(min(geometry.right() - self.minimumWidth() + 1, geometry.left() + delta.x()))
        if self._resize_edges & Qt.Edge.RightEdge:
            geometry.setRight(max(geometry.left() + self.minimumWidth() - 1, geometry.right() + delta.x()))
        if self._resize_edges & Qt.Edge.TopEdge:
            geometry.setTop(min(geometry.bottom() - self.minimumHeight() + 1, geometry.top() + delta.y()))
        if self._resize_edges & Qt.Edge.BottomEdge:
            geometry.setBottom(max(geometry.top() + self.minimumHeight() - 1, geometry.bottom() + delta.y()))
        self.setGeometry(geometry)

    def _build_shell(self) -> None:
        self.root = QWidget(self)
        self.root.setObjectName("uiV2Root")
        self.title_bar = CustomTitleBar(self._theme, self.root)
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
        self._root_layout.addWidget(self.title_bar)
        self._root_layout.addWidget(self.body, 1)
        self._root_layout.addWidget(self.player_bar_container)
        self.setCentralWidget(self.root)
        self.router.set_content_safe_bottom(
            self._theme.metrics.player_bar_height + self._theme.metrics.content_safe_bottom
        )
        self._shell_surface_states = tuple(
            (widget, QPalette(widget.palette()), widget.autoFillBackground())
            for widget in (self.root, self.body, self.content_container, self.router)
        )

    def _connect_state(self) -> None:
        self.library_page.theme_changed.connect(self.set_theme)
        self.title_bar.search_text_changed.connect(self.router.set_global_query)
        self.title_bar.search_submitted.connect(self._submit_global_query)
        self.title_bar.back_requested.connect(self.navigation_adapter.go_back)
        self.title_bar.forward_requested.connect(self.navigation_adapter.go_forward)
        self.title_bar.settings_requested.connect(self.open_settings_overlay)
        self.title_bar.theme_toggle_requested.connect(self.toggle_theme)
        self.sidebar.settings_requested.connect(self.open_settings_overlay)
        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        self.settings_shortcut.activated.connect(self.open_settings_overlay)
        self.desktop_lyrics_shortcut = QShortcut(QKeySequence("Ctrl+Alt+L"), self)
        self.desktop_lyrics_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.desktop_lyrics_shortcut.activated.connect(self._toggle_desktop_lyrics)
        self.previous_track_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Left"), self)
        self.previous_track_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.previous_track_shortcut.activated.connect(self.playback_adapter.play_previous)
        self.play_pause_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Space"), self)
        self.play_pause_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.play_pause_shortcut.activated.connect(self.playback_adapter.toggle_playback)
        self.next_track_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Right"), self)
        self.next_track_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.next_track_shortcut.activated.connect(self.playback_adapter.play_next)
        self.navigation_adapter.history_changed.connect(
            self.title_bar.set_navigation_state
        )
        self.title_bar.set_navigation_state(
            self.navigation_adapter.can_go_back,
            self.navigation_adapter.can_go_forward,
        )
        self.router.track_play_requested.connect(self._play_tracks)
        self.router.track_action_requested.connect(self._on_track_action)
        self.router.track_browse_requested.connect(
            lambda track_id: self._on_track_action("show_info", track_id)
        )
        self.router.queue_requested.connect(self._play_queue)
        self.router.online_play_requested.connect(self._play_online_track)
        self.router.online_recovery_requested.connect(self._request_online_recovery)
        self.router.pending_import_requested.connect(self._import_pending_paths)
        self.router.pending_ignore_requested.connect(self._ignore_pending_paths)
        self.router.pending_open_folder_requested.connect(self._open_pending_folder)
        self.router.immersive_fullscreen_requested.connect(
            self.set_immersive_fullscreen
        )
        self.router.immersive_transparency_requested.connect(
            self.set_immersive_transparency
        )
        self.navigation_adapter.route_changed.connect(self._sync_immersive_shell)
        self.navigation_adapter.route_changed.connect(self._sync_search_context)
        self.playback_adapter.track_changed.connect(self._on_playback_track_changed)
        self.playback_adapter.playing_changed.connect(self.router.set_playback_state)
        self.playback_adapter.playback_status_changed.connect(
            self.lyrics_adapter.set_playback_status
        )
        self.playback_adapter.remote_track_state_changed.connect(
            self._on_remote_track_state_changed
        )
        self.playback_adapter.duration_changed.connect(
            self._on_playback_duration_changed
        )
        # Lyrics parsing and online lyric requests must not delay the media
        # switch during previous/next.  Let the controller start the new
        # source first, then refresh the shared lyric surface in the event loop.
        self.playback_adapter.track_changed.connect(
            self.lyrics_adapter.set_track,
            (
                Qt.ConnectionType.DirectConnection
                if self.data_mode == "mock"
                else Qt.ConnectionType.QueuedConnection
            ),
        )
        self.playback_adapter.position_changed.connect(self.lyrics_adapter.set_position)
        self.lyrics_adapter.set_track(self.playback_adapter.state.current_track)
        self.lyrics_adapter.set_playback_status(
            self.playback_adapter.state.status,
            self.playback_adapter.state.status_detail,
        )
        self.lyrics_adapter.seek_requested.connect(self.playback_adapter.seek)
        self.player_bar.mock_action_requested.connect(self._on_player_bar_action)
        self.player_bar.track_open_requested.connect(self._open_now_playing)
        self.player_bar.desktop_lyrics_settings_requested.connect(
            self._toggle_desktop_lyrics_quick_settings
        )
        self.library_collection.track_updated.connect(self.playback_adapter.update_track)
        if self.online_adapter.is_formal:
            self.online_adapter.track_updated.connect(self.playback_adapter.update_track)
        if self.online_discovery is not None:
            self.online_discovery.artwork_service.imageReady.connect(
                self._on_online_artwork_ready
            )
            recovery = getattr(self.online_discovery, "track_recovery", None)
            if recovery is not None:
                recovery.status_changed.connect(self._on_recovery_status)
                recovery.match_found.connect(self._on_recovery_match)
                recovery.candidates_found.connect(self._on_recovery_candidates)
                recovery.failed.connect(self._on_recovery_failed)
        self.library_collection.favorite_changed.connect(self._sync_favorite_from_library)
        self.playback_adapter.favorite_changed.connect(self._sync_favorite_from_player)
        self._sync_immersive_shell(self.navigation_adapter.route)
        self._sync_search_context(self.navigation_adapter.route)

    def _submit_global_query(self, text: str) -> None:
        """Submit the shell query through the one online-search route."""

        query = str(text or "").strip()
        if not query:
            return
        if self.navigation_adapter.route != "online_search":
            self.navigation_adapter.set_route("online_search")
        self.router.set_global_query(query)
        self.online_adapter.search()

    def _sync_search_context(self, route_id: str) -> None:
        """Keep the one shell search field clear about its current scope."""

        self.title_bar.set_search_context(route_id)

    def open_settings_overlay(self, category: str | None = None) -> None:
        """Show the one cached Settings surface without changing the route."""

        if category:
            # The request can originate from the always-on-top desktop lyrics
            # window while the main shell is behind another application.
            self.show()
            self.raise_()
            self.activateWindow()
        immersive_page = self.router._pages.get("immersive_lyrics")
        if self._presentation_mode is not ShellPresentationMode.NORMAL and immersive_page is not None:
            if hasattr(immersive_page, "hide_settings_panel"):
                immersive_page.hide_settings_panel()
        if self.settings_overlay is None:
            self.settings_overlay = SettingsOverlay(
                self.settings_bridge,
                self._theme,
                online_sources=self.router._online_sources,
                pending_import_service=self.music_import_service,
                preview_callback=self._apply_settings_snapshot,
                parent=self.body,
            )
            self.settings_overlay.saved.connect(self._on_settings_saved)
            self.settings_overlay.pending_import_requested.connect(
                self._import_pending_paths
            )
            self.settings_overlay.pending_ignore_requested.connect(
                self._ignore_pending_paths
            )
            self.settings_overlay.pending_open_folder_requested.connect(
                self._open_pending_folder
            )
            if self._pending_import_status:
                self.settings_overlay.pending_imports_page.set_status(
                    self._pending_import_status
                )
        elif self.settings_overlay.isVisible():
            if category:
                self.settings_overlay.set_category(category)
            self.settings_overlay.raise_()
            return
        self.settings_overlay.open()
        if category:
            self.settings_overlay.set_category(category)
        self.settings_overlay.raise_()

    def _set_update_status(self, message: str, *, state: str = "success") -> None:
        """Reflect asynchronous update service feedback in the settings surface."""

        if self.settings_overlay is not None:
            self.settings_overlay.set_update_status(message, state=state)

    def _check_for_updates(self) -> str:
        """Start a manual update check from the Quiet Orbit settings surface."""

        if not self.update_service.check_for_updates(manual=True):
            return "当前已有更新检查或下载正在进行。"
        return "正在检查更新…"

    def _on_update_available(self, manifest: object, _manual: bool) -> None:
        if not isinstance(manifest, UpdateManifest):
            return
        self._set_update_status(f"发现新版本 {manifest.version}。")
        dialog = UpdateDialog(self.update_service, manifest, self)
        self._update_dialog = dialog
        dialog.exec()
        if self._update_dialog is dialog:
            self._update_dialog = None

    def _on_update_no_update(self, _manual: bool) -> None:
        self._set_update_status(f"当前已是最新版本（{APP_VERSION}）。")

    def _on_update_check_failed(self, message: str, _manual: bool) -> None:
        self._set_update_status(message, state="failed")

    def _on_update_installer_launched(self, _path: str) -> None:
        # The update dialog runs a nested event loop.  Closing only the main
        # window leaves that modal loop alive, so the updater still sees the
        # HushPlayer process holding files in the install directory.
        dialog = getattr(self, "_update_dialog", None)
        if dialog is not None:
            dialog.done(QDialog.DialogCode.Accepted)
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _on_settings_saved(self, snapshot: SettingsSnapshot) -> None:
        """Keep the shell's last persisted snapshot in sync with the overlay."""

        self._settings_snapshot = SettingsSnapshot.from_mapping(snapshot.to_dict())

    @staticmethod
    def _open_settings_path(path: str) -> bool:
        candidate = Path(str(path or "").strip()).expanduser()
        if not candidate.exists():
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate.resolve()))))

    def _scan_music_folders(self) -> str:
        service = self.music_import_service
        if service is None:
            return "当前运行模式不支持真实音乐库扫描。"
        folders = self.settings_bridge.value(self._settings_snapshot, "music_scan_folders") or []
        folders = [str(folder).strip() for folder in folders if str(folder).strip()]
        if not folders:
            return "请先在设置中添加音乐文件夹。"
        mode = str(
            self.settings_bridge.value(self._settings_snapshot, "music_scan_import_mode")
            or "pending"
        )
        if not service.start(folders, import_mode=mode):
            return "已有音乐扫描任务正在运行。"
        return "正在扫描音乐文件夹…"

    def _auto_scan_music_folders_on_startup(self) -> None:
        if self.data_mode == "real":
            self._scan_music_folders()

    def _on_music_import_completed(self, result: object) -> None:
        if not isinstance(result, dict):
            return
        added = int(result.get("added_count", 0) or 0)
        pending = int(result.get("pending_count", 0) or 0)
        if self.settings_overlay is not None:
            self.settings_overlay.set_update_status(
                f"扫描完成：加入音乐库 {added} 首，待确认 {pending} 首。"
            )
        self._show_pending_status(
            f"扫描完成：加入音乐库 {added} 首，待确认 {pending} 首。"
        )
        if self.real_library_adapter is not None and added:
            self.real_library_adapter.refresh()

    def _pending_page(self):
        if self.settings_overlay is not None:
            page = getattr(self.settings_overlay, "pending_imports_page", None)
            if page is not None:
                return page
        return self.router._pages.get("pending_imports")

    def _show_pending_status(self, text: str) -> None:
        self._pending_import_status = str(text or "")
        page = self._pending_page()
        if page is not None and hasattr(page, "set_status"):
            page.set_status(self._pending_import_status)

    def _import_pending_paths(self, paths: object) -> None:
        service = self.music_import_service
        if service is None or not isinstance(paths, (list, tuple)):
            return
        result = service.import_pending(str(path) for path in paths)
        if result.get("ok") and int(result.get("imported", 0) or 0):
            if self.real_library_adapter is not None:
                self.real_library_adapter.refresh()
        if result.get("ok"):
            self._show_pending_status(
                f"已加入音乐库 {int(result.get('imported', 0) or 0)} 首。"
            )
        else:
            self._show_pending_status(str(result.get("error") or "加入音乐库失败。"))

    def _ignore_pending_paths(self, paths: object) -> None:
        service = self.music_import_service
        if service is None or not isinstance(paths, (list, tuple)):
            return
        clean_paths = [str(path) for path in paths if str(path).strip()]
        if not clean_paths:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("忽略待导入歌曲")
        dialog.setText(f"确定要忽略选中的 {len(clean_paths)} 首歌曲吗？")
        dialog.setInformativeText("忽略只会从待导入列表移除，不会删除本地音频文件。")
        confirm = dialog.addButton("继续忽略", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is not confirm:
            return
        result = service.ignore_pending(clean_paths)
        if result.get("ok"):
            self._show_pending_status(
                f"已忽略 {int(result.get('ignored', 0) or 0)} 首歌曲。"
            )
        else:
            self._show_pending_status(str(result.get("error") or "忽略歌曲失败。"))

    def _open_pending_folder(self, path: str) -> bool:
        candidate = Path(str(path or "")).expanduser()
        if not candidate.is_dir():
            candidate = candidate.parent
        if not candidate:
            return False
        return self._open_settings_path(str(candidate))

    def _open_audio_cache_directory(self) -> bool:
        discovery = self.online_discovery
        if discovery is None:
            return False
        return self._open_settings_path(str(discovery.online_audio_cache.cache_root))

    def _clear_missing_cache(self) -> dict[str, object]:
        paths = AppPaths.resolve()
        return clear_missing_cache_files(
            (paths.cache_dir / "covers", paths.cache_dir / "lyrics")
        )

    def _protected_online_audio_cache_key(self) -> str:
        controller = self.playback_adapter.controller
        if controller is None:
            return ""
        return str(getattr(controller, "online_cache_key", "") or "")

    def _clear_incomplete_audio_cache(self) -> dict:
        discovery = self.online_discovery
        if discovery is None:
            return {"removed": 0, "skipped": 0, "bytes": 0}
        return discovery.online_audio_cache.clear_incomplete(
            protected_cache_key=self._protected_online_audio_cache_key()
        )

    def _clear_all_audio_cache(self) -> dict:
        discovery = self.online_discovery
        if discovery is None:
            return {"removed": 0, "skipped": 0, "bytes": 0}
        return discovery.online_audio_cache.clear_all(
            protected_cache_key=self._protected_online_audio_cache_key()
        )

    def _apply_settings_values(self, values: dict[str, object]) -> None:
        """Apply persisted settings to the small set of V2 runtime models."""

        appearance = str(values.get("appearance_mode", "dark"))
        resolved_appearance = "dark" if self._force_dark_theme else appearance
        self.immersive_lyrics_options.theme = (
            "light" if resolved_appearance == "light" else "dark"
        )
        background = normalize_immersive_background_visual_mode(
            values.get("immersive_background_visual_mode"),
            values.get("immersive_background_mode", "cover"),
        )
        self.immersive_lyrics_options.background_mode = background
        self.immersive_lyrics_options.controls_auto_hide = bool(
            values.get("immersive_auto_hide_ui", True)
        )
        try:
            self.immersive_lyrics_options.global_font_scale = max(
                75, min(160, int(values.get("immersive_lyrics_font_scale", 100)))
            )
        except (TypeError, ValueError):
            self.immersive_lyrics_options.global_font_scale = 100
        for attribute, key, default, low, high in (
            ("background_blur", "immersive_background_blur", 40, 0, 100),
            ("background_darkness", "immersive_background_darkness", 68, 0, 100),
            ("background_image_opacity", "immersive_background_image_opacity", 100, 0, 100),
            ("background_transparency", "immersive_background_transparency", 38, 0, 100),
        ):
            try:
                value = max(low, min(high, int(values.get(key, default))))
            except (TypeError, ValueError):
                value = default
            setattr(self.immersive_lyrics_options, attribute, value)
            if attribute == "background_image_opacity":
                self.immersive_lyrics_options.background_opacity = value
        self.immersive_lyrics_options.background_custom_path = str(
            values.get("immersive_background_custom_path", "") or ""
        )
        if self.desktop_lyrics_window is not None:
            self.desktop_lyrics_window.apply_settings(values)

    def _apply_settings_snapshot(
        self,
        values: dict[str, object],
        *,
        theme_reveal_overlay: ThemeRevealOverlay | None = None,
    ) -> None:
        """Preview or apply a Settings snapshot without creating another shell."""

        self._apply_settings_values(values)
        try:
            self.playback_adapter.set_volume(int(values.get("volume", 65) or 65))
        except (TypeError, ValueError):
            self.playback_adapter.set_volume(65)
        mode = str(values.get("appearance_mode", "dark"))
        self.set_theme(
            "dark" if self._force_dark_theme or mode != "light" else "light",
            reveal_overlay=theme_reveal_overlay,
        )
        page = self.router._pages.get("immersive_lyrics")
        if page is not None and hasattr(page, "apply_options"):
            page.apply_options(self.immersive_lyrics_options)

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
        immersive = route_id in {"immersive_lyrics", "immersive_now_playing"}
        if immersive == self._immersive_shell_active:
            return
        self._immersive_shell_active = immersive
        if immersive:
            page = self.router._pages.get("immersive_lyrics")
            if page is not None and hasattr(page, "set_read_only"):
                page.set_read_only(self.real_library_adapter is not None)
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
        self.title_bar.setVisible(not immersive)
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
        self._update_window_shape()

    def _apply_root_stylesheet(self) -> None:
        """Apply only root-specific rules; shared rules already live on QApplication."""

        stylesheet = (
            f"QWidget#uiV2Root {{ background: {self._theme.colors.app_background}; "
            f"color: {self._theme.colors.text_primary}; "
            f"border: 1px solid {self._theme.colors.divider}; "
            f"border-radius: {self._WINDOW_CORNER_RADIUS}px; }}"
        )
        if self._immersive_transparency_enabled and self._immersive_transparency_supported:
            stylesheet += (
                "\nQWidget#uiV2Root, QWidget#uiV2Body, QWidget#uiV2ContentContainer, "
                "QStackedWidget#uiV2ContentRouter { background: transparent; }\n"
            )
        self.root.setStyleSheet(stylesheet)

    def _play_tracks(self, tracks, track_id: str) -> None:
        allow_remote = self.playback_adapter.has_real_backend
        available = tuple(
            track
            for track in tracks
            if not track.is_missing or (allow_remote and track.is_online)
        )
        if not available:
            return
        self.playback_adapter.set_queue(available)
        self.playback_adapter.play_track(track_id)

    def _play_queue(self, tracks, shuffle: bool) -> None:
        allow_remote = self.playback_adapter.has_real_backend
        available = tuple(
            track
            for track in tracks
            if not track.is_missing or (allow_remote and track.is_online)
        )
        if not available:
            return
        self.playback_adapter.set_queue(available)
        if self.playback_adapter.state.shuffle_enabled != shuffle:
            self.playback_adapter.toggle_shuffle()
        self.playback_adapter.play_track(available[0].id)

    def _play_online_track(self, track) -> None:
        # The next play_item call replaces the old media synchronously. Keep
        # the new queue alive long enough for that call to reach the controller.
        self.playback_adapter.set_queue(
            (track,),
            preserve_current_context=True,
        )
        self.playback_adapter.play_track(track.id)

    def _on_track_action(self, action: str, track_id: str) -> None:
        """Handle lightweight track actions without touching playback context."""

        track = self.library_collection.track_for_id(str(track_id or ""))
        if track is None:
            return
        if action == "show_info":
            dialog = self._track_info_dialog
            if dialog is None:
                dialog = TrackInfoDialog(self._theme, track, self)
                dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                dialog.destroyed.connect(
                    lambda _object=None: setattr(self, "_track_info_dialog", None)
                )
                self._track_info_dialog = dialog
            else:
                dialog.set_track(track)
                dialog.set_theme(self._theme)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        if action != "add_to_playlist":
            return
        if not self.playlist_adapter.can_mutate:
            self._show_action_message("当前运行模式不支持修改歌单。")
            return
        dialog = PlaylistSelectionDialog(self._theme, self.playlist_adapter.playlists(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        playlist_id = dialog.selected_playlist_id
        if not playlist_id:
            return
        added = self.playlist_adapter.add_tracks(playlist_id, (track.id,))
        playlist = self.playlist_adapter.playlist_for_id(playlist_id)
        playlist_name = playlist.name if playlist is not None else "歌单"
        if added:
            self._show_action_message(f"已添加到歌单：{playlist_name}")
        else:
            self._show_action_message("歌曲已经在该歌单中，未重复添加。")

    @property
    def recovery_status_message(self) -> str:
        return getattr(self, "_recovery_status_message", "")

    def _request_online_recovery(self, track) -> None:
        recovery = getattr(self.online_discovery, "track_recovery", None)
        if recovery is None:
            self._show_recovery_message("当前运行模式没有可用的在线恢复服务。")
            return
        if isinstance(track, Track) and track.stable_identity:
            # Manual recovery also counts as the one automatic attempt for
            # this playback context, preventing a failed replacement from
            # starting an endless recovery loop.
            self._automatic_recovery_identities.add(track.stable_identity)
        generation = recovery.request(track)
        if isinstance(track, Track):
            self._pending_recovery_tracks[int(generation)] = track

    def _on_recovery_status(self, _generation: int, message: str) -> None:
        self._show_recovery_message(str(message or ""))

    def _on_recovery_match(self, generation: int, track) -> None:
        source = self._pending_recovery_tracks.pop(int(generation), None)
        self._play_recovery_candidate(source, track)

    def _on_recovery_candidates(self, generation: int, candidates) -> None:
        values = tuple(candidates or ())
        source = self._pending_recovery_tracks.pop(int(generation), None)
        if not values:
            self._show_recovery_message("没有找到可靠的在线版本。")
            return
        dialog = OnlineRecoveryCandidateDialog(values, self._theme, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_track is not None:
            self._play_recovery_candidate(source, dialog.selected_track)

    def _play_recovery_candidate(self, source, track) -> None:
        if track is None:
            return
        source_update = self.online_adapter.set_playback_source(source, track)
        if source_update == "failed":
            self._show_recovery_message("保存在线播放来源失败，已取消播放。")
            return
        playback_track = self.online_adapter.build_playback_source_track(source, track)
        if playback_track is None:
            self._show_recovery_message("在线版本暂时无法播放。")
            return
        self._play_online_track(playback_track)
        if source_update == "source_updated":
            message = f"已更换为 {track.source_name} 的播放来源，正在播放。"
        else:
            message = f"已找到 {track.source_name} 的在线版本，正在播放。"
        self._show_recovery_message(message)

    def _on_recovery_failed(self, generation: int, message: str) -> None:
        self._pending_recovery_tracks.pop(int(generation), None)
        self._show_recovery_message(str(message or "在线恢复失败。"))

    def _show_recovery_message(self, message: str) -> None:
        text = str(message or "").strip()
        self._recovery_status_message = text
        if not text or not self.isVisible():
            return
        QToolTip.showText(
            self.mapToGlobal(QPoint(max(24, self.width() // 2), 72)),
            text,
            self,
            QRect(),
            3500,
        )

    def _show_action_message(self, message: str) -> None:
        """Show a short confirmation for non-playback actions."""

        text = str(message or "").strip()
        if not text or not self.isVisible():
            return
        QToolTip.showText(
            self.mapToGlobal(QPoint(max(24, self.width() // 2), 72)),
            text,
            self,
            QRect(),
            3000,
        )

    def _on_playback_track_changed(self, track) -> None:
        track_id = track.id if track is not None else ""
        self.library_collection.set_playing_track(track_id)
        self.router.set_playing_track(track_id)
        current_identity = track.stable_identity if isinstance(track, Track) else ""
        if current_identity:
            self._automatic_recovery_identities.intersection_update({current_identity})
        else:
            self._automatic_recovery_identities.clear()
        if track is not None:
            self.library_collection.record_play(track.id)

    def _on_remote_track_state_changed(
        self,
        identity: str,
        state: str,
        detail: str,
        payload: object,
    ) -> None:
        updated = self.online_adapter.apply_remote_state(
            identity,
            state,
            detail,
            payload if isinstance(payload, dict) else {},
        )
        if not self.online_adapter.is_formal or not isinstance(updated, Track):
            return
        normalized_state = str(state or "").strip().casefold().replace("-", "_")
        if normalized_state not in _AUTO_RECOVERY_FAILURE_STATES:
            return
        library_track = self.library_collection.track_for_id(updated.id)
        current_track = self.playback_adapter.state.current_track
        if (
            library_track is None
            or not library_track.is_online
            or current_track is None
            or current_track.stable_identity != library_track.stable_identity
        ):
            return
        recovery_identity = library_track.stable_identity
        if not recovery_identity or recovery_identity in self._automatic_recovery_identities:
            return
        self._automatic_recovery_identities.add(recovery_identity)
        self._request_online_recovery(library_track)

    def _on_playback_duration_changed(self, duration_ms: int | None) -> None:
        if duration_ms is None or int(duration_ms) <= 0:
            return
        current = self.playback_adapter.state.current_track
        if (
            self.online_adapter.is_formal
            and current is not None
            and current.is_online
            and current.stable_identity
        ):
            self.online_adapter.update_remote_duration(
                current.stable_identity,
                int(duration_ms),
            )

    def _sync_favorite_from_library(self, track_id: str, favorite: bool) -> None:
        current = self.playback_adapter.state.current_track
        if current is not None and current.id == track_id:
            self.playback_adapter.set_current_favorite(favorite)

    def _persist_favorite_membership(self, track: Track, favorite: bool) -> bool:
        """Persist local and remote favorites through the existing bridge."""

        discovery = self.online_discovery
        if discovery is None or not isinstance(track, Track):
            return False
        bridge = discovery.bridge
        if track.is_online:
            payload = dict(track.remote_payload)
            payload.update(
                {
                    "id": track.remote_track_id or track.remote_identity or track.id,
                    "remote_id": track.remote_track_id or track.remote_identity or track.id,
                    "source_id": track.source_id,
                    "sourceId": track.source_id,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                }
            )
            return bool(bridge.set_favorite(payload, bool(favorite)))
        member = self.playlist_adapter._track_member(track.id)
        if member is None:
            return False
        method_name = "add_playlist_members" if favorite else "remove_playlist_members"
        method = getattr(bridge, method_name, None)
        if not callable(method):
            return False
        try:
            return bool(method("liked", (member,)))
        except Exception:
            return False

    def _sync_favorite_from_player(self, favorite: bool) -> None:
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
        has_tracks = bool(self.library_collection.tracks())
        self.library_page.empty_state.set_action("" if has_tracks else "添加音乐文件夹")
        self.library_page.set_view_state(
            "content" if state == "loaded" else "empty",
            detail,
        )

    def _on_library_empty_action(self) -> None:
        """Route the empty-library action to the appropriate safe next step."""

        if self.library_page.current_view_state == "error" and self.real_library_adapter is not None:
            self.real_library_adapter.refresh()
            return
        self.open_settings_overlay()

    def _on_real_library_loaded(self) -> None:
        """Refresh the local playback projection after the read-only snapshot arrives."""

        if self._close_finalized or self.real_library_adapter is None:
            return
        self._real_library_projection_generation += 1
        generation = self._real_library_projection_generation
        self.playback_adapter.set_queue(self.library_collection.tracks())
        self.library_page.set_playback_enabled(
            self.playback_adapter.has_real_backend
        )
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("real_library.ui_state")
        # Let the shell paint the loaded state before building or replacing
        # Browse cards.  The following turns keep card work and artwork
        # requests separate so a loaded snapshot cannot monopolize the UI.
        if len(self.library_collection.tracks()) <= _REAL_LIBRARY_IMMEDIATE_PROJECTION_LIMIT:
            self.router.browse_page.refresh_cards()
            if self._startup_diagnostics is not None:
                self._startup_diagnostics.mark("real_library.browse_projection")
            next_phase = 1
        else:
            next_phase = 0
        QTimer.singleShot(
            0,
            lambda generation=generation, next_phase=next_phase: self._continue_real_library_projection(
                generation, next_phase
            ),
        )

    def _continue_real_library_projection(self, generation: int, phase: int) -> None:
        """Run post-load UI projection in small event-loop batches."""

        if (
            generation != self._real_library_projection_generation
            or self._close_finalized
            or self.real_library_adapter is None
        ):
            return
        if phase == 0:
            self.router.browse_page.refresh_cards()
            if self._startup_diagnostics is not None:
                self._startup_diagnostics.mark("real_library.browse_projection")
            QTimer.singleShot(
                0,
                lambda generation=generation: self._continue_real_library_projection(
                    generation, 1
                ),
            )
            return
        self._request_loaded_remote_artwork()
        if self._startup_diagnostics is not None:
            self._startup_diagnostics.mark("real_library.artwork_requests")

    def _request_loaded_remote_artwork(self) -> None:
        """Warm artwork for persisted remote tracks before they reach player surfaces."""

        if self.online_discovery is None:
            return
        requests: list[tuple[str, str]] = []
        for track in self.library_collection.tracks():
            if not track.is_online:
                continue
            artwork_url = track.artwork_url or artwork_url_from_payload(track.remote_payload)
            if artwork_url:
                requests.append((track.stable_identity, artwork_url))
        if requests:
            self.online_discovery.artwork_service.request_many(requests[:32])

    def _on_online_artwork_ready(self, _generation: int, track_key: str, data: bytes) -> None:
        """Apply one fetched cover to every existing projection of its stable track."""

        identity = str(track_key or "")
        artwork = bytes(data or b"")
        if not identity or not artwork:
            return
        for track in self.library_collection.tracks():
            identities = {
                track.id,
                track.stable_identity,
                track.remote_identity,
                track.remote_track_id,
            }
            if not track.is_online or identity not in identities:
                continue
            updated = replace(track, artwork_data=artwork)
            self.library_collection.update_runtime_track(updated)
            self.playback_adapter.update_track(updated)
            break

    def _on_player_bar_action(self, action: str) -> None:
        if action == "lyrics":
            self.navigation_adapter.set_route("immersive_lyrics")
        elif action == "desktop_lyrics":
            self._toggle_desktop_lyrics()
        elif action == "queue":
            self.navigation_adapter.set_route("immersive_now_playing")
            page = self.router._pages.get("immersive_lyrics")
            if page is not None and hasattr(page, "show_queue_panel"):
                page.show_queue_panel()

    def _ensure_desktop_lyrics_window(self) -> DesktopLyricsWindow:
        window = self.desktop_lyrics_window
        if window is not None:
            return window
        window = DesktopLyricsWindow(
            self.playback_adapter,
            self.lyrics_adapter,
            self._theme,
        )
        window.position_changed.connect(self._persist_desktop_lyrics_position)
        window.enabled_changed.connect(self._on_desktop_lyrics_enabled_changed)
        window.settings_requested.connect(
            self._toggle_desktop_lyrics_quick_settings_at
        )
        window.lock_state_change_requested.connect(
            self._on_desktop_lyrics_lock_state_requested
        )
        if self.desktop_lyrics_settings_popover is not None:
            self.desktop_lyrics_settings_popover.visibility_changed.connect(
                window.set_settings_popover_visible
            )
            window.set_settings_popover_visible(
                self.desktop_lyrics_settings_popover.isVisible()
            )
        self.desktop_lyrics_window = window
        window.apply_settings(self._settings_snapshot.to_dict())
        self._sync_desktop_lyrics_tray_state()
        return window

    def _ensure_desktop_lyrics_settings_popover(
        self,
    ) -> DesktopLyricsQuickSettingsPopover:
        popover = self.desktop_lyrics_settings_popover
        if popover is not None:
            return popover
        popover = DesktopLyricsQuickSettingsPopover(self._theme, self)
        popover.value_changed.connect(self._on_desktop_lyrics_setting_changed)
        popover.reset_position_requested.connect(
            self._reset_desktop_lyrics_position_from_quick_settings
        )
        if self.desktop_lyrics_window is not None:
            popover.visibility_changed.connect(
                self.desktop_lyrics_window.set_settings_popover_visible
            )
        self.desktop_lyrics_settings_popover = popover
        return popover

    def _toggle_desktop_lyrics_quick_settings(self) -> None:
        popover = self._prepare_desktop_lyrics_settings_popover()
        if popover is None:
            return
        popover.show_anchored(self.player_bar.desktop_lyrics_button)

    def _toggle_desktop_lyrics_quick_settings_at(
        self,
        global_position: QPoint,
    ) -> None:
        popover = self._prepare_desktop_lyrics_settings_popover()
        if popover is None:
            return
        popover.show_near_global(global_position)

    def _prepare_desktop_lyrics_settings_popover(
        self,
    ) -> DesktopLyricsQuickSettingsPopover | None:
        if self._close_finalized:
            return None
        popover = self._ensure_desktop_lyrics_settings_popover()
        if popover.isVisible():
            popover.hide()
            return None
        snapshot = (
            self._desktop_lyrics_settings_pending_snapshot
            or self._settings_snapshot
        )
        popover.set_values(snapshot.to_dict())
        return popover

    def _on_desktop_lyrics_lock_state_requested(self, locked: bool) -> None:
        self._on_desktop_lyrics_setting_changed(
            "floating_lyrics_passthrough",
            bool(locked),
        )

    def _sync_desktop_lyrics_tray_state(self) -> None:
        window = self.desktop_lyrics_window
        self.close_behavior_controller.set_desktop_lyrics_locked(
            bool(window is not None and window.is_enabled and window.is_locked)
        )

    def _unlock_desktop_lyrics_from_tray(self) -> None:
        if self._close_finalized:
            return
        window = self.desktop_lyrics_window
        if window is None or not window.is_enabled or not window.is_locked:
            return
        self._on_desktop_lyrics_setting_changed(
            "floating_lyrics_passthrough",
            False,
        )

    def _apply_pending_desktop_lyrics_preview(self) -> None:
        """Apply only the newest continuous desktop-lyrics preview value."""

        candidate = self._desktop_lyrics_settings_pending_snapshot
        window = self.desktop_lyrics_window
        if candidate is None or window is None:
            return
        window.apply_settings(candidate.to_dict(), live_preview=True)

    def _on_desktop_lyrics_setting_changed(self, key: str, value: object) -> None:
        if self._close_finalized or key not in DESKTOP_LYRICS_QUICK_SETTING_KEYS:
            return
        base = (
            self._desktop_lyrics_settings_pending_snapshot
            or self._settings_snapshot
        )
        candidate = base.with_updates({key: value})
        errors = self.settings_bridge.validate(candidate.to_dict())
        if key in errors:
            if self.desktop_lyrics_settings_popover is not None:
                self.desktop_lyrics_settings_popover.show_error(errors[key])
            return
        self._desktop_lyrics_settings_pending_snapshot = candidate
        if self.desktop_lyrics_settings_popover is not None:
            self.desktop_lyrics_settings_popover.show_error("")
        if self.desktop_lyrics_window is not None:
            if key in _DESKTOP_LYRICS_CONTINUOUS_PREVIEW_KEYS:
                self._desktop_lyrics_settings_preview_timer.start()
            else:
                self._desktop_lyrics_settings_preview_timer.stop()
                self.desktop_lyrics_window.apply_settings(candidate.to_dict())
        self._sync_desktop_lyrics_tray_state()
        self._desktop_lyrics_settings_save_timer.start()

    def _save_pending_desktop_lyrics_settings(self) -> bool:
        self._desktop_lyrics_settings_preview_timer.stop()
        candidate = self._desktop_lyrics_settings_pending_snapshot
        if candidate is None:
            return True
        previous = self._settings_snapshot
        try:
            saved = self.settings_bridge.save_snapshot(candidate)
        except SettingsBridgeError as error:
            self._desktop_lyrics_settings_pending_snapshot = None
            if self.desktop_lyrics_window is not None:
                self.desktop_lyrics_window.apply_settings(previous.to_dict())
            if self.desktop_lyrics_settings_popover is not None:
                self.desktop_lyrics_settings_popover.set_values(previous.to_dict())
                self.desktop_lyrics_settings_popover.show_error(str(error))
            return False
        self._settings_snapshot = SettingsSnapshot.from_mapping(saved.to_dict())
        self._desktop_lyrics_settings_pending_snapshot = None
        if self.desktop_lyrics_settings_popover is not None:
            self.desktop_lyrics_settings_popover.set_values(saved.to_dict())
        if self.settings_overlay is not None and self.settings_overlay.isVisible():
            self.settings_overlay.merge_external_snapshot(
                saved,
                DESKTOP_LYRICS_QUICK_SETTING_KEYS,
            )
        return True

    def _reset_desktop_lyrics_position_from_quick_settings(self) -> None:
        if not self._save_pending_desktop_lyrics_settings():
            return
        self._ensure_desktop_lyrics_window().reset_position()

    def _show_desktop_lyrics(self) -> None:
        if self._close_finalized:
            return
        self._ensure_desktop_lyrics_window().show_for_current_screen()

    def _toggle_desktop_lyrics(self) -> None:
        if self._close_finalized:
            return
        window = self._ensure_desktop_lyrics_window()
        if window.is_enabled:
            window.hide_for_user()
        else:
            window.show_for_current_screen()

    def _on_desktop_lyrics_enabled_changed(self, enabled: bool) -> None:
        if hasattr(self, "player_bar"):
            self.player_bar.desktop_lyrics_button.set_active(bool(enabled))
        self._sync_desktop_lyrics_tray_state()

    def _persist_desktop_lyrics_position(self, x: int, y: int) -> None:
        if self._close_finalized:
            return
        try:
            self._settings_snapshot = self.settings_bridge.save_snapshot(
                self._settings_snapshot.with_updates(
                    {"floating_lyrics_x": int(x), "floating_lyrics_y": int(y)}
                )
            )
            if self.settings_overlay is not None and self.settings_overlay.isVisible():
                self.settings_overlay.merge_external_snapshot(
                    self._settings_snapshot,
                    ("floating_lyrics_x", "floating_lyrics_y"),
                )
        except Exception:
            # Dragging must never surface a modal error or affect playback.
            return

    def _open_now_playing(self) -> None:
        self.navigation_adapter.set_route("immersive_now_playing")
