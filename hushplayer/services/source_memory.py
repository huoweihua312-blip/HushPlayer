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
import re
import threading
import time
from pathlib import Path
from typing import Any

from ..core import paths
from ..core.logging_setup import get_logger
from ..online.models import payload_matches_source

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
def _norm(text: object) -> str:
    raw = str(text or "").lower()
    return "".join(ch for ch in raw if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


_BRACKETS = re.compile(r"[\(（\[【].*?[\)）\]】]")


def _loose(text: object) -> str:
    """Normalise a title while ignoring bracketed version suffixes."""
    return _norm(_BRACKETS.sub("", str(text or "")))


def track_key(source_id: str, remote_id: str) -> str:
    """Stable key for a remote track, independent of the local row id."""
    return f"r::{source_id}::{remote_id}"


def query_key(source_id: str, title: str, artist: str) -> str:
    return f"q::{source_id}::{_norm(title)}::{_norm(artist)}"


def _valid(entry: object) -> dict[str, Any] | None:
    if not isinstance(entry, dict) or not entry.get("source_id") or not entry.get("remote_id"):
        return None
    return dict(entry)


def track_alias(track: object) -> dict[str, Any] | None:
    """Look up a remembered source for ``track`` (accepts id or Track).

    Tries the local row id first, then (source_id, remote_id) and finally the
    normalised (source, title, artist) triple, so re-importing the same song
    from search results still hits the memory.
    """
    if track is None:
        return None
    if isinstance(track, str):
        entry = _valid(_read()["tracks"].get(track))
        return entry
    tid = str(getattr(track, "id", "") or "")
    source_id = str(getattr(track, "source_id", "") or "")
    remote_id = str(getattr(track, "remote_id", "") or "")
    title = str(getattr(track, "title", "") or "")
    artist = str(getattr(track, "artist", "") or "")
    data = _read()["tracks"]
    for key in (tid, track_key(source_id, remote_id) if remote_id else "", query_key(source_id, title, artist)):
        entry = _valid(data.get(key)) if key else None
        if entry is not None:
            return entry
    # Titles drift between the library row and the variant that actually
    # played ("晴天" vs "晴天 (Live)"), so fall back to a loose scan over the
    # same source instead of re-searching every time.
    loose_title = _loose(title)
    if loose_title:
        loose_artist = _loose(artist)
        best: dict[str, Any] | None = None
        for raw in data.values():
            entry = _valid(raw)
            if entry is None or _loose(entry.get("title")) != loose_title:
                continue
            if loose_artist:
                alias_artist = _loose(entry.get("artist"))
                if alias_artist and loose_artist not in alias_artist and alias_artist not in loose_artist:
                    continue
            if best is None or float(entry.get("saved_at") or 0) > float(best.get("saved_at") or 0):
                best = entry
        if best is not None:
            return best
    return None


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
    orig_source = str(getattr(track, "source_id", "") or "")
    orig_remote = str(getattr(track, "remote_id", "") or "")
    title = str(getattr(track, "title", "") or "")
    artist = str(getattr(track, "artist", "") or "")
    # Old aliases only kept the mapping and reused the *original* payload,
    # which is how a NetEase plugin once received a Kugou song id.  Persist the
    # matched track's own payload so a replay can rebuild an identity-consistent
    # request; only keep it when it provably belongs to this alias.
    raw = getattr(match, "raw", None)
    if isinstance(raw, dict) and raw and payload_matches_source(
        raw, source_id, str(getattr(match, "remote_id", "") or "")
    ):
        alias["raw"] = raw
    with _LOCK:
        data = _read()
        data["tracks"][track_id] = alias
        if orig_remote:
            data["tracks"][track_key(orig_source, orig_remote)] = alias
        data["tracks"][query_key(orig_source, title, artist)] = alias
        _prune(data)
        _write(data)


def forget_track(track: object) -> None:
    if not track:
        return
    if isinstance(track, str):
        keys = [track]
    else:
        keys = [str(getattr(track, "id", "") or "")]
        source_id = str(getattr(track, "source_id", "") or "")
        remote_id = str(getattr(track, "remote_id", "") or "")
        if remote_id:
            keys.append(track_key(source_id, remote_id))
        keys.append(query_key(source_id, str(getattr(track, "title", "") or ""), str(getattr(track, "artist", "") or "")))
    with _LOCK:
        data = _read()
        dirty = False
        for key in keys:
            if key and data["tracks"].pop(key, None) is not None:
                dirty = True
        if dirty:
            _write(data)


def mark_alias_failed(track: object) -> None:
    """Remember that a remembered alias just failed to resolve.

    One 404 is usually transient (the plugin rotates URLs), so the alias is
    kept for a retry; only after two failures in a row do we drop it.
    """
    if not track:
        return
    if isinstance(track, str):
        keys = [track]
    else:
        keys = [str(getattr(track, "id", "") or "")]
        source_id = str(getattr(track, "source_id", "") or "")
        remote_id = str(getattr(track, "remote_id", "") or "")
        if remote_id:
            keys.append(track_key(source_id, remote_id))
        keys.append(query_key(source_id, str(getattr(track, "title", "") or ""), str(getattr(track, "artist", "") or "")))
    with _LOCK:
        data = _read()
        dirty = False
        for key in keys:
            if not key:
                continue
            entry = data["tracks"].get(key)
            if not isinstance(entry, dict):
                continue
            entry["fail"] = int(entry.get("fail", 0) or 0) + 1
            entry["last_fail"] = time.time()
            dirty = True
            if entry["fail"] >= 2:
                data["tracks"].pop(key, None)
        if dirty:
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
    entry = _read().get("preferred")
    return str(entry.get("source_id") or "") if isinstance(entry, dict) else ""


def clear_preferred() -> None:
    """Forget the last working source (it stopped working)."""
    with _LOCK:
        data = _read()
        if data.pop("preferred", None) is not None:
            _write(data)

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
