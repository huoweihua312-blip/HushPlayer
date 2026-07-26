"""Immutable UI-only lyric document supplied by the mock adapter."""

from __future__ import annotations

from dataclasses import dataclass

from app.ui_v2.models.lyric_line import LyricLine


@dataclass(frozen=True, slots=True)
class LyricsDocument:
    track_id: str
    title: str
    artist: str
    source_type: str
    lines: tuple[LyricLine, ...]
    offset_ms: int = 0
    has_translation: bool = False
    has_romanization: bool = False
    sync_mode: str = "line"
