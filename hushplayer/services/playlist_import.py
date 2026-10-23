"""Parse playlist files exported by other players (import step 2 of 3).

Supported: ``.m3u`` / ``.m3u8`` (including ``#EXTALB`` / ``#EXTART`` /
``#PLAYLIST``), ``.pls``, ``.csv``, ``.txt`` and Apple Music / iTunes
``Library.xml`` (plist). CSV column order is detected from the header, and the
text reader sniffs UTF-8 BOM, UTF-16 and GB18030 so Chinese exports just work.

Entries keep the file order; matching happens later (see ``playlist_matcher``).
"""

from __future__ import annotations

import csv
import plistlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SUPPORTED_SUFFIXES = (
    ".m3u",
    ".m3u8",
    ".pls",
    ".csv",
    ".txt",
    ".xml",
    ".plist",
)

_SEPARATORS = (" - ", " – ", " — ", "\t", "|", " / ")

_TITLE_KEYS = {"title", "name", "song", "track", "标题", "歌曲", "歌名", "曲名", "歌曲名"}
_ARTIST_KEYS = {"artist", "artists", "singer", "歌手", "艺术家", "艺人", "演唱者"}
_ALBUM_KEYS = {"album", "专辑", "唱片", "专辑名"}
_DURATION_KEYS = {"duration", "length", "time", "时长", "时间", "歌曲时长"}
_PATH_KEYS = {"path", "file", "location", "路径", "文件"}

_MASTER_PLAYLISTS = {"library", "音乐库", "资料库", "music", "最近添加", "recently added"}


@dataclass
class PlaylistEntry:
    title: str = ""
    artist: str = ""
    album: str = ""
    path: str = ""
    duration_ms: int = 0


@dataclass
class ParsedPlaylist:
    name: str = ""
    entries: list[PlaylistEntry] = field(default_factory=list)
    kind: str = "unknown"
    note: str = ""

    @property
    def total(self) -> int:
        return len(self.entries)


@dataclass
class ImportSummary:
    playlist_id: int = 0
    playlist_name: str = ""
    matched: int = 0
    total: int = 0
    unmatched: list[str] | None = None


def parse_playlist_file(path: str | Path) -> list[PlaylistEntry]:
    """Backwards-compatible entry point: entries only."""
    return parse_playlist(path).entries


def parse_playlist(path: str | Path) -> ParsedPlaylist:
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix in (".xml", ".plist"):
        return _parse_plist(file)
    text = _read_text(file)
    name = file.stem.strip() or "导入的歌单"
    if suffix == ".pls":
        return ParsedPlaylist(name, _parse_pls(text), "pls")
    if suffix == ".csv":
        return ParsedPlaylist(name, _parse_csv(text), "csv")
    if suffix in (".m3u", ".m3u8"):
        playlist_name, entries = _parse_m3u(text)
        return ParsedPlaylist(playlist_name or name, entries, "m3u")
    return ParsedPlaylist(name, _parse_lines(text), "txt")


def parse_playlist_text(text: str, *, name: str = "粘贴的歌单") -> ParsedPlaylist:
    """Paste-to-import fallback for platforms whose links need a login."""
    return ParsedPlaylist(name, _parse_lines(text), "txt")


# --------------------------------------------------------------------- readers
def _read_text(file: Path) -> str:
    raw = file.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", "")).strip()


def _parse_duration_ms(value: str) -> int:
    text = _clean(value)
    if not text:
        return 0
    if ":" in text:
        parts = [part for part in text.split(":") if part.strip()]
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            return 0
        seconds = 0.0
        for number in numbers:
            seconds = seconds * 60 + number
        return int(round(seconds * 1000))
    digits = re.sub(r"[^\d.]", "", text)
    if not digits:
        return 0
    try:
        number = float(digits)
    except ValueError:
        return 0
    # Values above an hour in seconds are millisecond exports (iTunes uses ms too).
    if number > 3600 or "ms" in text.lower():
        return int(round(number))
    return int(round(number * 1000))


