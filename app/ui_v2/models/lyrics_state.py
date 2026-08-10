"""Small state value object used by the lyrics page and its state view."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LyricsState:
    phase: str = "idle"
    message: str = "请选择一首歌曲开始播放。"
    track_id: str = ""
    source_type: str = "none"
