from __future__ import annotations

import math


LYRICS_TIMING_OFFSETS_KEY = "lyrics_timing_offsets_ms"
MIN_LYRICS_OFFSET_MS = -10_000
MAX_LYRICS_OFFSET_MS = 10_000
LYRICS_OFFSET_STEP_MS = 100
MAX_LYRICS_OFFSET_RECORDS = 500


def normalize_lyrics_offset_ms(value) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    bounded = max(MIN_LYRICS_OFFSET_MS, min(MAX_LYRICS_OFFSET_MS, number))
    steps = math.floor(abs(bounded) / LYRICS_OFFSET_STEP_MS + 0.5)
    return int(math.copysign(steps * LYRICS_OFFSET_STEP_MS, bounded))


def normalize_lyrics_timing_offsets(value) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for raw_identity, raw_offset in value.items():
        identity = raw_identity.strip() if isinstance(raw_identity, str) else ""
        if not identity:
            continue
        offset_ms = normalize_lyrics_offset_ms(raw_offset)
        if offset_ms:
            normalized[identity] = offset_ms
    if len(normalized) > MAX_LYRICS_OFFSET_RECORDS:
        normalized = dict(list(normalized.items())[-MAX_LYRICS_OFFSET_RECORDS:])
    return normalized


def lyrics_offset_for_settings(settings: dict | None, track_identity: str) -> int:
    document = settings if isinstance(settings, dict) else {}
    identity = str(track_identity or "").strip()
    if not identity:
        return 0
    offsets = normalize_lyrics_timing_offsets(
        document.get(LYRICS_TIMING_OFFSETS_KEY, {})
    )
    return int(offsets.get(identity, 0))


def update_lyrics_timing_offsets(
    value,
    track_identity: str,
    offset_ms,
) -> dict[str, int]:
    identity = str(track_identity or "").strip()
    offsets = normalize_lyrics_timing_offsets(value)
    if not identity:
        return offsets
    offsets.pop(identity, None)
    normalized_offset = normalize_lyrics_offset_ms(offset_ms)
    if normalized_offset:
        offsets[identity] = normalized_offset
    if len(offsets) > MAX_LYRICS_OFFSET_RECORDS:
        offsets = dict(list(offsets.items())[-MAX_LYRICS_OFFSET_RECORDS:])
    return offsets


def effective_lyrics_position_ms(player_position_ms, offset_ms) -> int:
    try:
        player_position = int(player_position_ms)
    except (TypeError, ValueError):
        player_position = 0
    return player_position + normalize_lyrics_offset_ms(offset_ms)