def _parse_m3u(text: str) -> tuple[str, list[PlaylistEntry]]:
    entries: list[PlaylistEntry] = []
    pending: PlaylistEntry | None = None
    playlist_name = ""
    artist_tag = ""
    album_tag = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("#EXTM3U"):
            continue
        if upper.startswith("#PLAYLIST:"):
            playlist_name = _clean(line.split(":", 1)[1])
            continue
        if upper.startswith("#EXTART:"):
            artist_tag = _clean(line.split(":", 1)[1])
            continue
        if upper.startswith("#EXTALB:"):
            album_tag = _clean(line.split(":", 1)[1])
            continue
        if upper.startswith("#EXTINF"):
            if pending is not None and (pending.title or pending.path):
                entries.append(pending)
            pending = _entry_from_extinf(line)
            continue
        if line.startswith("#"):
            continue
        entry = pending or PlaylistEntry()
        pending = None
        entry.path = line
        if not entry.title:
            entry.title = Path(line.replace("\\", "/")).stem
        if artist_tag and not entry.artist:
            entry.artist = artist_tag
        if album_tag and not entry.album:
            entry.album = album_tag
        entries.append(entry)
    if pending is not None and (pending.title or pending.path):
        entries.append(pending)
    return playlist_name, [entry for entry in entries if entry.title or entry.path]


def _entry_from_extinf(line: str) -> PlaylistEntry:
    entry = PlaylistEntry()
    body = line.split(",", 1)[1] if "," in line else ""
    # The duration is everything between "#EXTINF:" and the first comma; it may
    # be plain seconds (225) or mm:ss / h:mm:ss (4:02), so delegate to the
    # shared parser instead of grabbing the first colon group.
    head = line.split(":", 1)[1] if ":" in line else ""
    duration_text = head.split(",", 1)[0].strip()
    entry.duration_ms = _parse_duration_ms(duration_text)
    entry.artist, entry.title = _split_artist_title(body)
    return entry


def _parse_pls(text: str) -> list[PlaylistEntry]:
    rows: dict[int, PlaylistEntry] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = _clean(value)
        match = re.match(r"(file|title|length)(\d+)$", key.strip().lower())
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
        elif kind == "length":
            entry.duration_ms = _parse_duration_ms(value)
    return [rows[index] for index in sorted(rows)]


def _header_index(cells: list[str]) -> dict[str, int] | None:
    lowered = [_clean(cell).casefold() for cell in cells]
    mapping: dict[str, int] = {}
    for index, cell in enumerate(lowered):
        for key in _TITLE_KEYS:
            if cell == key or cell.endswith(key):
                mapping.setdefault("title", index)
        for key in _ARTIST_KEYS:
            if cell == key or cell.endswith(key):
                mapping.setdefault("artist", index)
        for key in _ALBUM_KEYS:
            if cell == key or cell.endswith(key):
                mapping.setdefault("album", index)
        for key in _DURATION_KEYS:
            if cell == key or cell.endswith(key):
                mapping.setdefault("duration", index)
        for key in _PATH_KEYS:
            if cell == key or cell.endswith(key):
                mapping.setdefault("path", index)
    return mapping if "title" in mapping or "path" in mapping else None


