"""R3-02 回归：源内不可播放时自动改用其他音源播放同一首歌。

用户反馈「原版各音源都能播放，移植后部分源不能播放」。实测酷狗 / QQ海棠插件
调用的第三方接口当前返回 404（直接 Node 调用同样 404，与本移植无关），所以修复
不是"让 404 消失"，而是恢复原版 OnlineTrackRecoveryService 的跨源匹配行为：
先用同一音源的不同音质重试，再按标题/歌手/专辑/时长打分从其它音源找回同一首。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
import pytest

from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.model.track import Track
from hushplayer.online import matching
from hushplayer.online.models import SourceInfo, track_from_item
from hushplayer.services import source_memory


@pytest.fixture(autouse=True)
def _isolated_source_memory(data_dir):
    source_memory.clear()
    yield

KG = SourceInfo(
    id="custom_source_kg",
    name="酷狗",
    platform="kg",
    enabled=True,
    capabilities={"search": True, "playback": True},
)
WY = SourceInfo(
    id="custom_source_wy",
    name="网易音乐",
    platform="wy",
    enabled=True,
    capabilities={"search": True, "playback": True},
)

KG_ITEM = {"id": "kg-1", "title": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269000}
WY_ITEM = {"id": "wy-9", "title": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269000}


class FakeClient(QObject):
    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self, *, resolve_failures: int = 0, search_items=None) -> None:
        super().__init__()
        self.resolve_failures = resolve_failures
        self.search_items = search_items or []
        self.resolve_calls: list[tuple[str, str]] = []
        self.search_calls: list[tuple[str, str]] = []

    def search(self, source_id, keyword, page=1, callback=None, **kwargs):  # noqa: ANN001
        self.search_calls.append((source_id, keyword))
        if callback is not None:
            callback({"ok": True, "data": self.search_items})
        return 0

    def resolve_playback(self, source_id, payload, callback, **kwargs):  # noqa: ANN001
        self.resolve_calls.append((source_id, str(kwargs.get("quality"))))
        if self.resolve_failures > 0:
            self.resolve_failures -= 1
            callback({"ok": False, "error": "Request failed with status code 404"})
            return 0
        callback({
            "ok": True,
            "data": {
                "url": f"https://cdn.example.com/{source_id}.mp3",
                "headers": {},
                "mimeType": "audio/mpeg",
                "quality": kwargs.get("quality") or "standard",
            },
        })
        return 0

    def stop(self) -> None:
        return None


def make_controller(client: FakeClient) -> tuple[PlayerController, list]:
    engine = PlaybackEngine()
    controller = PlayerController(engine=engine, client=client)
    controller.set_volume(0.0)
    controller._sources = [KG, WY]  # noqa: SLF001 - test seam
    loaded: list = []
    engine.load = lambda *a, **kw: loaded.append((a, kw))  # type: ignore[assignment]
    controller.proxy.register = lambda *a, **kw: "http://127.0.0.1:9/audio/x"  # type: ignore[assignment]
    return controller, loaded


def test_score_prefers_exact_recording():
    target = Track(id="a", title="晴天", artist="周杰伦", album="叶惠美", duration_ms=269000)
    exact = Track(id="b", title="晴天", artist="周杰伦", album="叶惠美", duration_ms=269000)
    live = Track(id="c", title="晴天 (Live)", artist="周杰伦", album="演唱会", duration_ms=249000)
    cover = Track(id="d", title="晴天", artist="翻唱歌手", album="", duration_ms=200000)
    assert matching.score_match(target, exact) > matching.score_match(target, live)
    assert matching.score_match(target, live) > matching.score_match(target, cover)
    ranked = matching.rank_candidates(target, [cover, live, exact])
    assert ranked[0].track.id == "b"
    assert matching.best_candidate(target, [cover, live, exact]).track.id == "b"


def test_falls_back_to_another_source_and_plays(qapp):
    client = FakeClient(resolve_failures=3, search_items=[WY_ITEM])
    controller, loaded = make_controller(client)
    messages: list[str] = []
    controller.status_message.connect(messages.append)
    track = track_from_item(KG_ITEM, source=KG)

    controller.play_tracks([track], 0, context="test")
    assert loaded, "fallback playback never reached the engine"
    assert client.search_calls and client.search_calls[0][0] == WY.id
    assert any(WY.label in message for message in messages if "播放" in message)


def test_quality_chain_retries_before_falling_back(qapp):
    client = FakeClient(resolve_failures=1, search_items=[])
    controller, loaded = make_controller(client)
    track = track_from_item(KG_ITEM, source=KG)

    controller.play_tracks([track], 0, context="test")
    qualities = [quality for source, quality in client.resolve_calls if source == KG.id]
    assert len(qualities) >= 2, qualities
    assert qualities[0] == "standard"
    assert len(set(qualities)) == len(qualities)


def test_no_fallback_when_disabled(qapp):
    client = FakeClient(resolve_failures=3, search_items=[WY_ITEM])
    controller, loaded = make_controller(client)
    controller._online_fallback = False  # noqa: SLF001 - test seam
    errors: list[str] = []
    controller.error_message.connect(errors.append)
    track = track_from_item(KG_ITEM, source=KG)

    controller.play_tracks([track], 0, context="test")
    assert not loaded
    assert not client.search_calls
    assert errors

def test_remembered_source_skips_the_broken_one(qapp):
    """After a successful cross-source fallback the next play goes straight there."""
    first_client = FakeClient(resolve_failures=3, search_items=[WY_ITEM])
    first, loaded = make_controller(first_client)
    track = track_from_item(KG_ITEM, source=KG)
    first.play_tracks([track], 0, context="test")
    assert loaded

    alias = source_memory.track_alias(track.id)
    assert alias is not None and alias["source_id"] == WY.id

    second_client = FakeClient(search_items=[])
    second, loaded_again = make_controller(second_client)
    second.play_track(track)

    assert loaded_again, "remembered source should play without a new search"
    assert [call[0] for call in second_client.resolve_calls] == [WY.id]
    assert not second_client.search_calls


def test_resolved_url_is_reused_within_ttl(qapp):
    client = FakeClient(search_items=[])
    controller, loaded = make_controller(client)
    track = track_from_item(KG_ITEM, source=KG)

    controller.play_tracks([track], 0, context="test")
    calls_after_first = len(client.resolve_calls)
    controller.play_track(track)
    assert len(client.resolve_calls) == calls_after_first, "second play should reuse the cached URL"
    assert len(loaded) >= 2


def test_expired_cache_entry_is_refreshed(qapp):
    import time as _time

    from hushplayer.audio import controller as controller_module

    client = FakeClient(search_items=[])
    controller, _loaded = make_controller(client)
    track = track_from_item(KG_ITEM, source=KG)
    controller.play_tracks([track], 0, context="test")
    key = controller._resolve_cache_key(track)
    stamped, payload = controller._resolve_cache[key]
    controller._resolve_cache[key] = (
        stamped - (controller_module.RESOLVE_CACHE_TTL_MS / 1000 + 1),
        payload,
    )
    calls = len(client.resolve_calls)
    controller.play_track(track)
    assert len(client.resolve_calls) == calls + 1

def test_dedupe_keeps_versions_apart():
    tracks = [
        Track(id="1", title="晴天", artist="周杰伦", duration_ms=269000),
        Track(id="2", title="晴天 (Live)", artist="周杰伦", duration_ms=249000),
        Track(id="3", title="晴天", artist="周杰伦", duration_ms=269000),
        Track(id="4", title="晴天", artist="翻唱歌手", duration_ms=200000),
    ]
    kept = matching.dedupe_tracks(tracks)
    assert [track.id for track in kept] == ["1", "2", "4"]
