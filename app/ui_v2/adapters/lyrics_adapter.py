"""Mock lyric timing state, separate from playback widgets and real services."""

from __future__ import annotations

from bisect import bisect_right

from PySide6.QtCore import QObject, Signal

from app.ui_v2.mock.lyrics_factory import create_mock_document
from app.ui_v2.models.lyric_line import LyricLine, LyricSegment
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.lyrics_state import LyricsState
from app.ui_v2.models.track import Track


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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._track: Track | None = None
        self._document: LyricsDocument | None = None
        self._state = LyricsState()
        self._scenario = "chinese_synced"
        self._position_ms = 0
        self._offset_ms = 0
        self._active_line_index = -1
        self._active_segment_index = -1
        self._line_starts: tuple[int, ...] = ()
        self._show_translation = True
        self._show_romanization = False
        self._font_scale = 1.0

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
        if track is None:
            self.clear()
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
        self._track = None
        self._position_ms = 0
        self._active_line_index = -1
        self._active_segment_index = -1
        self._set_document(None)
        self._set_state("idle", "请选择一首歌曲开始播放。", "", "none")
        self.position_changed.emit(0)

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
