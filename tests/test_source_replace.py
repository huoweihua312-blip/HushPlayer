"""Tests for the "replace song source" feature."""

from __future__ import annotations

from PySide6.QtCore import QObject

from hushplayer.model.track import Track, album_key, online_track_id
from hushplayer.online import models as online_models
from hushplayer.services import source_replace as sr
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


# ---------------------------------------------------------------------------
# 筛选 / 增量 / 缓存：对应用户反馈「结果里全是不相关的歌」「搜索太慢」
# ---------------------------------------------------------------------------


def _plausible_track() -> Track:
    return Track(
        id="online:kw:abc",
        kind="online",
        title="家书",
        artist="加木",
        album="羲和",
        duration_ms=242_000,
        source_id="kw",
        source_name="酷我",
        remote_id="abc",
    )


def _candidate(remote_id: str, **kwargs) -> SourceCandidate:
    data = dict(
        source_id="wy",
        source_name="网易音乐",
        remote_id=remote_id,
        title="家书",
        artist="加木",
        album="羲和",
        duration_ms=242_000,
        artwork_url="",
        score=100,
        raw={},
    )
    data.update(kwargs)
    return SourceCandidate(**data)


def test_plausible_keeps_covers_but_rejects_previews_and_other_songs() -> None:
    track = _plausible_track()
    assert sr.plausible(track, _candidate("a"))

    preview = _candidate("b", duration_ms=30_000, score=95)
    assert not sr.plausible(track, preview), "30 秒试听片段不应通过"
    assert "试听片段" in sr._duration_problem(track.duration_ms, preview.duration_ms)

    # 用户要求保留翻唱：标题对得上、歌手不同时仍然展示，只加提示。
    cover = _candidate("c", title="家书（翻唱）", artist="别人", score=80)
    assert sr.plausible(track, cover), "翻唱版本应保留在候选里"
    assert "歌手不同" in sr._note_for(track, cover)

    other = _candidate("d", title="完全不同的歌", artist="别人", score=70)
    assert not sr.plausible(track, other), "标题不符不应通过"


def test_search_reports_candidates_incrementally() -> None:
    class _StreamingClient(_FakeClient):
        running = True

        def ensure_started(self) -> None:  # pragma: no cover - 只在未运行时调用
            self.running = True

    client = _StreamingClient(
        {
            "wy": [
                {"id": "a", "title": "家书", "artist": "加木", "album": "羲和", "duration": 242000},
            ],
            "kg": [
                {"id": "b", "title": "家书", "artist": "加木", "album": "羲和", "duration": 243000},
            ],
        }
    )
    updates: list[tuple[int, int]] = []
    finished: list[list[SourceCandidate]] = []
    sr.clear_cache()
    search = SourceReplaceSearch(
        client,
        _plausible_track(),
        [_source("wy", "网易音乐"), _source("kg", "酷狗")],
        lambda candidates, errors: finished.append(candidates),
        on_update=lambda candidates, errors, done, total: updates.append((done, len(candidates))),
        use_cache=False,
    )
    search.start()
    assert updates, "应在全部返回前先回显部分结果"
    assert updates[-1][0] >= 1
    assert finished and len(finished[0]) == 2


def test_search_reuses_cache_and_starts_runtime() -> None:
    class _ColdClient(_FakeClient):
        def __init__(self, responses):
            super().__init__(responses)
            self.running = False
            self.ensure_calls = 0

        def ensure_started(self) -> None:
            self.ensure_calls += 1
            self.running = True

    client = _ColdClient(
        {"wy": [{"id": "a", "title": "家书", "artist": "加木", "duration": 242000}]}
    )
    sr.clear_cache()
    first: list[list[SourceCandidate]] = []
    SourceReplaceSearch(
        client, _plausible_track(), [_source("wy", "网易音乐")], lambda c, e: first.append(c)
    ).start()
    assert client.ensure_calls == 1, "运行时没起来时应先 ensure_started"
    assert first and len(first[0]) == 1
    calls = len(client.calls)

    second: list[list[SourceCandidate]] = []
    SourceReplaceSearch(
        client, _plausible_track(), [_source("wy", "网易音乐")], lambda c, e: second.append(c)
    ).start()
    assert len(client.calls) == calls, "命中缓存时不应再发请求"
    assert [(c.source_id, c.remote_id) for c in second[0]] == [("wy", "a")]


def test_dialog_ok_button_submits_selected_candidate(qapp) -> None:
    """用户反馈「点『使用此来源』没反应」：按钮必须把选中项写进 chosen。"""
    from hushplayer.ui.track_source_dialog import TrackSourceDialog

    dialog = TrackSourceDialog(None, _plausible_track())
    candidate = _candidate("a")
    dialog._render([candidate], [])
    assert dialog.list.count() == 1
    dialog.list.setCurrentRow(0)
    ok = dialog.button_for("ok")
    assert ok is not None and ok.isEnabled()
    ok.click()
    assert dialog.chosen is candidate


