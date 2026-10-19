"""ReplayGain support for local files (track or album gain)."""

from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile

_DB = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*dB", re.IGNORECASE)
_CACHE: dict[tuple[str, float, str], float | None] = {}
_MAX_DB = 12.0


def _parse(value: object) -> float | None:
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    match = _DB.search(str(value))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def gain_db(path: str, mode: str = "track") -> float | None:
    """Return the ReplayGain value in dB for ``path`` (cached per mtime)."""
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    key = (path, stat.st_mtime, mode)
    if key in _CACHE:
        return _CACHE[key]
    db: float | None = None
    try:
        audio = MutagenFile(path, easy=True)
        if audio is not None and audio.tags:
            tags = audio.tags
            album = mode == "album"
            db = _parse(tags.get("replaygain_album_gain" if album else "replaygain_track_gain"))
            if db is None and album:
                db = _parse(tags.get("replaygain_track_gain"))
    except Exception:
        db = None
    _CACHE[key] = db
    return db


def scale_for(path: str, mode: str = "track") -> float:
    """Linear volume multiplier for the given mode (1.0 when unavailable)."""
    if mode not in ("track", "album") or not path:
        return 1.0
    db = gain_db(path, mode)
    if db is None:
        return 1.0
    db = max(-_MAX_DB, min(_MAX_DB, db))
    return 10 ** (db / 20.0)


def clear_cache() -> None:
    _CACHE.clear()
