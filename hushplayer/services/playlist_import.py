"""Import playlists exported by other players.

Apple Music / iTunes, foobar2000, MusicBee, VLC and most desktop players can
export ``.m3u``/``.m3u8``/``.pls``; several Chinese players export ``.csv`` or a
plain ``歌手 - 歌名`` list. Matching is done against the local library first
(by path, then by title + artist) so importing never needs the network.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED_SUFFIXES = (".m3u", ".m3u8", ".pls", ".csv", ".txt")

_SEPARATORS = (" - ", " – ", " — ", "\t", "|")


@dataclass
class PlaylistEntry:
    title: str = ""
    artist: str = ""
    album: str = ""
    path: str = ""
    duration_ms: int = 0


@dataclass
class ImportSummary:
    playlist_id: int = 0
    playlist_name: str = ""
    matched: int = 0
    total: int = 0
    unmatched: list[str] | None = None


def parse_playlist_file(path: str | Path) -> list[PlaylistEntry]:
    file = Path(path)
    text = _read_text(file)
    suffix = file.suffix.lower()
    if suffix == ".pls":
        return _parse_pls(text)
    if suffix == ".csv":
        return _parse_csv(text)
    if suffix in (".m3u", ".m3u8"):
        return _parse_m3u(text)
    return _parse_lines(text)


# --------------------------------------------------------------------- readers
def _read_text(file: Path) -> str:
    raw = file.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _clean(value: str) -> str:
    return value.replace("\x00", "").strip()


def _parse_m3u(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    pending: PlaylistEntry | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith(("#EXTINF", "#EXTM3U")):
            # An #EXTINF without a following path still names a song; flush it
            # so hand-written or copy-pasted lists work too.
            if pending is not None and pending.title:
                entries.append(pending)
            pending = _entry_from_extinf(line) if line.upper().startswith("#EXTINF") else None
            continue
        if line.startswith("#"):
            continue
        entry = pending or PlaylistEntry()
        pending = None
        entry.path = line
        if not entry.title:
            entry.title = Path(line.replace("\\", "/")).stem
        entries.append(entry)
    if pending is not None and pending.title:
        entries.append(pending)
    return [entry for entry in entries if entry.title or entry.path]


def _entry_from_extinf(line: str) -> PlaylistEntry:
    entry = PlaylistEntry()
    body = line.split(",", 1)[1] if "," in line else ""
    seconds = re.search(r":(-?\d+)", line)
    if seconds:
        entry.duration_ms = max(0, int(seconds.group(1))) * 1000
    entry.artist, entry.title = _split_artist_title(body)
    return entry


def _parse_pls(text: str) -> list[PlaylistEntry]:
    rows: dict[int, PlaylistEntry] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = _clean(value)
        match = re.match(r"(file|title|length)(\d+)$", key)
        if not match:
            continue
        kind, index = match.group(1), int(match.group(2))
        entry = rows.setdefault(index, PlaylistEntry())
        if kind == "file":
            entry.path = value
            if not entry.title:
                entry.title = Path(value.replace("\\", "/")).stem
        elif kind == "title":
            entry.artist, entry.title = _split_artist_title(value)
        elif kind == "length" and value.isdigit():
            entry.duration_ms = int(value) * 1000
    return [rows[index] for index in sorted(rows)]


def _parse_csv(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    reader = csv.reader(text.splitlines())
    for row in reader:
        cells = [_clean(cell) for cell in row]
        if not any(cells):
            continue
        lowered = [cell.lower() for cell in cells]
        if any(cell in ("title", "标题", "歌曲", "歌名", "name") for cell in lowered[:1]):
            continue
        entry = PlaylistEntry()
        if len(cells) >= 3:
            entry.title, entry.artist, entry.album = cells[0], cells[1], cells[2]
        elif len(cells) == 2:
            entry.title, entry.artist = cells[0], cells[1]
        else:
            entry.title, entry.artist = _split_artist_title(cells[0])
        entries.append(entry)
    return entries


def _parse_lines(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    for line in text.splitlines():
        line = _clean(line)
        if not line or line.startswith("#"):
            continue
        if Path(line).suffix.lower() in (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac"):
            entry = PlaylistEntry(path=line, title=Path(line).stem)
        else:
            artist, title = _split_artist_title(line)
            entry = PlaylistEntry(title=title, artist=artist)
        entries.append(entry)
    return entries


def _split_artist_title(text: str) -> tuple[str, str]:
    text = _clean(text)
    if not text:
        return "", ""
    for separator in _SEPARATORS:
        if separator in text:
            left, right = text.split(separator, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                # "歌手 - 歌名" is the common shape; keep it that way.
                return left, right
    return "", text


# --------------------------------------------------------------------- import
def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").casefold())


def match_tracks(entries: Iterable[PlaylistEntry], library) -> tuple[list, list[str]]:
    """Resolve entries against the local library; returns (tracks, missing)."""
    tracks = []
    missing: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        track = None
        if entry.path:
            track = library.tracks.track_by_path(entry.path)
        if track is None and entry.title:
            candidates = [
                item
                for item in library.tracks.search_local(entry.title, limit=20)
                if item.kind == "local"
            ]
            track = _best_match(entry, candidates)
        if track is None:
            missing.append(entry.title or entry.path)
            continue
        if track.id in seen:
            continue
        seen.add(track.id)
        tracks.append(track)
    return tracks, missing


def _best_match(entry: PlaylistEntry, candidates):
    wanted_title = _normalise(entry.title)
    wanted_artist = _normalise(entry.artist)
    for track in candidates:
        if _normalise(track.title) != wanted_title:
            continue
        if wanted_artist and wanted_artist not in _normalise(track.artist):
            continue
        return track
    return None


def import_playlist_file(path: str | Path, library) -> ImportSummary:
    file = Path(path)
    entries = parse_playlist_file(file)
    name = file.stem.strip() or "导入的歌单"
    tracks, missing = match_tracks(entries, library)
    # Re-importing the same export should update that playlist, not stack
    # duplicates in the sidebar.
    playlist_id = 0
    for existing in library.playlists_all():
        if existing.name.strip().casefold() == name.casefold():
            playlist_id = existing.id
            break
    if not playlist_id:
        playlist_id = library.create_playlist(name)
    if tracks:
        library.playlists.add_tracks(playlist_id, [track.id for track in tracks])
    return ImportSummary(
        playlist_id=playlist_id,
        playlist_name=name,
        matched=len(tracks),
        total=len(entries),
        unmatched=missing,
    )
