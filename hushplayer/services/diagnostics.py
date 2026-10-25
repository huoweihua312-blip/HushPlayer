"""One-click diagnostics bundle (logs + versions + source state)."""

from __future__ import annotations

import json
import platform
import zipfile
from datetime import datetime
from pathlib import Path

from ..core import paths
from ..version import VERSION
from ..online import health

_SENSITIVE = ("token", "cookie", "secret", "password", "authorization", "csrf")


def _sanitize(value):
    if isinstance(value, dict):
        return {
            key: ("***" if any(word in str(key).lower() for word in _SENSITIVE) else _sanitize(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def export_bundle(dest: Path | None = None) -> Path:
    """Zip logs, version info and (sanitised) source state for support."""
    data = paths.data_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if dest is None:
        out_dir = data / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"hushplayer-diagnostics-{stamp}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "version": VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "timestamp": stamp,
        "data_dir": str(data),
    }
    try:
        import PySide6

        summary["pyside6"] = PySide6.__version__
    except Exception:  # noqa: BLE001
        summary["pyside6"] = "unknown"

    registry = _read_json(data / "source_registry.json") or {}
    sources = registry.get("sources") if isinstance(registry, dict) else None
    if isinstance(sources, list):
        summary["sources"] = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "enabled": item.get("enabled"),
                "file_exists": item.get("file_exists"),
            }
            for item in sources
            if isinstance(item, dict)
        ]
    summary["health"] = health.all_stats() if hasattr(health, "all_stats") else {}

    memory = _read_json(data / "online_source_memory.json") or {}
    tracks = memory.get("tracks") if isinstance(memory, dict) else None
    summary["memory"] = {
        "tracks": len(tracks) if isinstance(tracks, dict) else 0,
        "source_map": len(memory.get("source_map") or {}) if isinstance(memory, dict) else 0,
        "preferred": (memory.get("preferred") or {}).get("source_id") if isinstance(memory, dict) else "",
    }

    settings = _read_json(data / "settings.json")
    if settings is not None:
        summary["settings"] = _sanitize(settings)

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        for name in ("hushplayer.log", "hushplayer.log.1", "crash.log"):
            path = data / "logs" / name if (data / "logs" / name).exists() else data / name
            if path.exists() and path.is_file():
                try:
                    bundle.write(path, f"logs/{name}")
                except OSError:
                    pass
        bundle.writestr(
            "README.txt",
            "HushPlayer diagnostics\n"
            f"version: {VERSION}\n"
            "summary.json contains version, platform and sanitised source state.\n"
            "logs/ contains the last rotated player logs when present.\n",
        )
    return dest
