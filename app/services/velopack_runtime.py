"""Optional Velopack bootstrap used by the parallel update prototype.

The existing updater remains the default.  A Velopack package is detected by
the files that Velopack places beside the current executable, or it can be
explicitly enabled with ``HUSHPLAYER_ENABLE_VELOPACK=1`` during testing.
Keeping the import lazy means normal source runs and the current release build
do not require the optional package.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_LOGGER = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "on"}
VELOPACK_UPDATE_SOURCE_ENV = "HUSHPLAYER_VELOPACK_UPDATE_SOURCE"
VELOPACK_DEFAULT_UPDATE_SOURCE = "https://github.com/huoweihua312-blip/HushPlayer"


def _is_true(value: object) -> bool:
    return str(value or "").strip().casefold() in _TRUE_VALUES


def is_velopack_install(executable: str | Path | None = None) -> bool:
    """Return whether *executable* is inside a Velopack app directory."""

    candidate = Path(executable or sys.executable).expanduser()
    try:
        root = candidate.resolve().parent
    except OSError:
        root = candidate.parent
    updater = root / "Update.exe"
    if root.name.casefold() == "current":
        updater = root.parent / "Update.exe"
    return updater.is_file() and (root / "sq.version").is_file()


def is_velopack_enabled(executable: str | Path | None = None) -> bool:
    """Return whether the optional Velopack bootstrap should run."""

    if _is_true(os.environ.get("HUSHPLAYER_DISABLE_VELOPACK")):
        return False
    return _is_true(os.environ.get("HUSHPLAYER_ENABLE_VELOPACK")) or is_velopack_install(
        executable
    )


def velopack_update_source() -> str | None:
    """Return the Velopack feed, allowing a local source during acceptance."""

    source = os.environ.get(VELOPACK_UPDATE_SOURCE_ENV, "").strip()
    return source or VELOPACK_DEFAULT_UPDATE_SOURCE


def bootstrap_velopack() -> bool:
    """Run Velopack's early process bootstrap when the package is active.

    Missing optional dependencies or a failed bootstrap are logged and fall
    back to the current startup path.  This is intentional while the new
    packaging route is being validated in parallel.
    """

    if not is_velopack_enabled():
        return False
    try:
        import velopack  # type: ignore[import-not-found]
    except ImportError:
        _LOGGER.warning(
            "Velopack package detected but the optional Python module is unavailable."
        )
        return False

    try:
        # Updates are applied only after the app has saved state and closed Qt.
        velopack.App().set_auto_apply_on_startup(False).run()
    except Exception:
        _LOGGER.exception("Velopack bootstrap failed; using the existing startup path.")
        return False
    return True


def create_update_manager(update_source: str) -> Any | None:
    """Create a manager for the packaged update source."""

    try:
        import velopack  # type: ignore[import-not-found]
    except ImportError:
        return None
    source: Any = str(update_source).strip()
    parsed = urlsplit(source)
    if parsed.hostname == "github.com" and len(parsed.path.strip("/").split("/")) == 2:
        source = velopack.GithubSource(source, prerelease=True)
    elif parsed.scheme.casefold() in {"http", "https"}:
        source = velopack.HttpSource(
            source, velopack.HttpOptions(Headers=[], TimeoutMilliseconds=120_000)
        )
    return velopack.UpdateManager(source)
