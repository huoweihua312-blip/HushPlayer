from __future__ import annotations

import atexit
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


_ISOLATED_ENVIRONMENT_NAMES = (
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "HUSHPLAYER_APP_DATA_DIR",
    "HUSHPLAYER_CACHE_DIR",
    "HUSHPLAYER_LOG_DIR",
    "HUSHPLAYER_SOURCE_REGISTRY",
    "HUSHPLAYER_USER_SOURCES",
)


@dataclass(slots=True)
class IsolatedAppStorage:
    root: Path
    _temporary_directory: tempfile.TemporaryDirectory
    _original_environment: dict[str, str | None]
    _app_paths_type: type | None = None
    _original_resolve: object | None = None
    _isolated_resolve: object | None = None
    _closed: bool = False

    @property
    def app_data_dir(self) -> Path:
        return self.root / "appdata"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    @property
    def roaming_app_data_dir(self) -> Path:
        return self.root / "roaming"

    @property
    def local_app_data_dir(self) -> Path:
        return self.root / "local"

    @property
    def legacy_project_dir(self) -> Path:
        return self.root / "legacy_project"

    @property
    def source_registry_file(self) -> Path:
        return self.app_data_dir / "source_runtime" / "source_registry.json"

    @property
    def user_sources_dir(self) -> Path:
        return self.app_data_dir / "user_sources"

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        if (
            self._app_paths_type is not None
            and self._original_resolve is not None
            and self._app_paths_type.__dict__.get("resolve") is self._isolated_resolve
        ):
            setattr(self._app_paths_type, "resolve", self._original_resolve)
        for name, value in self._original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._temporary_directory.cleanup()


def activate_isolated_app_storage(prefix: str) -> IsolatedAppStorage:
    """Redirect writable and legacy application paths before app imports."""

    temporary_directory = tempfile.TemporaryDirectory(prefix=prefix)
    storage = IsolatedAppStorage(
        root=Path(temporary_directory.name).resolve(),
        _temporary_directory=temporary_directory,
        _original_environment={
            name: os.environ.get(name) for name in _ISOLATED_ENVIRONMENT_NAMES
        },
    )
    for directory in (
        storage.app_data_dir,
        storage.cache_dir,
        storage.log_dir,
        storage.roaming_app_data_dir,
        storage.local_app_data_dir,
        storage.legacy_project_dir / "data",
        storage.legacy_project_dir / "source_runtime" / "sources" / "active",
        storage.legacy_project_dir / "user_sources",
        storage.user_sources_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    isolated_environment = {
        "APPDATA": storage.roaming_app_data_dir,
        "LOCALAPPDATA": storage.local_app_data_dir,
        "XDG_CACHE_HOME": storage.local_app_data_dir / "xdg-cache",
        "XDG_DATA_HOME": storage.local_app_data_dir / "xdg-data",
        "HUSHPLAYER_APP_DATA_DIR": storage.app_data_dir,
        "HUSHPLAYER_CACHE_DIR": storage.cache_dir,
        "HUSHPLAYER_LOG_DIR": storage.log_dir,
        "HUSHPLAYER_SOURCE_REGISTRY": storage.source_registry_file,
        "HUSHPLAYER_USER_SOURCES": storage.user_sources_dir,
    }
    for name, path in isolated_environment.items():
        os.environ[name] = str(path)

    # Development builds deliberately use the checkout as a legacy migration
    # source. Smoke tests must never inspect that real data, so replace only
    # the resolver in this test process after every user path is isolated.
    from app.core.app_paths import AppPaths

    original_resolve = AppPaths.__dict__["resolve"]

    def resolve_isolated(cls) -> AppPaths:
        paths = original_resolve.__func__(cls)
        object.__setattr__(paths, "legacy_project_dir", storage.legacy_project_dir)
        return paths

    AppPaths.resolve = classmethod(resolve_isolated)
    storage._app_paths_type = AppPaths
    storage._original_resolve = original_resolve
    storage._isolated_resolve = AppPaths.__dict__["resolve"]

    resolved_paths = AppPaths.resolve()
    assert resolved_paths.application_data_dir == storage.app_data_dir
    assert resolved_paths.cache_dir == storage.cache_dir
    assert resolved_paths.log_dir == storage.log_dir
    assert resolved_paths.legacy_project_dir == storage.legacy_project_dir
    atexit.register(storage.cleanup)
    return storage
