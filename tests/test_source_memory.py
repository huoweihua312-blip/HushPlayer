"""The remembered-source cache used to make track switching feel instant."""

from __future__ import annotations

from hushplayer.model.track import ONLINE, Track
from hushplayer.services import source_memory


def _online(track_id: str, source_id: str = "kg", title: str = "家书") -> Track:
    return Track(
        id=track_id,
        kind=ONLINE,
        title=title,
        artist="加木",
        source_id=source_id,
        source_name="酷狗",
        remote_id=f"r{track_id}",
        duration_ms=242_000,
    )


def test_track_alias_roundtrip(data_dir) -> None:
    source_memory.clear()
    original = _online("t1")
    match = _online("t2", source_id="ne", title="家书")
    match.source_name = "网易云"

    assert source_memory.track_alias("t1") is None
    source_memory.remember_track(original, match)
    alias = source_memory.track_alias("t1")
    assert alias is not None
    assert alias["source_id"] == "ne"
    assert alias["remote_id"] == "rt2"
    assert alias["duration_ms"] == 242_000

    source_memory.forget_track("t1")
    assert source_memory.track_alias("t1") is None


def test_source_map_and_preferred_persist(data_dir) -> None:
    source_memory.clear()
    source_memory.remember_source_map("kg", "ne")
    source_memory.set_preferred("ne")

    assert source_memory.source_map("kg") == "ne"
    assert source_memory.source_map("qq") == ""
    assert source_memory.preferred() == "ne"

    # A new process re-reads the same file (the module cache is the only state).
    source_memory._CACHE = None  # type: ignore[attr-defined]
    assert source_memory.source_map("kg") == "ne"
    assert source_memory.preferred() == "ne"


def test_remember_track_requires_remote_id(data_dir) -> None:
    source_memory.clear()
    original = _online("t3")
    match = _online("t4", source_id="ne")
    match.remote_id = ""

    source_memory.remember_track(original, match)
    # Without a remote id the alias would resolve to an empty payload; skip it.
    assert source_memory.track_alias("t3") is None
