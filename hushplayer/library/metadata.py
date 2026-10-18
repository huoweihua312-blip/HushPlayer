"""本地音频文件元数据读取（mutagen）。

只负责「把文件读成 Track」，不做数据库与 UI。
覆盖 MP3 / FLAC / WAV / M4A(AAC) / OGG / OPUS / WMA / AIFF 等常见格式，
并支持从内嵌封面或同目录图片得到专辑封面字节。
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from ..core.logging_setup import get_logger
from ..model.track import Track, album_key, artist_key, local_track_id

log = get_logger("metadata")

try:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4
    from mutagen.mp4 import MP4Tags
except Exception:  # pragma: no cover - mutagen 是必需依赖
    MutagenFile = None  # type: ignore[assignment]
    MP4Tags = ()  # type: ignore[assignment]
    ID3 = ()  # type: ignore[assignment]
    MP4 = ()  # type: ignore[assignment]

AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wma",
    ".aiff",
    ".aif",
    ".ape",
    ".wv",
    ".mpc",
    ".dsf",
    ".dff",
}

COVER_NAMES = (
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "folder.jpg",
    "folder.jpeg",
    "folder.png",
    "front.jpg",
    "front.png",
    "album.jpg",
    "albumart.jpg",
    "albumartsmall.jpg",
)

_ID3_MAP = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "albumartist": "TPE2",
    "date": "TDRC",
    "tracknumber": "TRCK",
    "discnumber": "TPOS",
    "genre": "TCON",
    "composer": "TCOM",
}

_VORBIS_MAP = {
    "title": ("title",),
    "artist": ("artist",),
    "album": ("album",),
    "albumartist": ("albumartist", "album artist", "album_artist"),
    "date": ("date", "year"),
    "tracknumber": ("tracknumber", "track"),
    "discnumber": ("discnumber", "disc"),
    "genre": ("genre",),
}

_MP4_MAP = {
    "title": ("\xa9nam",),
    "artist": ("\xa9ART",),
    "album": ("\xa9alb",),
    "albumartist": ("aART",),
    "date": ("\xa9day",),
    "genre": ("\xa9gen",),
}


class UnsupportedAudio(Exception):
    pass


def is_audio_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def _first(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value)


def _tag(tags, kind: str, key: str) -> str:
    if tags is None:
        return ""
    try:
        if kind == "id3":
            frame = tags.get(_ID3_MAP.get(key, ""))
            if frame is None:
                return ""
            text = getattr(frame, "text", None)
            return _first(text) if text is not None else str(frame)
        if kind == "vorbis":
            for candidate in _VORBIS_MAP.get(key, ()):
                if candidate in tags:
                    return _first(tags.get(candidate))
            return ""
        if kind == "mp4":
            for candidate in _MP4_MAP.get(key, ()):
                if candidate in tags:
                    return _first(tags.get(candidate))
            return ""
        if kind == "asf":
            for candidate in (key, key.upper()):
                if candidate in tags:
                    return _first(tags.get(candidate))
    except Exception:
        return ""
    return ""


def _kind_of(audio) -> str:
    """判定标签族：id3 / mp4 / asf / vorbis。

    WAV 与 AIFF 的标签类（``mutagen.wave._WaveID3`` / ``mutagen.aiff._IFFID3``）
    继承自 ``ID3``，但模块名里没有 "id3"，所以必须用 isinstance 判断，
    否则会被误判成 vorbis 而读不到标题。
    """
    tags = getattr(audio, "tags", None)
    if isinstance(tags, ID3) or isinstance(audio, ID3):
        return "id3"
    if isinstance(audio, MP4) or isinstance(tags, MP4Tags):
        return "mp4"
    if tags is not None:
        module = type(tags).__module__
        if "asf" in module:
            return "asf"
        if "mp4" in module:
            return "mp4"
    return "vorbis"


def _to_int(value: str, default: int = 0) -> int:
    if not value:
        return default
    text = str(value).strip()
    for separator in ("/", "-", " "):
        if separator in text:
            text = text.split(separator)[0]
            break
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _year(value: str) -> int:
    text = (value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return _to_int(text)


def read_track(path: str | Path, *, with_cover: bool = True) -> tuple[Track, bytes | None, str]:
    """读取单个文件，返回 (Track, 封面字节, 封面扩展名)。"""
    path = Path(path)
    if MutagenFile is None:
        raise UnsupportedAudio("mutagen 不可用")
    try:
        audio = MutagenFile(str(path))
    except Exception as exc:  # mutagen 对损坏文件会抛各种异常
        raise UnsupportedAudio(str(exc)) from exc
    if audio is None:
        raise UnsupportedAudio("无法识别的音频格式")

    info = getattr(audio, "info", None)
    duration_ms = int(round(float(getattr(info, "length", 0.0) or 0.0) * 1000))
    bitrate = int(getattr(info, "bitrate", 0) or 0)
    sample_rate = int(getattr(info, "sample_rate", 0) or 0)
    channels = int(getattr(info, "channels", 0) or 0)
    tags = getattr(audio, "tags", None)
    kind = _kind_of(audio)

    title = _tag(tags, kind, "title").strip()
    artist = _tag(tags, kind, "artist").strip()
    album = _tag(tags, kind, "album").strip()
    album_artist = _tag(tags, kind, "albumartist").strip() or artist
    genre = _tag(tags, kind, "genre").strip()
    track_no = _to_int(_tag(tags, kind, "tracknumber"))
    disc_no = _to_int(_tag(tags, kind, "discnumber"))
    year = _year(_tag(tags, kind, "date"))

    if not title:
        title = path.stem
        # 常见命名："01 - 歌手 - 标题"
        name = path.stem
        for separator in (" - ", "-"):
            if separator in name:
                parts = [part.strip() for part in name.split(separator)]
                if len(parts) >= 2 and parts[0].isdigit():
                    parts = parts[1:]
                if len(parts) >= 2 and not artist:
                    artist = parts[0]
                if parts:
                    title = parts[-1]
                break
    if not artist:
        parent = path.parent.name
        artist = "" if parent.lower() in {"music", "音乐", "downloads"} else ""

    try:
        stat = path.stat()
        size = stat.st_size
        modified = stat.st_mtime
    except OSError:
        size = 0
        modified = 0.0

    cover_bytes: bytes | None = None
    cover_ext = ".jpg"
    if with_cover:
        cover_bytes, cover_ext = extract_cover(audio, path)

    codec = Path(path).suffix.lower().lstrip(".")
    track = Track(
        id=local_track_id(str(path)),
        kind="local",
        title=title,
        artist=artist,
        album=album,
        album_artist=album_artist,
        duration_ms=duration_ms,
        path=str(path),
        track_no=track_no,
        disc_no=disc_no,
        year=year,
        genre=genre,
        bitrate=bitrate,
        sample_rate=sample_rate,
        codec=codec,
        size=size,
        added_at=time.time(),
        modified_at=modified,
        album_id=album_key(album, album_artist) if album else "",
        artist_id=artist_key(artist) if artist else "",
        raw={
            "channels": channels,
            "container": type(audio).__name__,
        },
    )
    return track, cover_bytes, cover_ext


def extract_cover(audio, path: Path) -> tuple[bytes | None, str]:
    tags = getattr(audio, "tags", None)

    # FLAC
    try:
        pictures = getattr(audio, "pictures", None)
        if pictures:
            picture = pictures[0]
            return bytes(picture.data), _ext_from_mime(getattr(picture, "mime", ""))
    except Exception:
        pass

    # ID3 APIC
    try:
        if tags is not None and hasattr(tags, "getall"):
            frames = tags.getall("APIC")
            if frames:
                frame = frames[0]
                return bytes(frame.data), _ext_from_mime(getattr(frame, "mime", ""))
    except Exception:
        pass

    # MP4 covr
    try:
        if tags is not None and "covr" in tags:
            values = tags["covr"]
            if values:
                fmt = getattr(values[0], "imageformat", None)
                ext = ".png" if fmt == 14 else ".jpg"
                return bytes(values[0]), ext
    except Exception:
        pass

    # Vorbis metadata_block_picture
    try:
        if tags is not None and "metadata_block_picture" in tags:
            data = base64.b64decode(tags["metadata_block_picture"][0])
            picture = Picture(data)
            return bytes(picture.data), _ext_from_mime(getattr(picture, "mime", ""))
    except Exception:
        pass

    # 同目录图片
    folder = find_folder_cover(path.parent)
    if folder is not None:
        try:
            return folder.read_bytes(), folder.suffix.lower()
        except OSError:
            return None, ".jpg"
    return None, ".jpg"


def _ext_from_mime(mime: str) -> str:
    mime = (mime or "").lower()
    if "png" in mime:
        return ".png"
    if "webp" in mime:
        return ".webp"
    if "gif" in mime:
        return ".gif"
    return ".jpg"


_folder_cover_cache: dict[str, Path | None] = {}


def find_folder_cover(folder: Path) -> Path | None:
    key = str(folder).casefold()
    if key in _folder_cover_cache:
        return _folder_cover_cache[key]
    result: Path | None = None
    try:
        entries = {entry.name.casefold(): entry for entry in os.scandir(folder) if entry.is_file()}
    except OSError:
        entries = {}
    for name in COVER_NAMES:
        entry = entries.get(name)
        if entry is not None:
            result = Path(entry.path)
            break
    if result is None:
        for entry in entries.values():
            if entry.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                stem = Path(entry.name).stem.lower()
                if "cover" in stem or "front" in stem or "folder" in stem:
                    result = Path(entry.path)
                    break
    _folder_cover_cache[key] = result
    return result


def clear_folder_cache() -> None:
    _folder_cover_cache.clear()


def probe_duration(path: str | Path) -> int:
    """轻量读取时长（用于缓存文件识别）。"""
    try:
        audio = MutagenFile(str(path))
        info = getattr(audio, "info", None)
        return int(round(float(getattr(info, "length", 0.0) or 0.0) * 1000))
    except Exception:
        return 0
