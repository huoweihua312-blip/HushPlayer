"""Production-capable startup helpers for the opt-in UI V2 shell."""

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
from app.startup import UI_FLAVOR_V2, create_application_context
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
    return UiV2RuntimeServices(
        paths=resolved,
        settings_path=data_dir / "settings.json",
        repository=LibraryRepository(
            data_dir / "library.json",
            data_dir / "playlists.json",
            data_dir / "stats.json",
        ),
        remote_tracks=RemoteTrackStore(data_dir / "remote_tracks.json"),
        playback_adapter=playback_adapter or PlaybackAdapter(
            timer_enabled=False,
            controller=ProductionPlaybackController(),
        ),
        lyrics_adapter=lyrics_adapter or LyricsAdapter(),
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
            force_dark_theme=True,
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
        force_dark_theme=True,
    )


def install_ui_v2_smoke_exit(
    app: QApplication,
    window: MainWindow,
    *,
    environment_key: str = "HUSHPLAYER_UI_V2_SMOKE_EXIT_MS",
) -> None:
    smoke_exit_text = str(os.environ.get(environment_key) or "").strip()
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

    context = create_application_context(
        argv if argv is not None else sys.argv,
        ui_flavor=UI_FLAVOR_V2,
    )
    window = create_ui_v2_main_window(
        data_mode=data_mode,
        initialize_storage=initialize_storage,
    )
    window.setWindowIcon(context.icon)
    window.show()
    install_ui_v2_smoke_exit(context.app, window)
    return context.app.exec()
