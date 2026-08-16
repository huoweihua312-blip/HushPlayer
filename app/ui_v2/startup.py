"""Production-capable startup helpers for the formal UI V2 shell."""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core.app_paths import AppPaths
from app.services.library_repository import LibraryRepository
from app.services.production_playback_controller import ProductionPlaybackController
from app.services.remote_track_store import RemoteTrackStore
from app.services.online_discovery_runtime import OnlineDiscoveryRuntime
from app.startup import create_application_context
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.shell.main_window import MainWindow


UI_V2_DATA_MODE_MOCK = "mock"
UI_V2_DATA_MODE_REAL = "real"


@dataclass(frozen=True, slots=True)
class UiV2RuntimeServices:
    """Formal service boundary injected into the UI V2 shell."""

    paths: AppPaths
    settings_path: Path
    repository: LibraryRepository
    remote_tracks: RemoteTrackStore
    playback_adapter: PlaybackAdapter
    lyrics_adapter: LyricsAdapter
    online_discovery: OnlineDiscoveryRuntime | None = None


def normalize_ui_v2_data_mode(value: str | None) -> str:
    mode = str(value or "").strip().casefold()
    if mode in {UI_V2_DATA_MODE_MOCK, UI_V2_DATA_MODE_REAL}:
        return mode
    raise ValueError(f"Unsupported UI V2 data mode: {value!r}")


def build_ui_v2_runtime_services(
    paths: AppPaths | None = None,
    *,
    playback_adapter: PlaybackAdapter | None = None,
    lyrics_adapter: LyricsAdapter | None = None,
) -> UiV2RuntimeServices:
    """Create the single formal service set used by production UI V2."""

    resolved = paths or AppPaths.resolve()
    data_dir = resolved.data_dir
    repository = LibraryRepository(
        data_dir / "library.json",
        data_dir / "playlists.json",
        data_dir / "stats.json",
    )
    remote_tracks = RemoteTrackStore(data_dir / "remote_tracks.json")
    online_discovery = OnlineDiscoveryRuntime(
        resolved,
        repository,
        remote_tracks,
    )
    if playback_adapter is None:
        controller = ProductionPlaybackController(
            online_resolver=online_discovery.playback_resolver,
            online_audio_cache=online_discovery.online_audio_cache,
            online_cache_allowed=online_discovery.online_source_allows_audio_cache,
        )
        playback_adapter = PlaybackAdapter(
            timer_enabled=False,
            controller=controller,
        )
    elif playback_adapter.controller is not None:
        playback_adapter.controller.set_online_resolver(
            online_discovery.playback_resolver
        )
    return UiV2RuntimeServices(
        paths=resolved,
        settings_path=data_dir / "settings.json",
        repository=repository,
        remote_tracks=remote_tracks,
        playback_adapter=playback_adapter,
        lyrics_adapter=lyrics_adapter or LyricsAdapter(
            lyrics_service=online_discovery.lyrics_service,
            lyrics_cache_dir=resolved.cache_dir / "lyrics",
            lyrics_bindings_path=resolved.data_dir / "lyrics_bindings.json",
        ),
        online_discovery=online_discovery,
    )


def create_ui_v2_main_window(
    *,
    data_mode: str = UI_V2_DATA_MODE_REAL,
    services: UiV2RuntimeServices | None = None,
    initialize_storage: bool = True,
) -> MainWindow:
    """Build the V2 shell through one injectable production path."""

    mode = normalize_ui_v2_data_mode(data_mode)
    if mode == UI_V2_DATA_MODE_MOCK:
        isolated_settings = (
            Path(os.environ.get("TEMP", tempfile.gettempdir()))
            / "HushPlayer-ui-v2"
            / f"mock-settings-{os.getpid()}.json"
        )
        return MainWindow(
            data_mode=UI_V2_DATA_MODE_MOCK,
            settings_path=isolated_settings,
        )

    runtime = services or build_ui_v2_runtime_services()
    if initialize_storage:
        runtime.paths.initialize_user_storage()
    return MainWindow(
        data_mode=UI_V2_DATA_MODE_REAL,
        settings_path=runtime.settings_path,
        repository=runtime.repository,
        remote_tracks=runtime.remote_tracks,
        playback_adapter=runtime.playback_adapter,
        lyrics_adapter=runtime.lyrics_adapter,
        online_discovery=runtime.online_discovery,
    )


