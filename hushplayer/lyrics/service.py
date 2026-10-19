"""Lyrics resolution pipeline.

Order of preference for a track:

1. a local file the user explicitly bound to the track (``lyric_bindings``)
2. a sidecar ``.lrc`` / ``.txt`` next to the audio file
3. lyrics embedded in the audio tags (ID3 USLT, Vorbis LYRICS, MP4 ©lyr)
4. the persistent lyrics cache (already fetched earlier)
5. the online source that provided the track (``getLyric``)
6. LRCLIB for anything still missing (local files included)
7. give up with ``status="none"`` / ``"instrumental"``

Parsing lives in :mod:`hushplayer.lyrics.parser`; this module only fetches,
caches and decides precedence.  Network work happens on worker threads, file
parsing is fast enough to stay on the caller's thread.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core import paths
from ..core.logging_setup import get_logger
from ..lyrics import parser as lyric_parser
from ..model.lyrics import EMPTY_DOCUMENT, LyricDocument
from ..model.track import Track
from ..online.client import OnlineSourceClient
from ..store.repository import LyricBindingRepository, MetaStore, TrackRepository

log = get_logger("lyrics.service")

LRCLIB_SEARCH = "https://lrclib.net/api/search"
LRCLIB_UA = "HushPlayer/1.0 (desktop music player; lyrics lookup)"
SIDECAR_SUFFIXES = (".lrc", ".LRC", ".txt", ".yrc", ".qrc", ".krc")

_USER_AGENT = "HushPlayer/1.0 (desktop music player; lyrics lookup)"

STATUS_OK = "ok"
STATUS_NONE = "none"
STATUS_INSTRUMENTAL = "instrumental"
STATUS_ERROR = "error"
STATUS_LOADING = "loading"


@dataclass(slots=True)
class LyricsResult:
    track_id: str
    document: LyricDocument
    status: str
    provider: str = ""
    message: str = ""


def _network_error(exc: Exception) -> str:
    text = str(exc)
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "网络超时，请稍后重试"
    return f"搜索失败：{type(exc).__name__}"


def _cache_file(track_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", track_id)[:80]
    return os.path.join(str(paths.lyrics_cache_dir()), f"{safe}.json")


def _read_text(path: str) -> str:
    data = b""
    try:
        with open(path, "rb") as handle:
            data = handle.read(600_000)
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _write_cache(track_id: str, text: str, *, provider: str, translation: str = "") -> None:
    try:
        os.makedirs(str(paths.lyrics_cache_dir()), exist_ok=True)
        payload = {
            "track_id": track_id,
            "text": text,
            "translation": translation,
            "provider": provider,
            "fetched_at": time.time(),
        }
        target = _cache_file(track_id)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp, target)
    except OSError:
        log.debug("cannot write lyrics cache for %s", track_id)


def _read_cache(track_id: str) -> tuple[str, str, str] | None:
    path = _cache_file(track_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    text = str(payload.get("text") or "")
    if not text.strip():
        return None
    return text, str(payload.get("translation") or ""), str(payload.get("provider") or "cache")


def find_sidecar(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    stem = os.path.splitext(path)[0]
    for suffix in SIDECAR_SUFFIXES:
        candidate = stem + suffix
        if os.path.isfile(candidate):
            return candidate
    # Some libraries keep lyrics in a sibling "Lyrics" folder.
    folder = os.path.dirname(path)
    for name in ("Lyrics", "lyrics", "歌词"):
        candidate_dir = os.path.join(folder, name)
        if not os.path.isdir(candidate_dir):
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        for suffix in SIDECAR_SUFFIXES:
            candidate = os.path.join(candidate_dir, base + suffix)
            if os.path.isfile(candidate):
                return candidate
    return ""


def find_translation_sidecar(path: str) -> str:
    """查找与音频同名的翻译歌词文件（如 ``歌名.trans.lrc`` / ``歌名.zh.lrc``）。"""
    if not path:
        return ""
    stem = os.path.splitext(path)[0]
    suffixes = (".trans.lrc", ".translation.lrc", ".zh.lrc", ".trans.txt", ".translation.txt")
    for suffix in suffixes:
        candidate = stem + suffix
        if os.path.isfile(candidate):
            return candidate
    folder = os.path.dirname(path)
    base = os.path.splitext(os.path.basename(path))[0]
    for name in ("Lyrics", "lyrics", "歌词"):
        candidate_dir = os.path.join(folder, name)
        if not os.path.isdir(candidate_dir):
            continue
        for suffix in suffixes:
            candidate = os.path.join(candidate_dir, base + suffix)
            if os.path.isfile(candidate):
                return candidate
    return ""


def embedded_lyrics(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        from mutagen import File as MutagenFile
    except Exception:  # pragma: no cover
        return ""
    try:
        audio = MutagenFile(path)
    except Exception:
        return ""
    if audio is None:
        return ""
    tags = getattr(audio, "tags", None)
    if tags is None:
        return ""
    try:
        if hasattr(tags, "getall"):
            frames = tags.getall("USLT")
            if frames:
                return str(frames[0].text or "")
        for key in ("lyrics", "LYRICS", "unsyncedlyrics", "UNSYNCEDLYRICS"):
            if key in tags:
                value = tags.get(key)
                if isinstance(value, (list, tuple)):
                    return str(value[0]) if value else ""
                return str(value)
        for key in ("\xa9lyr",):
            if key in tags:
                value = tags.get(key)
                if isinstance(value, (list, tuple)):
                    return str(value[0]) if value else ""
        # synchronized lyrics: SYLT frames store (text, time) pairs
        if hasattr(tags, "getall"):
            frames = tags.getall("SYLT")
            if frames:
                frame = frames[0]
                lines = []
                for text, millis in getattr(frame, "text", []) or []:
                    total = int(millis)
                    minutes, rest = divmod(total, 60_000)
                    seconds, ms = divmod(rest, 1000)
                    lines.append(f"[{minutes:02d}:{seconds:02d}.{ms:03d}]{text}")
                return "\n".join(lines)
    except Exception:
        log.debug("embedded lyrics parse failed for %s", path)
    return ""


class _LrclibJob(QRunnable):
    """Fetch synced lyrics from LRCLIB on a worker thread."""

    def __init__(self, service: "LyricsService", track: Track) -> None:
        super().__init__()
        self.service = service
        self.track = track

    def run(self) -> None:  # pragma: no cover - exercised through the UI
        result = self._fetch()
        self.service._on_lrclib_result(self.track, result)

    def _fetch(self) -> dict[str, Any] | None:
        try:
            import requests
        except Exception:
            return None
        params = {
            "track_name": self.track.title,
            "artist_name": self.track.artist,
        }
        if self.track.album:
            params["album_name"] = self.track.album
        try:
            response = requests.get(
                LRCLIB_SEARCH,
                params=params,
                timeout=8,
                headers={"User-Agent": LRCLIB_UA, "Accept": "application/json"},
            )
            if response.status_code != 200:
                log.info("lrclib status %s", response.status_code)
                return None
            payload = response.json()
        except Exception as exc:
            log.info("lrclib failed: %s", exc)
            return None
        if not isinstance(payload, list) or not payload:
            return None
        best: dict[str, Any] | None = None
        best_score = -1
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            synced = entry.get("syncedLyrics") or ""
            plain = entry.get("plainLyrics") or ""
            if not synced and not plain:
                continue
            score = 0
            if synced:
                score += 3
            if (entry.get("trackName") or "").casefold() == self.track.title.casefold():
                score += 2
            duration = float(entry.get("duration") or 0) * 1000
            if self.track.duration_ms and duration:
                if abs(duration - self.track.duration_ms) <= 3000:
                    score += 2
                elif abs(duration - self.track.duration_ms) <= 8000:
                    score += 1
            if bool(entry.get("instrumental")):
                score += 1
            if score > best_score:
                best = entry
                best_score = score
        return best


@dataclass(frozen=True)
class LyricsCandidate:
    """A lyric search hit (LRCLIB entry normalised for the picker)."""

    id: int
    title: str
    artist: str
    album: str
    duration_ms: int
    synced: str
    plain: str

    @property
    def duration_text(self) -> str:
        seconds = max(0, self.duration_ms // 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"

    @property
    def has_timing(self) -> bool:
        return bool(self.synced.strip())


class _LyricsSearchJob(QRunnable):
    def __init__(self, service: "LyricsService", query: str, token: int) -> None:
        super().__init__()
        self._service = service
        self._query = query
        self._token = token

    def run(self) -> None:  # pragma: no cover - network
        candidates: list[LyricsCandidate] = []
        error = ""
        try:
            response = requests.get(
                LRCLIB_SEARCH,
                params={"q": self._query},
                headers={"User-Agent": LRCLIB_UA, "Accept": "application/json"},
                timeout=(6, 12),
            )
            response.raise_for_status()
            for entry in response.json() or []:
                try:
                    candidates.append(
                        LyricsCandidate(
                            id=int(entry.get("id") or 0),
                            title=str(entry.get("trackName") or entry.get("name") or ""),
                            artist=str(entry.get("artistName") or ""),
                            album=str(entry.get("albumName") or ""),
                            duration_ms=int(float(entry.get("duration") or 0) * 1000),
                            synced=str(entry.get("syncedLyrics") or ""),
                            plain=str(entry.get("plainLyrics") or ""),
                        )
                    )
                except Exception:
                    continue
        except Exception as exc:  # noqa: BLE001
            error = _network_error(exc)
        self._service._on_search_done(self._token, candidates, error)  # noqa: SLF001


class LyricsService(QObject):
    resolved = Signal(object)  # LyricsResult
    search_finished = Signal(list)  # list[LyricsCandidate]
    search_failed = Signal(str)

    def __init__(
        self,
        tracks: TrackRepository,
        bindings: LyricBindingRepository,
        meta: MetaStore,
        client: OnlineSourceClient | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._bindings = bindings
        self._meta = meta
        self._client = client
        self._cache: dict[str, LyricsResult] = {}
        self._offsets: dict[str, int] = {}
        self._tag_offsets: dict[str, int] = {}
        self._pending: str = ""
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._generation = 0
        self._search_token = 0
        self._search_pool = QThreadPool(self)
        self._search_pool.setMaxThreadCount(1)

    # ------------------------------------------------------------------ api
    def search(self, query: str) -> None:
        """Search LRCLIB by free text; emits search_finished/search_failed."""
        query = query.strip()
        if not query:
            self.search_failed.emit("请输入歌曲名或歌手名")
            return
        self._search_token += 1
        self._search_pool.start(_LyricsSearchJob(self, query, self._search_token))

    def _on_search_done(
        self, token: int, candidates: list[LyricsCandidate], error: str
    ) -> None:
        if token != self._search_token:
            return
        if error:
            self.search_failed.emit(error)
            return
        self.search_finished.emit(candidates)

    def apply_candidate(self, track: Track, candidate: LyricsCandidate) -> LyricsResult:
        """Use a searched lyric as this track's lyrics and persist it."""
        if candidate.synced.strip():
            text = candidate.synced
            has_timing = True
        else:
            text = candidate.plain
            has_timing = False
        provider = f"LRCLIB · {candidate.artist}".strip(" ·")
        document = lyric_parser.parse(
            text,
            source="lrclib",
            provider=provider,
            duration_ms=track.duration_ms,
            plain=not has_timing,
        )
        document.offset_ms = self.offset_for(track) + self._tag_offsets.get(track.id, 0)
        result = LyricsResult(
            track_id=track.id,
            document=document,
            status=STATUS_NONE if document.is_empty() else STATUS_OK,
            provider="lrclib",
            message="手动选择",
        )
        self._cache[track.id] = result
        _write_cache(track.id, text, provider="lrclib-manual")
        self.resolved.emit(result)
        return result

    def offset_for(self, track: Track) -> int:
        if track.id in self._offsets:
            return self._offsets[track.id]
        return int(track.lyrics_offset_ms or 0)

    def set_offset(self, track: Track, offset_ms: int) -> LyricDocument | None:
        offset_ms = max(-60_000, min(60_000, int(offset_ms)))
        self._offsets[track.id] = offset_ms
        track.lyrics_offset_ms = offset_ms
        try:
            self._tracks.update_lyrics_offset(track.id, offset_ms)
        except Exception:
            log.debug("cannot persist lyrics offset for %s", track.id)
        cached = self._cache.get(track.id)
        if cached is not None:
            cached.document.offset_ms = offset_ms + self._tag_offsets.get(track.id, 0)
            return cached.document
        return None

    def cached(self, track_id: str) -> LyricsResult | None:
        return self._cache.get(track_id)

    def invalidate(self, track_id: str = "") -> None:
        if track_id:
            self._cache.pop(track_id, None)
            try:
                os.remove(_cache_file(track_id))
            except OSError:
                pass
        else:
            self._cache.clear()

    def request(self, track: Track, *, force: bool = False) -> LyricsResult:
        """Resolve lyrics for ``track``; emits ``resolved`` when done."""
        if track is None:
            return LyricsResult("", EMPTY_DOCUMENT, STATUS_NONE)
        if not force and track.id in self._cache:
            cached = self._cache[track.id]
            self.resolved.emit(cached)
            return cached

        self._generation += 1
        generation = self._generation

        # 1. manual binding
        bound_path, bound_source = "", ""
        try:
            bound_path, bound_source = self._bindings.get(track.id)
        except Exception:
            pass
        if bound_path and os.path.isfile(bound_path):
            text = _read_text(bound_path)
            if text.strip():
                result = self._finish(track, text, provider=f"local:{os.path.basename(bound_path)}",
                                     source=bound_source or "manual")
                self.resolved.emit(result)
                return result

        # 2/3. sidecar + embedded (local tracks only)
        if track.is_local and track.path:
            sidecar = find_sidecar(track.path)
            if sidecar:
                text = _read_text(sidecar)
                if text.strip():
                    result = self._finish(track, text, provider="local", source="local")
                    translation_path = find_translation_sidecar(track.path)
                    if translation_path and result.document is not None and result.document.lines:
                        translated = _read_text(translation_path)
                        if translated.strip():
                            lyric_parser.attach_translation(result.document, translated)
                            self._cache[track.id] = result
                    self.resolved.emit(result)
                    return result
            embedded = embedded_lyrics(track.path)
            if embedded.strip():
                result = self._finish(track, embedded, provider="embedded", source="embedded")
                self.resolved.emit(result)
                return result

        # 4. persistent cache
        if not force:
            cached_raw = _read_cache(track.id)
            if cached_raw is not None:
                text, translation, provider = cached_raw
                result = self._finish(track, text, provider=provider, source="cache",
                                     translation=translation, store_cache=False)
                self.resolved.emit(result)
                return result

        # 5. online source lyrics
        if track.is_online and track.source_id and self._client is not None:
            self._request_source_lyrics(track, generation)
            return LyricsResult(track.id, EMPTY_DOCUMENT, STATUS_LOADING, "source")

        # 6. LRCLIB
        self._request_lrclib(track, generation)
        return LyricsResult(track.id, EMPTY_DOCUMENT, STATUS_LOADING, "lrclib")

    def bind_local(self, track: Track, path: str) -> LyricsResult:
        text = _read_text(path)
        if not text.strip():
            result = LyricsResult(track.id, EMPTY_DOCUMENT, STATUS_ERROR, "local",
                                  "无法读取歌词文件")
            self.resolved.emit(result)
            return result
        try:
            self._bindings.set(track.id, path, "manual")
        except Exception:
            log.debug("cannot store lyric binding for %s", track.id)
        result = self._finish(track, text, provider=f"local:{os.path.basename(path)}",
                              source="local", force_store=True)
        self.resolved.emit(result)
        return result

    # ------------------------------------------------------------- internals
    def _request_source_lyrics(self, track: Track, generation: int) -> None:
        def on_response(response: dict) -> None:
            if generation != self._generation:
                return
            if not response.get("ok"):
                log.info("source lyrics failed: %s", response.get("error"))
                self._request_lrclib(track, generation)
                return
            data = response.get("data") or {}
            text = ""
            if isinstance(data, dict):
                for key in ("rawLrc", "lyric", "lyrics", "text", "content"):
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        text = value
                        break
                if not text and isinstance(data.get("raw"), str):
                    text = data["raw"]
            if not text.strip():
                self._request_lrclib(track, generation)
                return
            translation = ""
            if isinstance(data, dict):
                for key in ("translation", "trans", "krcTranslation"):
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        translation = value
                        break
            provider = track.source_name or "online"
            result = self._finish(track, text, provider=provider, source="online",
                                  translation=translation)
            self.resolved.emit(result)

        try:
            self._client.get_lyric(track.source_id, track.raw, on_response)
        except Exception as exc:  # pragma: no cover - client always exists here
            log.info("cannot request source lyrics: %s", exc)
            self._request_lrclib(track, generation)

    def _request_lrclib(self, track: Track, generation: int) -> None:
        job = _LrclibJob(self, track)
        job.setAutoDelete(True)
        self._pending = track.id
        self._pool.start(job)

    def _on_lrclib_result(self, track: Track, entry: dict[str, Any] | None) -> None:
        if entry is None:
            result = LyricsResult(track.id, EMPTY_DOCUMENT, STATUS_NONE, "none", "暂无歌词")
            self.resolved.emit(result)
            return
        synced = str(entry.get("syncedLyrics") or "")
        plain = str(entry.get("plainLyrics") or "")
        text = synced or plain
        if not text.strip():
            result = LyricsResult(track.id, EMPTY_DOCUMENT, STATUS_NONE, "none", "暂无歌词")
            self.resolved.emit(result)
            return
        result = self._finish(
            track,
            text,
            provider="LRCLIB",
            source="lrclib",
            instrumental=bool(entry.get("instrumental")),
            plain=not synced,
        )
        self.resolved.emit(result)

    def _finish(
        self,
        track: Track,
        text: str,
        *,
        provider: str,
        source: str,
        translation: str = "",
        instrumental: bool = False,
        plain: bool = False,
        store_cache: bool = True,
        force_store: bool = False,
    ) -> LyricsResult:
        try:
            document = lyric_parser.parse(
                text,
                source=source,
                provider=provider,
                duration_ms=track.duration_ms,
                plain=plain,
                instrumental=instrumental,
            )
        except Exception as exc:
            log.exception("lyrics parse failed")
            return LyricsResult(track.id, EMPTY_DOCUMENT, STATUS_ERROR, provider, str(exc))
        if translation.strip():
            try:
                lyric_parser.attach_translation(document, translation)
            except Exception:
                log.debug("translation attach failed")
        # ``offset_ms`` in the document may come from an LRC ``[offset:]`` tag;
        # the user calibration is applied on top of it.
        self._tag_offsets[track.id] = int(document.offset_ms or 0)
        document.offset_ms = self._tag_offsets[track.id] + self.offset_for(track)
        if document.is_empty() and not document.kind == "instrumental":
            result = LyricsResult(track.id, document, STATUS_NONE, provider, "暂无歌词")
            self._cache[track.id] = result
            return result
        if store_cache or force_store:
            _write_cache(track.id, text, provider=provider, translation=translation)
        status = STATUS_INSTRUMENTAL if document.kind == "instrumental" else STATUS_OK
        result = LyricsResult(track.id, document, status, provider)
        self._cache[track.id] = result
        return result

    # --------------------------------------------------------------- cleanup
    def shutdown(self) -> None:
        try:
            self._pool.clear()
        except Exception:
            pass


__all__ = [
    "LyricsResult",
    "LyricsService",
    "STATUS_ERROR",
    "STATUS_INSTRUMENTAL",
    "STATUS_LOADING",
    "STATUS_NONE",
    "STATUS_OK",
    "embedded_lyrics",
    "find_sidecar",
]
