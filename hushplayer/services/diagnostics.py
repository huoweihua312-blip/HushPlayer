"""One-click diagnostics bundle (logs + versions + source state)."""

from __future__ import annotations

import json
import platform
import re
import zipfile
from datetime import datetime
from pathlib import Path

from ..core import paths
from ..version import VERSION
from ..online import health

_SENSITIVE = ("token", "cookie", "secret", "password", "authorization", "csrf")

#: 日志正文里的凭据：日志是排查问题时唯一的现场，必须和 settings.json 一样脱敏。
_TEXT_SECRETS = (
    re.compile(
        r"(?i)\b(cookie|authorization|token|secret|password|csrf)\b\"?\s*[:=]\s*\"?([^\"\s,;}]+)"
    ),
    re.compile(r"(?i)([?&](?:token|key|sign|auth|password|secret)=)[^&\s]+"),
)


def _redact_text(text: str) -> str:
    for pattern in _TEXT_SECRETS:
        text = pattern.sub(lambda match: f"{match.group(1)}=***", text)
    return text


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


def _audio_cache_summary(data: Path) -> dict:
    """缓存命中/完整性概览；只统计大小与索引状态，不读音频内容。"""
    cache_dir = data / "cache" / "audio"
    if not cache_dir.is_dir():
        return {"files": 0, "bytes": 0, "complete": 0, "broken": 0}
    files = [item for item in cache_dir.iterdir() if item.is_file() and item.suffix != ".json"]
    complete = broken = 0
    for item in files:
        meta = _read_json(item.with_suffix(".meta.json"))
        if isinstance(meta, dict) and meta.get("complete"):
            complete += 1
        else:
            broken += 1
    return {
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files if item.is_file()),
        "complete": complete,
        "broken": broken,
    }


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

    session = _read_json(data / "play_queue.json") or {}
    if isinstance(session, dict):
        summary["session"] = {
            "version": session.get("version"),
            "saved_at": session.get("saved_at"),
            "position_ms": session.get("position_ms"),
            "current_id": session.get("current_id"),
            "tracks": len(session.get("items") or []),
            "shuffle": session.get("shuffle"),
            "repeat": session.get("repeat"),
        }
    summary["audio_cache"] = _audio_cache_summary(data)

    settings = _read_json(data / "settings.json")
    if settings is not None:
        summary["settings"] = _sanitize(settings)

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
        for name in ("hushplayer.log", "hushplayer.log.1", "crash.log"):
            path = data / "logs" / name if (data / "logs" / name).exists() else data / name
            if path.exists() and path.is_file():
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    bundle.writestr(f"logs/{name}", _redact_text(text))
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
