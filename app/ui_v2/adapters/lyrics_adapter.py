"""Bridge real and deterministic lyric documents into the shared V2 canvas."""

from __future__ import annotations

from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from app.models.media_item import MediaItem
from app.ui_v2.mock.lyrics_factory import create_mock_document
from app.ui_v2.models.lyric_line import LyricLine, LyricSegment
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.lyrics_state import LyricsState
from app.ui_v2.models.track import Track

if TYPE_CHECKING:
    from app.services.online_lyrics_service import OnlineLyricsService


_CONFIRMED_UNPLAYABLE_STATES = frozenset(
    {
        "unavailable",
        "source_unavailable",
        "source-unavailable",
        "resolve_failed",
        "resolve-failed",
        "permission_denied",
        "permission-denied",
        "playback_error",
        "playback-error",
    }
)

_LRC_TIME_PATTERN = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


def _timestamp_ms(match: re.Match[str]) -> int:
    minute = int(match.group(1))
    second = int(match.group(2))
    fraction = match.group(3) or "0"
    if len(fraction) == 1:
        milliseconds = int(fraction) * 100
    elif len(fraction) == 2:
        milliseconds = int(fraction) * 10
    else:
        milliseconds = int(fraction[:3])
    return minute * 60_000 + second * 1_000 + milliseconds


def _character_segments(text: str, start_ms: int, end_ms: int) -> tuple[LyricSegment, ...]:
    characters = tuple(text)
    if not characters:
        return ()
    duration = max(len(characters), int(end_ms) - int(start_ms))
    segments: list[LyricSegment] = []
    for index, character in enumerate(characters):
        segment_start = int(start_ms) + round((duration * index) / len(characters))
        segment_end = int(start_ms) + round((duration * (index + 1)) / len(characters))
        segments.append(
            LyricSegment(
                character,
                segment_start,
                max(segment_start + 1, segment_end),
                "character",
            )
        )
    return tuple(segments)


def _parse_lrc_lines(text: str) -> list[tuple[int, str]]:
    parsed: list[tuple[int, int, str]] = []
    order = 0
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matches = list(_LRC_TIME_PATTERN.finditer(line))
        if not matches:
            continue
        lyric_text = _LRC_TIME_PATTERN.sub("", line).strip() or "♪"
        for match in matches:
            parsed.append((_timestamp_ms(match), order, lyric_text))
            order += 1
    parsed.sort(key=lambda item: (item[0], item[1]))
    return [(start_ms, lyric_text) for start_ms, _order, lyric_text in parsed]


def _plain_lyrics_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _document_from_text(track: Track, text: str, source_type: str) -> LyricsDocument | None:
    """Convert provider text into the value object consumed by the V2 canvas."""

    timed_lines = _parse_lrc_lines(text)
    if timed_lines:
        lines: list[LyricLine] = []
        for index, (start_ms, lyric_text) in enumerate(timed_lines):
            next_start = (
                timed_lines[index + 1][0]
                if index + 1 < len(timed_lines)
                else None
            )
            if next_start is not None and next_start > start_ms:
                end_ms = next_start
            elif track.duration_ms and track.duration_ms > start_ms:
                end_ms = int(track.duration_ms)
            else:
                end_ms = start_ms + max(2_500, len(lyric_text) * 180)
            lines.append(
                LyricLine(
                    id=f"{track.stable_identity}:line:{index}",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=lyric_text,
                    language="plain",
                    segments=_character_segments(lyric_text, start_ms, end_ms),
                )
            )
        return LyricsDocument(
            track_id=track.stable_identity,
            title=track.title,
            artist=track.artist,
            source_type=source_type,
            lines=tuple(lines),
            sync_mode="line",
        )

    plain_lines = _plain_lyrics_lines(text)
    if not plain_lines:
        return None
    interval = max(
        2_500,
        round((track.duration_ms or len(plain_lines) * 4_000) / len(plain_lines)),
    )
    lines = tuple(
        LyricLine(
            id=f"{track.stable_identity}:plain:{index}",
            start_ms=index * interval,
            end_ms=(index + 1) * interval,
            text=lyric_text,
            language="plain",
        )
        for index, lyric_text in enumerate(plain_lines)
    )
    return LyricsDocument(
        track_id=track.stable_identity,
        title=track.title,
        artist=track.artist,
        source_type=source_type,
        lines=lines,
        sync_mode="plain",
    )


