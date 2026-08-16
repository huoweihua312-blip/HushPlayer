from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.lyrics_timing import (
    LYRICS_TIMING_OFFSETS_KEY,
    MAX_LYRICS_OFFSET_RECORDS,
    effective_lyrics_position_ms,
    lyrics_offset_for_settings,
    normalize_lyrics_offset_ms,
    normalize_lyrics_timing_offsets,
    update_lyrics_timing_offsets,
)


def main() -> int:
    assert normalize_lyrics_offset_ms(450) == 500
    assert normalize_lyrics_offset_ms(-550) == -600
    assert normalize_lyrics_offset_ms(50_000) == 10_000
    assert normalize_lyrics_offset_ms(-50_000) == -10_000
    assert normalize_lyrics_offset_ms(True) == 0
    assert normalize_lyrics_offset_ms("bad") == 0
    assert normalize_lyrics_offset_ms(float("nan")) == 0
    assert effective_lyrics_position_ms(1500, 500) == 2000
    assert effective_lyrics_position_ms(1500, -500) == 1000

    invalid = normalize_lyrics_timing_offsets(
        {"": 500, "bad": "no", "too-high": 99_000, "zero": 0}
    )
    assert invalid == {"too-high": 10_000}

    records = {f"track-{index}": 100 for index in range(MAX_LYRICS_OFFSET_RECORDS + 3)}
    bounded = normalize_lyrics_timing_offsets(records)
    assert len(bounded) == MAX_LYRICS_OFFSET_RECORDS
    assert "track-0" not in bounded
    assert f"track-{MAX_LYRICS_OFFSET_RECORDS + 2}" in bounded

    settings = {LYRICS_TIMING_OFFSETS_KEY: {"local:fixture": 500}}
    assert lyrics_offset_for_settings(settings, "local:fixture") == 500
    snapshot = deepcopy(settings)
    updated = update_lyrics_timing_offsets(
        settings[LYRICS_TIMING_OFFSETS_KEY], "online:fixture", -500
    )
    assert settings == snapshot
    assert updated == {"local:fixture": 500, "online:fixture": -500}
    assert update_lyrics_timing_offsets(updated, "local:fixture", 0) == {
        "online:fixture": -500
    }

    print("lyrics timing offset smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
