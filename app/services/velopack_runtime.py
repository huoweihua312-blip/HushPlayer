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


_LOGGER = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "on"}
VELOPACK_UPDATE_SOURCE_ENV = "HUSHPLAYER_VELOPACK_UPDATE_SOURCE"


def _is_true(value: object) -> bool:
    return str(value or "").strip().casefold() in _TRUE_VALUES


def is_velopack_install(executable: str | Path | None = None) -> bool:
    """Return whether *executable* is inside a Velopack app directory."""

    candidate = Path(executable or sys.executable).expanduser()
    try:
        root = candidate.resolve().parent
    except OSError:
        root = candidate.parent
    return (root / "Update.exe").is_file() and (root / "sq.version").is_file()


def is_velopack_enabled(executable: str | Path | None = None) -> bool:
    """Return whether the optional Velopack bootstrap should run."""

    if _is_true(os.environ.get("HUSHPLAYER_DISABLE_VELOPACK")):
        return False
    return _is_true(os.environ.get("HUSHPLAYER_ENABLE_VELOPACK")) or is_velopack_install(
        executable
    )


def velopack_update_source() -> str | None:
    """Return the opt-in Velopack feed used by the migration prototype."""

    source = os.environ.get(VELOPACK_UPDATE_SOURCE_ENV, "").strip()
    return source or None


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
        velopack.App().run()
    except Exception:
        _LOGGER.exception("Velopack bootstrap failed; using the existing startup path.")
        return False
    return True


def create_update_manager(update_source: str) -> Any | None:
    """Create a Velopack UpdateManager for future opt-in update integration."""

    try:
        import velopack  # type: ignore[import-not-found]
    except ImportError:
        return None
    return velopack.UpdateManager(str(update_source))