class LyricsAdapter(QObject):
    """Maps mock playback time to lyric state through cached timed indices."""

    document_changed = Signal(object)
    state_changed = Signal(object)
    active_line_changed = Signal(object)
    active_segment_changed = Signal(object, int, float)
    position_changed = Signal(int)
    offset_changed = Signal(int)
    display_options_changed = Signal(object)
    seek_requested = Signal(int)

    _SCENARIOS = {
        "chinese_synced", "english_synced", "mixed_language", "translation", "romanization",
        "instrumental", "empty", "loading", "failed", "long_song", "rapid_lines", "duplicate_timestamps",
    }

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        lyrics_service: "OnlineLyricsService | None" = None,
        lyrics_cache_dir: Path | None = None,
        lyrics_bindings_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._track: Track | None = None
        self._document: LyricsDocument | None = None
        self._state = LyricsState()
        self._lyrics_service = lyrics_service
        self._lyrics_cache_dir = Path(lyrics_cache_dir) if lyrics_cache_dir else None
        self._lyrics_bindings_path = (
            Path(lyrics_bindings_path) if lyrics_bindings_path else None
        )
        self._request_identity = ""
        self._request_generation = 0
        self._scenario = "chinese_synced"
        self._position_ms = 0
        self._offset_ms = 0
        self._active_line_index = -1
        self._active_segment_index = -1
        self._line_starts: tuple[int, ...] = ()
        self._show_translation = True
        self._show_romanization = False
        self._font_scale = 1.0
        self._playback_failure_from_status = False
        if self._lyrics_service is not None:
            self._lyrics_service.statusChanged.connect(self._on_service_status)
            self._lyrics_service.lyricsReady.connect(self._on_service_result)

    @property
    def document(self) -> LyricsDocument | None:
        return self._document

    @property
    def track(self) -> Track | None:
        return self._track

    @property
    def state(self) -> LyricsState:
        return self._state

    @property
    def active_line(self) -> LyricLine | None:
        return self._line_at(self._active_line_index)

    @property
    def display_options(self) -> dict[str, object]:
        return {
            "translation": self._show_translation,
            "romanization": self._show_romanization,
            "font_scale": self._font_scale,
        }

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self._position_ms = 0
        self._active_line_index = -1
        self._active_segment_index = -1
        self._playback_failure_from_status = False
        if track is None:
            self.clear()
            return
        if self._track_is_unplayable(track):
            self._cancel_formal_request()
            self._set_document(None)
            self._set_state(
                "playback_unavailable",
                self._playback_unavailable_message(track),
                track.id,
                track.source_type,
            )
            return
        if self._lyrics_service is not None:
            self._load_formal_track(track)
            return
        self._set_state("loading", "正在准备 mock 歌词。", track.id, "none")
        if self._scenario == "loading":
            self._set_document(None)
            return
        if self._scenario == "failed":
            self._set_document(None)
            self._set_state("failed", "暂时无法加载此歌曲的 mock 歌词。", track.id, "none")
            return
        document = create_mock_document(track, self._scenario)
        self._set_document(document)
        if self._scenario == "empty":
            self._set_state("empty", "当前歌曲没有可用歌词。", track.id, "none")
        elif self._scenario == "instrumental":
            self._set_state("instrumental", "当前为纯音乐片段。", track.id, document.source_type)
        else:
            self._set_state("ready", "", track.id, document.source_type)
        self.set_position(0, force=True)

    def load_mock_scenario(self, name: str) -> None:
        self._scenario = name if name in self._SCENARIOS else "chinese_synced"
        if self._track is not None:
            self.set_track(self._track)

    def complete_loading_for_test(self) -> None:
        if self._scenario == "loading" and self._track is not None:
            self._scenario = "chinese_synced"
            self.set_track(self._track)

    def retry(self) -> None:
        if self._track is not None:
            self.set_track(self._track)

    def set_playback_status(self, status: str, detail: str = "") -> None:
        """Keep playback failure visible instead of showing synthetic lyrics."""

        track = self._track
        if track is None:
            return
        normalized = str(status or "idle").strip().casefold().replace("-", "_")
        if normalized in {"error", "unavailable"}:
            self._playback_failure_from_status = True
            self._cancel_formal_request()
            self._set_document(None)
            self._set_state(
                "playback_unavailable",
                self._playback_unavailable_message(track, detail),
                track.id,
                track.source_type,
            )
            return
        if self._playback_failure_from_status and normalized in {"playing", "paused", "buffering"}:
            self.set_track(track)

    @staticmethod
    def _track_is_unplayable(track: Track) -> bool:
        availability = str(track.availability or "").strip().casefold()
        if track.is_online:
            return availability in _CONFIRMED_UNPLAYABLE_STATES
        return bool(track.is_missing)

    @staticmethod
    def _playback_unavailable_message(track: Track, detail: str = "") -> str:
        if detail and str(detail).strip():
            return f"{str(detail).strip()} 暂不显示默认歌词。"
        if track.is_online:
            return "当前无法播放这首在线歌曲，暂不显示默认歌词。"
        return "当前无法播放这首歌曲，暂不显示默认歌词。"

    def set_position(self, position_ms: int, *, force: bool = False) -> None:
        position = max(0, int(position_ms))
        if not force and position == self._position_ms:
            return
        self._position_ms = position
        self.position_changed.emit(position)
        self._update_active_timing(force)

    def set_offset(self, offset_ms: int) -> None:
        offset = max(-10_000, min(10_000, int(offset_ms)))
        if offset == self._offset_ms:
            return
        self._offset_ms = offset
        self.offset_changed.emit(offset)
        self._update_active_timing(True)

    def seek_to_line(self, line_id: str) -> None:
        if self._document is None:
            return
        line = next((item for item in self._document.lines if item.id == line_id), None)
        if line is None:
            return
        position = max(0, line.start_ms - self._offset_ms)
        self.set_position(position, force=True)
        self.seek_requested.emit(position)

    def request_seek(self, position_ms: int) -> None:
        position = max(0, int(position_ms))
        self.set_position(position, force=True)
        self.seek_requested.emit(position)

    def toggle_translation(self) -> None:
        self._show_translation = not self._show_translation
        self.display_options_changed.emit(self.display_options)

    def toggle_romanization(self) -> None:
        self._show_romanization = not self._show_romanization
        self.display_options_changed.emit(self.display_options)

    def set_font_scale(self, value: float) -> None:
        scale = max(0.8, min(1.45, round(float(value), 2)))
        if scale == self._font_scale:
            return
        self._font_scale = scale
        self.display_options_changed.emit(self.display_options)

    def clear(self) -> None:
        self._cancel_formal_request()
        self._track = None
        self._request_identity = ""
        self._request_generation = 0
        self._position_ms = 0
        self._active_line_index = -1
        self._active_segment_index = -1
        self._playback_failure_from_status = False
        self._set_document(None)
        self._set_state("idle", "请选择一首歌曲开始播放。", "", "none")
        self.position_changed.emit(0)

    def shutdown(self) -> None:
        """Cancel a pending provider request before the owning shell closes."""

        self._cancel_formal_request()

    def _load_formal_track(self, track: Track) -> None:
        self._cancel_formal_request()
        self._request_identity = track.stable_identity
        self._set_document(None)
        self._set_state("loading", "正在查找歌曲歌词。", track.id, track.source_type)

        local_text = self._read_local_lyrics(track)
        if local_text:
            self._apply_lyrics_text(track, local_text, "local")
            return

        if self._lyrics_service is None:
            self._set_state("empty", "当前歌曲没有可用歌词。", track.id, track.source_type)
            return

        media_item = self._media_item_for_track(track)
        self._request_generation = self._lyrics_service.generation + 1
        self._lyrics_service.request_lyrics(media_item)

    def _on_service_status(self, generation: int, identity: str, message: str) -> None:
        track = self._track
        if (
            track is None
            or self._lyrics_service is None
            or int(generation) != self._request_generation
            or str(identity or "") != track.stable_identity
            or self._playback_failure_from_status
        ):
            return
        self._set_state("loading", str(message or "正在加载歌词。"), track.id, track.source_type)

    def _on_service_result(self, generation: int, identity: str, payload: dict) -> None:
        track = self._track
        if (
            track is None
            or int(generation) != self._request_generation
            or str(identity or "") != track.stable_identity
            or self._playback_failure_from_status
        ):
            return
        payload = payload if isinstance(payload, dict) else {}
        text = str(payload.get("text") or "").strip()
        if text:
            source_type = str(payload.get("source") or track.source_type).strip()
            self._apply_lyrics_text(track, text, source_type)
            return
        self._set_document(None)
        if payload.get("error"):
            self._set_state(
                "failed",
                str(payload.get("source") or "暂时无法显示歌词，请稍后重试。"),
                track.id,
                track.source_type,
            )
        else:
            self._set_state(
                "empty",
                str(payload.get("source") or "当前歌曲没有可用歌词。"),
                track.id,
                track.source_type,
            )

    def _apply_lyrics_text(self, track: Track, text: str, source_type: str) -> None:
        document = _document_from_text(track, text, source_type)
        self._set_document(document)
        if document is None:
            self._set_state("empty", "当前歌曲没有可用歌词。", track.id, track.source_type)
            return
        self._set_state("ready", "", track.id, source_type)
        self.set_position(0, force=True)

    def _cancel_formal_request(self) -> None:
        if self._lyrics_service is not None:
            self._lyrics_service.cancel()
        self._request_identity = ""
        self._request_generation = 0

    @staticmethod
    def _media_item_for_track(track: Track) -> MediaItem:
        if not track.is_online:
            return MediaItem.from_local(
                {
                    "track_id": track.id,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "duration": (track.duration_ms or 0) / 1000,
                    "path": track.local_path,
                }
            )
        payload = dict(track.remote_payload) if isinstance(track.remote_payload, dict) else {}
        payload.update(
            {
                "media_type": "online",
                "source_id": track.source_id,
                "source_name": track.source_name,
                "track_id": track.remote_track_id or track.remote_identity or track.id,
                "remote_stable_id": track.stable_identity,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "duration": (track.duration_ms or 0) / 1000,
                "availability": track.availability,
            }
        )
        return MediaItem.from_online(payload)

    def _read_local_lyrics(self, track: Track) -> str:
        if track.is_online or not track.local_path:
            return ""
        song_path = Path(track.local_path)
        folder = song_path.parent
        paths: list[Path] = []
        bound_path = self._bound_lyrics_path(song_path)
        if bound_path:
            paths.append(bound_path)
        paths.extend(
            (
                song_path.with_suffix(".lrc"),
                folder / f"{song_path.stem}.lrc",
                folder / f"{track.title}.lrc",
                folder / f"{track.artist} - {track.title}.lrc",
                folder / f"{track.title} - {track.artist}.lrc",
            )
        )
        if self._lyrics_cache_dir is not None:
            normalized = self._normalized_path(song_path)
            digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
            paths.append(self._lyrics_cache_dir / f"{digest}.lrc")
        try:
            paths.extend(
                candidate
                for candidate in folder.glob("*.lrc")
                if candidate.stem.casefold() == song_path.stem.casefold()
            )
        except OSError:
            return ""
        seen: set[str] = set()
        for candidate in paths:
            key = str(candidate).casefold()
            if key in seen or not candidate.is_file():
                continue
            seen.add(key)
            for encoding in ("utf-8", "utf-8-sig", "gb18030"):
                try:
                    return candidate.read_text(encoding=encoding).strip()
                except UnicodeDecodeError:
                    continue
                except OSError:
                    break
        return ""

    def _bound_lyrics_path(self, song_path: Path) -> Path | None:
        if self._lyrics_bindings_path is None or not self._lyrics_bindings_path.is_file():
            return None
        try:
            bindings = json.loads(
                self._lyrics_bindings_path.read_text(encoding="utf-8")
            )
        except (OSError, TypeError, ValueError):
            return None
        if not isinstance(bindings, dict):
            return None
        normalized_song = self._normalized_path(song_path)
        for source, target in bindings.items():
            if self._normalized_path(Path(str(source))) != normalized_song:
                continue
            candidate = Path(str(target or ""))
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _normalized_path(path: Path) -> str:
        try:
            return str(path.expanduser().resolve()).casefold()
        except (OSError, RuntimeError):
            return str(path).casefold()

    def _update_active_timing(self, force: bool) -> None:
        if self._document is None or self._state.phase not in {"ready", "instrumental"}:
            return
        effective = self._position_ms + self._offset_ms
        next_index = self._locate_line(effective)
        if next_index != self._active_line_index or force:
            self._active_line_index = next_index
            self._active_segment_index = -1
            self.active_line_changed.emit(self._line_at(next_index))
        line = self._line_at(next_index)
        if line is None or not line.segments:
            return
        segment_index, progress = self._locate_segment(line, effective)
        if segment_index >= 0:
            self._active_segment_index = segment_index
            self.active_segment_changed.emit(line, segment_index, progress)

    def _locate_line(self, effective: int) -> int:
        if not self._line_starts:
            return -1
        current = self._active_line_index
        if current >= 0 and effective >= self._line_starts[current]:
            while current + 1 < len(self._line_starts) and self._line_starts[current + 1] <= effective:
                current += 1
            return current
        return bisect_right(self._line_starts, effective) - 1

    @staticmethod
    def _locate_segment(line: LyricLine, effective: int) -> tuple[int, float]:
        starts = tuple(segment.start_ms for segment in line.segments)
        index = bisect_right(starts, effective) - 1
        if index < 0:
            return -1, 0.0
        segment: LyricSegment = line.segments[index]
        end = segment.end_ms
        if end is None or end <= segment.start_ms:
            return index, 1.0
        return index, max(0.0, min(1.0, (effective - segment.start_ms) / (end - segment.start_ms)))

    def _line_at(self, index: int) -> LyricLine | None:
        if self._document is None or not 0 <= index < len(self._document.lines):
            return None
        return self._document.lines[index]

    def _set_document(self, document: LyricsDocument | None) -> None:
        self._document = document
        self._line_starts = tuple(line.start_ms for line in document.lines) if document else ()
        self.document_changed.emit(document)

    def _set_state(self, phase: str, message: str, track_id: str, source_type: str) -> None:
        self._state = LyricsState(phase, message, track_id, source_type)
        self.state_changed.emit(self._state)