def _parse_csv(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    rows = list(csv.reader(text.splitlines()))
    rows = [[_clean(cell) for cell in row] for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return entries
    mapping = _header_index(rows[0])
    if mapping is not None:
        rows = rows[1:]
    for cells in rows:
        if not any(cells):
            continue
        entry = PlaylistEntry()
        if mapping is not None:
            def cell(key: str) -> str:
                index = mapping.get(key)
                return cells[index] if index is not None and index < len(cells) else ""

            entry.title = cell("title")
            entry.artist = cell("artist")
            entry.album = cell("album")
            entry.path = cell("path")
            entry.duration_ms = _parse_duration_ms(cell("duration"))
            if not entry.title and entry.path:
                entry.title = Path(entry.path.replace("\\", "/")).stem
        elif len(cells) >= 3:
            entry.title, entry.artist, entry.album = cells[0], cells[1], cells[2]
        elif len(cells) == 2:
            entry.title, entry.artist = cells[0], cells[1]
        else:
            entry.artist, entry.title = _split_artist_title(cells[0])
        if entry.title or entry.path:
            entries.append(entry)
    return entries


def _parse_lines(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # Song lists copied out of players often look like "01. [03:12] 歌手 - 歌名".
        line = re.sub(r"^\s*\d{1,3}[.、)]\s*", "", line)
        stamp = re.match(r"^[\[(]?(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?[\])]?\s*", line)
        duration = 0
        if stamp:
            minutes, seconds, fraction = stamp.groups()
            duration = (int(minutes) * 60 + int(seconds)) * 1000
            if fraction:
                duration += int(fraction.ljust(3, "0")[:3])
            line = line[stamp.end() :].strip()
            if not line:
                continue
        if Path(line).suffix.lower() in (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".aac", ".ape"):
            entries.append(PlaylistEntry(path=line, title=Path(line).stem))
            continue
        artist, title = _split_artist_title(line)
        entries.append(PlaylistEntry(title=title, artist=artist, duration_ms=duration))
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


def _parse_plist(file: Path) -> ParsedPlaylist:
    try:
        payload = plistlib.loads(file.read_bytes())
    except Exception as exc:  # noqa: BLE001 - malformed exports are user input
        raise ValueError(f"无法解析 Apple Music 资料库文件：{exc}") from exc
    tracks = payload.get("Tracks") or {}
    playlists = payload.get("Playlists") or []
    if not isinstance(tracks, dict) or not isinstance(playlists, list):
        raise ValueError("这个 XML 不是 Apple Music / iTunes 的资料库格式。")

    wanted = file.stem.strip().casefold()
    chosen: dict | None = None
    fallback: dict | None = None
    for item in playlists:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        if name.casefold() == wanted:
            chosen = item
            break
        if name.casefold() in _MASTER_PLAYLISTS:
            continue
        if fallback is None and item.get("Playlist Items"):
            fallback = item
    chosen = chosen or fallback
    if chosen is None:
        # Exports that only contain the library master playlist are still
        # usable: import the whole library rather than failing outright.
        for item in playlists:
            if isinstance(item, dict) and item.get("Playlist Items"):
                chosen = item
                break
    if chosen is None:
        raise ValueError("资料库里没有找到可导入的歌单。")

    entries: list[PlaylistEntry] = []
    for item in chosen.get("Playlist Items") or []:
        track_id = item.get("Track ID") if isinstance(item, dict) else None
        track = tracks.get(track_id) or tracks.get(str(track_id))
        if not isinstance(track, dict):
            continue
        name = str(track.get("Name") or "").strip()
        artist = str(track.get("Artist") or "").strip()
        album = str(track.get("Album") or "").strip()
        duration = track.get("Total Time") or 0
        try:
            duration_ms = int(duration)
        except (TypeError, ValueError):
            duration_ms = 0
        if duration_ms and duration_ms < 1000:
            duration_ms *= 1000
        location = str(track.get("Location") or "").strip()
        path = _file_url_to_path(location)
        if not name and not path:
            continue
        entries.append(
            PlaylistEntry(
                title=name or Path(path).stem,
                artist=artist,
                album=album,
                duration_ms=duration_ms,
                path=path,
            )
        )
    name = str(chosen.get("Name") or file.stem).strip() or "Apple Music 歌单"
    return ParsedPlaylist(name, entries, "plist")


def _file_url_to_path(location: str) -> str:
    from urllib.parse import unquote, urlparse

    if not location:
        return ""
    parsed = urlparse(location)
    if parsed.scheme != "file":
        return ""
    path = unquote(parsed.path or "")
    if re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    return path.replace("/", "\\") if "\\" in path or re.match(r"^[A-Za-z]:", path) else path


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
    parsed = parse_playlist(file)
    name = parsed.name
    tracks, missing = match_tracks(parsed.entries, library)
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
        total=len(parsed.entries),
        unmatched=missing,
    )
