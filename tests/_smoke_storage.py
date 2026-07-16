from __future__ import annotations

import atexit
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IsolatedAppStorage:
    root: Path
    _temporary_directory: tempfile.TemporaryDirectory

    @property
    def app_data_dir(self) -> Path:
        return self.root / "appdata"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    def cleanup(self) -> None:
        self._temporary_directory.cleanup()


def activate_isolated_app_storage(prefix: str) -> IsolatedAppStorage:
    """Redirect all writable application paths before importing app modules."""

    temporary_directory = tempfile.TemporaryDirectory(prefix=prefix)
    storage = IsolatedAppStorage(
        root=Path(temporary_directory.name).resolve(),
        _temporary_directory=temporary_directory,
    )
    os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(storage.app_data_dir)
    os.environ["HUSHPLAYER_CACHE_DIR"] = str(storage.cache_dir)
    os.environ["HUSHPLAYER_LOG_DIR"] = str(storage.log_dir)
    atexit.register(storage.cleanup)
    return storage
