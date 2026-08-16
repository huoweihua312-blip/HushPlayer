"""Small cache-maintenance operations shared by the formal UI runtime."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def clear_missing_cache_files(cache_dirs: Iterable[Path]) -> dict[str, object]:
    """Remove marker files left by failed cover or lyrics requests.

    The old window owned this housekeeping loop.  Keep it as a filesystem-only
    service so the settings surface does not need to import a UI module.
    """

    removed = 0
    errors: list[str] = []
    visited: set[Path] = set()
    for raw_dir in cache_dirs:
        cache_dir = Path(raw_dir)
        try:
            cache_dir = cache_dir.resolve()
        except OSError as error:
            errors.append(f"{cache_dir}: {error}")
            continue
        if cache_dir in visited or not cache_dir.is_dir():
            continue
        visited.add(cache_dir)
        try:
            candidates = tuple(cache_dir.rglob("*.missing"))
        except OSError as error:
            errors.append(f"{cache_dir}: {error}")
            continue
        for marker in candidates:
            if not marker.is_file():
                continue
            try:
                marker.unlink()
            except OSError as error:
                errors.append(f"{marker}: {error}")
            else:
                removed += 1
    return {"removed": removed, "errors": errors}
