"""Remember which source actually played a song (or an album).

Online plugins go stale: a track can be listed by source A but its playback URL
returns 404, so HushPlayer falls back to searching other sources. Doing that
search again for every track of the same album makes switching feel slow, and the
user asked for the choice to stick ("一旦切到网易云，就别再每首重新找").

This module stores only *cache* data under the data directory, so it can be
deleted at any time without losing favourites, playlists or settings:

* ``tracks``     – track id → the candidate that actually played (source id,
                   remote id, title/artist/album/duration), so replaying the same
                   row resolves directly instead of searching again;
* ``source_map`` – original source id → source id that worked for that source's
                   tracks (a broken plugin stays broken for a while);
* ``preferred``  – the last source that successfully played a fallback, used to
                   order the fallback chain.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("services.source_memory")

_LOCK = threading.RLock()
_CACHE: dict[str, Any] | None = None
_MAX_TRACKS = 4000
_MAX_AGE_S = 60 * 60 * 24 * 90


def memory_file() -> Path:
    return paths.data_dir() / "online_source_memory.json"


def _empty() -> dict[str, Any]:
    return {"tracks": {}, "source_map": {}, "preferred": {}}


def _read() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    data = _empty()
    try:
        raw = json.loads(memory_file().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key in ("tracks", "source_map"):
                value = raw.get(key)
                if isinstance(value, dict):
                    data[key] = {str(k): v for k, v in value.items() if isinstance(v, dict)}
            pref = raw.get("preferred")
            if isinstance(pref, dict) and isinstance(pref.get("source_id"), str):
                data["preferred"] = {
                    "source_id": pref["source_id"],
                    "saved_at": float(pref.get("saved_at") or 0),
                }
    except FileNotFoundError:
        pass
    except Exception:
        log.debug("cannot read source memory", exc_info=True)
    _CACHE = data
    return data


def _write(data: dict[str, Any]) -> None:
    global _CACHE
    _CACHE = data
    path = memory_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        log.debug("cannot persist source memory", exc_info=True)


def _prune(data: dict[str, Any]) -> None:
    tracks: dict[str, dict] = data.get("tracks", {})
    if len(tracks) > _MAX_TRACKS:
        ordered = sorted(tracks.items(), key=lambda item: float(item[1].get("saved_at") or 0))
        for key, _ in ordered[: len(tracks) - _MAX_TRACKS]:
            tracks.pop(key, None)
    cutoff = time.time() - _MAX_AGE_S
    for key in [k for k, v in tracks.items() if float(v.get("saved_at") or 0) < cutoff]:
        tracks.pop(key, None)


# ------------------------------------------------------------------ tracks
def track_alias(track_id: str) -> dict[str, Any] | None:
    if not track_id:
        return None
    entry = _read()["tracks"].get(str(track_id))
    if not isinstance(entry, dict) or not entry.get("source_id"):
        return None
    if not entry.get("remote_id"):
        return None
    return dict(entry)


def remember_track(track: object, match: object) -> None:
    """Store the candidate that played for ``track`` (both are ``Track``s)."""
    track_id = str(getattr(track, "id", "") or "")
    source_id = str(getattr(match, "source_id", "") or "")
    if not track_id or not source_id:
        return
    alias = {
        "source_id": source_id,
        "source_name": str(getattr(match, "source_name", "") or ""),
        "remote_id": str(getattr(match, "remote_id", "") or ""),
        "title": str(getattr(match, "title", "") or ""),
        "artist": str(getattr(match, "artist", "") or ""),
        "album": str(getattr(match, "album", "") or ""),
        "duration_ms": int(getattr(match, "duration_ms", 0) or 0),
        "artwork_url": str(getattr(match, "artwork_url", "") or ""),
        "saved_at": time.time(),
    }
    with _LOCK:
        data = _read()
        data["tracks"][track_id] = alias
        _prune(data)
        _write(data)


def forget_track(track_id: str) -> None:
    if not track_id:
        return
    with _LOCK:
        data = _read()
        if data["tracks"].pop(str(track_id), None) is not None:
            _write(data)


# ------------------------------------------------------------- source map
def source_map(original_source_id: str) -> str:
    entry = _read()["source_map"].get(str(original_source_id or ""))
    if isinstance(entry, dict):
        return str(entry.get("source_id") or "")
    return ""


def remember_source_map(original_source_id: str, working_source_id: str) -> None:
    if not original_source_id or not working_source_id:
        return
    if original_source_id == working_source_id:
        return
    with _LOCK:
        data = _read()
        data["source_map"][str(original_source_id)] = {
            "source_id": str(working_source_id),
            "saved_at": time.time(),
        }
        _write(data)


# -------------------------------------------------------------- preferred
def preferred() -> str:
    entry = _read()["preferred"]
    return str(entry.get("source_id") or "") if isinstance(entry, dict) else ""


def set_preferred(source_id: str) -> None:
    if not source_id:
        return
    with _LOCK:
        data = _read()
        if preferred() == source_id:
            return
        data["preferred"] = {"source_id": str(source_id), "saved_at": time.time()}
        _write(data)


def clear() -> None:
    with _LOCK:
        _write(_empty())