def install_ui_v2_smoke_exit(
    app: QApplication,
    window: MainWindow,
    *,
    environment_key: str = "HUSHPLAYER_UI_V2_SMOKE_EXIT_MS",
) -> None:
    _install_packaging_node_smoke(app, window)
    _install_startup_smoke_exit(app, window)
    smoke_exit_text = str(os.environ.get(environment_key) or "").strip()
    if not smoke_exit_text:
        return
    try:
        smoke_exit_ms = max(100, int(smoke_exit_text))
    except ValueError:
        return
    QTimer.singleShot(smoke_exit_ms, window.close)
    QTimer.singleShot(smoke_exit_ms + 50, app.quit)


def _install_packaging_node_smoke(app: QApplication, window: MainWindow) -> None:
    smoke_exit_text = str(
        os.environ.get("HUSHPLAYER_PACKAGING_SMOKE_EXIT_MS") or ""
    ).strip()
    if not smoke_exit_text:
        return
    try:
        smoke_exit_ms = max(500, int(smoke_exit_text))
    except ValueError:
        smoke_exit_ms = 0
    if not smoke_exit_ms:
        return

    def fail_packaging_node_smoke(message: str) -> None:
        print(f"[packaging-smoke] Node runner failed: {message}", file=sys.stderr)
        app.exit(2)

    def start_packaging_node_smoke() -> None:
        runtime = getattr(window, "online_discovery", None)
        client = getattr(runtime, "client", None)
        if client is None:
            fail_packaging_node_smoke("online source client is unavailable")
            return
        client.sourceReady.connect(
            lambda _data: print("[packaging-smoke] Node runner ready")
        )
        client.processError.connect(fail_packaging_node_smoke)
        client.requestFailed.connect(
            lambda _request_id, _action, message: fail_packaging_node_smoke(message)
        )
        client.ping(timeout_ms=max(1000, smoke_exit_ms - 1000))

    QTimer.singleShot(0, start_packaging_node_smoke)
    QTimer.singleShot(smoke_exit_ms, window.close)


def _install_startup_smoke_exit(app: QApplication, window: MainWindow) -> None:
    smoke_exit_text = str(
        os.environ.get("HUSHPLAYER_STARTUP_SMOKE_EXIT_MS") or ""
    ).strip()
    if not smoke_exit_text:
        return
    try:
        smoke_exit_ms = max(100, int(smoke_exit_text))
    except ValueError:
        return
    QTimer.singleShot(smoke_exit_ms, window.close)
    QTimer.singleShot(smoke_exit_ms + 50, app.quit)


def run_ui_v2_application(
    argv: Sequence[str] | None = None,
    *,
    data_mode: str = UI_V2_DATA_MODE_REAL,
    initialize_storage: bool = True,
) -> int:
    """Run UI V2 without maintaining a second QApplication flow."""

    isolated_settings = None
    if normalize_ui_v2_data_mode(data_mode) == UI_V2_DATA_MODE_MOCK:
        isolated_settings = (
            Path(os.environ.get("TEMP", tempfile.gettempdir()))
            / "HushPlayer-ui-v2"
            / f"mock-settings-{os.getpid()}.json"
        )
    context = create_application_context(
        argv if argv is not None else sys.argv,
        settings_path=str(isolated_settings) if isolated_settings is not None else None,
    )
    window = create_ui_v2_main_window(
        data_mode=data_mode,
        initialize_storage=initialize_storage,
    )
    window.setWindowIcon(context.icon)
    window.show()
    install_ui_v2_smoke_exit(context.app, window)
    return context.app.exec()
