"""Tests for the "replace song source" feature."""

from __future__ import annotations

from PySide6.QtCore import QObject

from hushplayer.model.track import Track, album_key, online_track_id
from hushplayer.online import models as online_models
from hushplayer.services.source_replace import SourceCandidate, SourceReplaceSearch


def _source(source_id: str, label: str) -> online_models.SourceInfo:
    return online_models.SourceInfo(
        id=source_id,
        name=label,
        platform=label,
        enabled=True,
        user_installed=True,
        content_policy="user_owned",
        capabilities={
            "search": True,
            "metadata": False,
            "lyrics": True,
            "playback": True,
            "download": True,
            "downloadViaPlayback": False,
        },
    )


class _FakeClient(QObject):
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        super().__init__()
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def search(self, source_id, keyword, page=1, callback=None, *, timeout=0, kind="music"):
        self.calls.append((source_id, keyword))
        payload = {"ok": True, "data": {"data": self.responses.get(source_id, [])}}
        if callback is not None:
            callback(payload)
        return 1


def test_search_builds_sorted_deduped_candidates() -> None:
    track = Track(
        id="online:kw:abc",
        kind="online",
        title="晴天",
        artist="周杰伦",
        duration_ms=269000,
        source_id="kw",
        source_name="酷我",
    )
    client = _FakeClient(
        {
            "wy": [
                {"id": "1", "title": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269000},
                {"id": "1", "title": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269000},
                {"id": "2", "title": "晴天", "artist": "翻唱歌手", "album": "翻唱", "duration": 200000},
            ],
            "kg": [
                {"id": "9", "title": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 270000},
            ],
        }
    )
    collected: list[SourceCandidate] = []
    search = SourceReplaceSearch(
        client, track, [_source("wy", "网易音乐"), _source("kg", "酷狗")], lambda c, e: collected.extend(c)
    )
    search.start()
    assert collected, "应该拿到候选"
    assert len({(c.source_id, c.remote_id) for c in collected}) == len(collected)
    assert collected[0].score >= collected[-1].score
    assert {c.source_id for c in collected} == {"wy", "kg"}
    assert all(c.remote_id for c in collected)


def test_search_skips_current_source_and_reports_errors() -> None:
    track = Track(id="online:kw:x", kind="online", title="家书", artist="加木", source_id="kw")
    client = _FakeClient({})
    client.search = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment]
    done: list[tuple[list, list]] = []
    search = SourceReplaceSearch(
        client,
        track,
        [_source("kw", "酷我"), _source("wy", "网易音乐")],
        lambda c, e: done.append((c, e)),
    )
    search.start()
    assert done, "即使全部失败也要回调"
    candidates, errors = done[0]
    assert candidates == []
    assert any("网易音乐" in error for error in errors)


def test_replace_online_source_keeps_track_id(loaded_library) -> None:
    library = loaded_library
    library.import_files([])
    online = Track(
        id=online_track_id("kw", "remote-1"),
        kind="online",
        title="家书",
        artist="加木",
        album="羲和",
        duration_ms=242000,
        source_id="kw",
        source_name="酷我",
        remote_id="remote-1",
        favorite=True,
    )
    library.tracks.upsert(online)
    candidate = SourceCandidate(
        source_id="wy",
        source_name="网易音乐",
        remote_id="remote-2",
        title="家书",
        artist="加木",
        album="羲和",
        duration_ms=243000,
        artwork_url="https://example.invalid/cover.jpg",
        score=100,
        raw={"id": "remote-2"},
    )
    updated = library.replace_online_source(online.id, candidate)
    assert updated is not None
    assert updated.id == online.id
    assert updated.source_id == "wy"
    assert updated.source_name == "网易音乐"
    assert updated.remote_id == "remote-2"
    assert updated.album_id == album_key("羲和", "加木")
    stored = library.track(online.id)
    assert stored is not None and stored.remote_id == "remote-2"
