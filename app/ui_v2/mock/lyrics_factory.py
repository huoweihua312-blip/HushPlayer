"""Deterministic lyric documents for UI V2; no files or services are used."""

from __future__ import annotations

from app.ui_v2.models.lyric_line import LyricLine, LyricSegment
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.track import Track


_CHINESE = (
    "雾落在清晨的海岸",
    "灯火穿过安静的街道",
    "我们沿着月光慢慢前行",
    "风把未说完的话带远",
    "夜航越过城市的边缘",
)
_ENGLISH = (
    "The morning finds a quieter shore",
    "City lights are fading into blue",
    "We follow every signal home",
    "The rain keeps time against the glass",
    "A paper moon is hanging low",
)


def create_mock_document(track: Track, scenario: str = "chinese_synced") -> LyricsDocument:
    """Create at least 100 stable, timed lines for a requested mock scenario."""
    if scenario == "empty":
        return LyricsDocument(track.id, track.title, track.artist, "none", ())
    source_type = "online" if track.is_online else "local"
    if scenario == "mixed_language":
        source_type = "embedded"
    if scenario == "instrumental":
        line = LyricLine(
            id=f"{track.id}:instrumental",
            start_ms=0,
            end_ms=None,
            text="纯音乐片段",
            language="plain",
            is_instrumental=True,
        )
        return LyricsDocument(track.id, track.title, track.artist, source_type, (line,), sync_mode="none")

    interval = 2_400
    if scenario == "long_song":
        interval = 3_200
    elif scenario == "rapid_lines":
        interval = 360
    lines: list[LyricLine] = []
    for index in range(100):
        start = (index // 2) * 1_400 if scenario == "duplicate_timestamps" else index * interval
        next_start = (
            ((index + 1) // 2) * 1_400
            if scenario == "duplicate_timestamps"
            else (index + 1) * interval
        )
        end = max(start + 300, next_start - 80)
        if index == 99 and scenario in {"long_song", "rapid_lines"}:
            end = None
        language = "chinese"
        if scenario == "english_synced" or (scenario == "mixed_language" and index % 2):
            language = "english"
        if language == "chinese":
            text = _CHINESE[index % len(_CHINESE)]
            segments = _character_segments(text, start, end)
            translation = _ENGLISH[index % len(_ENGLISH)] if scenario in {"translation", "mixed_language"} else ""
            romanization = f"ye hang de guang ying {index + 1}" if scenario == "romanization" else ""
        else:
            text = _ENGLISH[index % len(_ENGLISH)]
            segments = _word_segments(text, start, end)
            translation = _CHINESE[index % len(_CHINESE)] if scenario in {"translation", "mixed_language"} else ""
            romanization = "" if scenario != "romanization" else f"english line {index + 1}"
        if scenario == "long_song" and index % 9 == 0:
            text += "，这一段较长的 mock 歌词用于验证自动换行和稳定的滚动位置。"
            segments = _character_segments(text, start, end)
        lines.append(
            LyricLine(
                id=f"{track.id}:line:{index:03d}",
                start_ms=start,
                end_ms=end,
                text=text,
                translation=translation,
                romanization=romanization,
                language=language,
                segments=segments,
            )
        )
    return LyricsDocument(
        track.id,
        track.title,
        track.artist,
        source_type,
        tuple(lines),
        has_translation=any(line.translation for line in lines),
        has_romanization=any(line.romanization for line in lines),
        sync_mode="segment",
    )


def _character_segments(text: str, start: int, end: int | None) -> tuple[LyricSegment, ...]:
    duration = max(1, (end if end is not None else start + 2_400) - start)
    width = max(1, duration // max(1, len(text)))
    return tuple(
        LyricSegment(character, start + index * width, min(start + (index + 1) * width, start + duration), "character")
        for index, character in enumerate(text)
    )


def _word_segments(text: str, start: int, end: int | None) -> tuple[LyricSegment, ...]:
    words = text.split(" ")
    duration = max(1, (end if end is not None else start + 2_400) - start)
    width = max(1, duration // max(1, len(words)))
    return tuple(
        LyricSegment(f"{word}{' ' if index < len(words) - 1 else ''}", start + index * width, min(start + (index + 1) * width, start + duration), "word")
        for index, word in enumerate(words)
    )
