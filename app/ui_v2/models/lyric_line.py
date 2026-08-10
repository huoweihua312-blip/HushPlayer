"""Value objects for one mock lyric line and its timed segments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LyricSegment:
    text: str
    start_ms: int
    end_ms: int | None
    segment_type: str


@dataclass(frozen=True, slots=True)
class LyricLine:
    id: str
    start_ms: int
    end_ms: int | None
    text: str
    translation: str = ""
    romanization: str = ""
    language: str = "plain"
    segments: tuple[LyricSegment, ...] = ()
    is_instrumental: bool = False
