from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths


APP_NAME = "HushPlayer"
APP_VERSION = "0.5.0-beta.1"

USER_DATA_FILES = (
    "ignored_imports.json",
    "library.json",
    "pending_imports.json",
    "playback_session.json",
    "playlists.json",
    "play_queue.json",
    "remote_tracks.json",
    "settings.json",
    "stats.json",
    "lyrics_bindings.json",
)


def _resolved_environment_path(name: str) -> Path | None:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Single source of truth for bundled and user-writable paths."""

    bundled_resource_dir: Path
    application_data_dir: Path
    cache_dir: Path
    log_dir: Path
    frozen: bool
    legacy_project_dir: Path

    @classmethod
    def resolve(cls) -> "AppPaths":
        frozen = bool(getattr(sys, "frozen", False))
        bundled_override = _resolved_environment_path(
            "HUSHPLAYER_BUNDLED_RESOURCE_DIR"
        )
        if bundled_override is not None:
            bundled_resource_dir = bundled_override
        elif frozen:
            # PyInstaller-specific handling stays centralized in this module.
            bundled_resource_dir = Path(
                getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)
            ).resolve()
        else:
            bundled_resource_dir = Path(__file__).resolve().parents[2]

        application_data_dir = _resolved_environment_path(
            "HUSHPLAYER_APP_DATA_DIR"
        )
        if application_data_dir is None:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
            application_data_dir = (
                Path(location).resolve()
                if location
                else Path.home() / "AppData" / "Roaming" / APP_NAME
            )

        cache_dir = _resolved_environment_path("HUSHPLAYER_CACHE_DIR")
        if cache_dir is None:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation
            )
            cache_dir = (
                Path(location).resolve()
                if location
                else application_data_dir / "cache"
            )

        log_dir = _resolved_environment_path("HUSHPLAYER_LOG_DIR")
        if log_dir is None:
            log_dir = application_data_dir / "logs"

        return cls(
            bundled_resource_dir=bundled_resource_dir,
            application_data_dir=application_data_dir,
            cache_dir=cache_dir,
            log_dir=log_dir,
            frozen=frozen,
            legacy_project_dir=Path(__file__).resolve().parents[2],
        )

    @property
    def data_dir(self) -> Path:
        return self.application_data_dir / "data"

    @property
    def metadata_cache_file(self) -> Path:
        return self.cache_dir / "metadata_cache.json"

    def resource_path(self, *parts: str) -> Path:
        return self.bundled_resource_dir.joinpath(*parts)

    def initialize_user_storage(self) -> None:
        for directory in (
            self.application_data_dir,
            self.data_dir,
            self.cache_dir,
            self.cache_dir / "covers",
            self.cache_dir / "lyrics",
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_data_files()

    def _migrate_legacy_data_files(self) -> None:
        if self.frozen:
            return
        legacy_data_dir = self.legacy_project_dir / "data"
        for filename in USER_DATA_FILES:
            self._copy_file_if_missing(
                legacy_data_dir / filename,
                self.data_dir / filename,
            )
        self._copy_file_if_missing(
            legacy_data_dir / "metadata_cache.json",
            self.metadata_cache_file,
        )

    @staticmethod
    def _copy_file_if_missing(source: Path, destination: Path) -> bool:
        if destination.exists() or not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return True
