"""音源记忆 / 正式绑定回归（1.3.18）。

任务书要求的 14 类场景：正式绑定优先、预加载身份校验、强制刷新不换源、
旧别名不混用 raw、失败归因、回退落库、重复导入保护、迟到回调隔离等。

这里的 FakeClient 会记录传给插件层的**完整** ``resolve_playback`` 参数
（``source_id`` / ``payload`` / ``quality``），因为这次 bug 的核心就是
「用 A 音源的插件解析 B 音源的歌曲 ID」。
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QObject, Signal

from hushplayer.audio.controller import PlayerController, PreloadedStream
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.model.track import Track
from hushplayer.online import health
from hushplayer.services import source_memory
from hushplayer.services.binding import BindingChoice, TrackBindingService
from hushplayer.services.playlist_import import PlaylistEntry
from hushplayer.services.playlist_matcher import MatchRow, _bind_import_choices
from hushplayer.store.db import Database
from hushplayer.store.repository import TrackRepository

from test_cross_source import KG, KG_ITEM, QQ, QQ_ITEM, WY, WY_ITEM


class RecordingClient(QObject):
    """Records the exact resolve arguments and can answer later."""

    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self, *, search_items=None, search_by_source=None,
                 fail_sources=(), defer: bool = False) -> None:
        super().__init__()
        self.search_items = list(search_items or [])
        self.search_by_source = dict(search_by_source or {})
        self.fail_sources = set(fail_sources)
        self.fail_quality_once: set[tuple[str, str]] = set()
        self.defer = defer
        self.resolve_calls: list[dict] = []
        self.search_calls: list[tuple[str, str]] = []
        self.pending: list[tuple[dict, object, dict]] = []
        self.cancelled: list[int] = []
        self._next_id = 0

    # ---------------------------------------------------------- fake API
    def search(self, source_id, keyword, page=1, callback=None, **kwargs):  # noqa: ANN001
        self.search_calls.append((source_id, keyword))
        items = self.search_by_source.get(source_id, self.search_items)
        if callback is not None:
            callback({"ok": True, "data": items})
        return 0

    def resolve_playback(self, source_id, payload, callback, **kwargs):  # noqa: ANN001
        quality = str(kwargs.get("quality") or "standard")
        self._next_id += 1
        call = {
            "request_id": self._next_id,
            "source_id": source_id,
            "payload": dict(payload or {}),
            "quality": quality,
        }
        self.resolve_calls.append(call)
        key = (source_id, quality)
        if source_id in self.fail_sources or key in self.fail_quality_once:
            self.fail_quality_once.discard(key)
            response = {"ok": False, "error": "Request failed with status code 404"}
        else:
            response = {
                "ok": True,
                "data": {
                    "url": f"https://cdn.example.com/{source_id}/{self._next_id}.mp3",
                    "headers": {},
                    "mimeType": "audio/mpeg",
                    "quality": quality,
                },
            }
        if self.defer:
            self.pending.append((call, callback, response))
        else:
            callback(response)
        return self._next_id

    def flush(self) -> None:
        pending, self.pending = self.pending, []
        for _call, callback, response in pending:
            callback(response)  # type: ignore[operator]

    def cancel(self, request_id) -> None:  # noqa: ANN001
        # 记录取消，但保留回调：真实 runtime 偶尔仍会迟到投递，必须由
        # generation/session 校验挡住，而不是依赖传输层。
        self.cancelled.append(int(request_id))

    def stop(self) -> None:
        return None


class _StubEngine(PlaybackEngine):
    def __init__(self) -> None:
        super().__init__()
        self.fake_state = "stopped"

    @property
    def state(self) -> str:
        return self.fake_state


class _Library:
    def __init__(self, tmp_path) -> None:
        self.db_path = tmp_path / "bindings.db"
        self.db = Database(self.db_path)
        self.tracks = TrackRepository(self.db)


@pytest.fixture()
def library(tmp_path):
    return _Library(tmp_path)


@pytest.fixture(autouse=True)
def _isolated_memory(data_dir):
    source_memory.clear()
    health.reset()
    yield


# ------------------------------------------------------------------ helpers
def _track(track_id: str = "t1", source=KG, remote: str = "kg-1",
           raw=None, title: str = "晴天") -> Track:
    return Track(
        id=track_id,
        kind="online",
        source_id=source.id,
        source_name=source.name,
        remote_id=remote,
        title=title,
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
        raw=dict(raw if raw is not None else KG_ITEM),
    )


def _choice(source=QQ, remote: str = "qq-3", raw=None) -> BindingChoice:
    return BindingChoice(
        source_id=source.id,
        source_name=source.name,
        remote_id=remote,
        title="晴天",
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
        artwork_url="",
        album_id="",
        artist_id="",
        raw=dict(raw if raw is not None else (QQ_ITEM if source is QQ else WY_ITEM)),
    )


def _controller(library, client, sources=None):
    service = getattr(library, "source_bindings", None)
    engine = _StubEngine()
    controller = PlayerController(engine=engine, client=client, binding=service)
    controller.set_volume(0.0)
    controller._sources = list(sources or [KG, WY, QQ])  # noqa: SLF001 - test seam
    controller.loaded = []  # type: ignore[attr-defined]
    engine.load = lambda *a, **kw: controller.loaded.append((a, kw))  # type: ignore[assignment]
    controller.registered = []  # type: ignore[attr-defined]
    controller.proxy.register = (  # type: ignore[assignment]
        lambda key, url, headers, **kw: (
            controller.registered.append(key) or "http://127.0.0.1:9/audio/x"
        )
    )
    return controller, engine


def _setup(library, client, sources=None):
    service = TrackBindingService(library)
    library.source_bindings = service
    controller, engine = _controller(library, client, sources)
    return service, controller, engine


def _confirm(controller, engine, first: int = 400, second: int = 1500) -> None:
    engine.fake_state = "playing"
    controller._on_position(first)  # noqa: SLF001
    controller._on_position(second)  # noqa: SLF001


# ------------------------------------------------------------- 1. 正式绑定优先
def test_formal_binding_beats_legacy_alias(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, _engine = _setup(library, client)
    assert service.manual_choose(track.id, _choice()) is True

    # 旧 JSON 记忆指向网易云，但数据库已经手动绑定 QQ。
    alias = Track(id="alias", kind="online", source_id=WY.id, remote_id="wy-9",
                  title=track.title, artist=track.artist, album=track.album,
                  duration_ms=track.duration_ms, raw=dict(WY_ITEM))
    source_memory.remember_track(track, alias)

    controller.play_tracks([track], 0)

    assert client.search_calls == []
    assert [call["source_id"] for call in client.resolve_calls] == [QQ.id]
    assert client.resolve_calls[0]["payload"]["id"] == "qq-3"


# -------------------------------------------------------- 2. 预加载身份不符丢弃
def test_mismatching_preload_is_discarded(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, _engine = _setup(library, client)
    assert service.manual_choose(track.id, _choice()) is True
    revision = service.state(track.id).revision

    controller._preloaded[track.id] = PreloadedStream(  # noqa: SLF001
        source_id=WY.id, remote_id="wy-9", quality="standard",
        revision=revision, request_id=7, request={"id": "wy-9"},
        data={"url": "https://cdn.example.com/stale.mp3", "quality": "standard"},
    )

    controller.play_tracks([track], 0)

    assert [call["source_id"] for call in client.resolve_calls] == [QQ.id]
    assert controller.registered and controller.registered[0].startswith(f"{QQ.id}:qq-3:")


# ------------------------------------------- 3. 预加载命中 + 真实播放后 verified
def test_preload_hit_is_verified_after_real_playback(library):
    track = _track(source=QQ, remote="qq-3", raw=QQ_ITEM)
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, engine = _setup(library, client)
    assert service.import_choice(track.id, BindingChoice.from_track(track)) is True
    revision = service.state(track.id).revision
    controller._preloaded[track.id] = PreloadedStream(  # noqa: SLF001
        source_id=QQ.id, remote_id="qq-3", quality="standard",
        revision=revision, request_id=9, request={"id": "qq-3"},
        data={"url": "https://cdn.example.com/pre.mp3", "quality": "standard",
              "headers": {}, "mimeType": "audio/mpeg"},
    )

    controller.play_tracks([track], 0)

    assert client.resolve_calls == []
    assert controller._attempt is not None  # noqa: SLF001
    assert controller._attempt["source_id"] == QQ.id  # noqa: SLF001
    assert service.state(track.id).verify_state == "pending"

    _confirm(controller, engine)

    assert service.state(track.id).verified is True
    assert library.tracks.get(track.id).source_id == QQ.id


# ------------------------------------------ 4. 手动换源后迟到的预加载不污染
def test_late_preload_after_manual_replace_is_dropped(library):
    first = _track("a", KG, "kg-1")
    second = _track("b", WY, "wy-9", raw=WY_ITEM, title="稻香")
    library.tracks.upsert(first)
    library.tracks.upsert(second)
    client = RecordingClient(defer=True)
    _service, controller, _engine = _setup(library, client)

    controller.play_tracks([first, second], 0)
    client.flush()  # 第一首正常解析

    controller.preload_next()
    assert client.pending, "preload should be in flight"
    held = list(client.pending)
    client.pending = []

    # 用户在预加载返回前把第二首手动换成 QQ。
    assert _service.manual_choose(second.id, _choice()) is True
    updated = library.tracks.get(second.id)
    controller.refresh_track(updated)

    # 迟到的预加载回调仍然到达 —— 但不能进入缓存。
    for _call, callback, response in held:
        callback(response)  # type: ignore[operator]

    assert second.id not in controller._preloaded  # noqa: SLF001
    assert controller._preload_epoch >= 1  # noqa: SLF001

    before = len(client.resolve_calls)
    controller.play_tracks([updated], 0)
    assert client.resolve_calls[before]["source_id"] == QQ.id
    assert controller._track is not None and controller._track.id == second.id


# --------------------------------------- 5. 强制刷新只绕 URL 缓存，不换身份
def test_force_refresh_keeps_bound_identity(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, _engine = _setup(library, client)
    assert service.manual_choose(track.id, _choice()) is True

    controller.play_tracks([track], 0)
    before = len(client.resolve_calls)
    assert {call["source_id"] for call in client.resolve_calls} == {QQ.id}

    client.fail_sources.add(QQ.id)  # 模拟 URL 过期/解析失败
    controller._online_fallback = False  # noqa: SLF001
    controller._resolve_online(  # noqa: SLF001
        track, autoplay=True, force=True, tried=set(), was_playing=False
    )

    retries = client.resolve_calls[before:]
    assert retries
    assert {call["source_id"] for call in retries} == {QQ.id}
    assert {call["payload"]["id"] for call in retries} == {"qq-3"}
    assert {call["quality"] for call in retries} == {"standard", "higher", "320k"}
    assert controller._quality == "standard"  # 失败重试不永久降级全局音质
    assert client.search_calls == []


# ------------------------------------ 6. 旧别名不得复用原音源 raw / 歌曲 ID
def test_alias_payload_never_reuses_foreign_ids(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    controller, _engine = _controller(library, client)  # 故意没有绑定服务

    # (a) 旧数据：只有映射，没有目标 raw。
    source_memory.remember_track(track, Track(
        id="alias", kind="online", source_id=QQ.id, remote_id="qq-3",
        title=track.title, artist=track.artist, album=track.album,
        duration_ms=track.duration_ms, raw={},
    ))
    controller.play_tracks([track], 0)
    call = client.resolve_calls[0]
    assert call["source_id"] == QQ.id
    assert call["payload"]["id"] == "qq-3"
    assert "kg-1" not in str(call["payload"])

    # (b) 更旧的记忆里 raw 是原音源（酷狗）的 item：必须整体丢弃。
    source_memory.clear()
    source_memory._write({  # noqa: SLF001 - 模拟 1.3.17 之前写出的 JSON
        "tracks": {
            track.id: {
                "source_id": QQ.id, "source_name": QQ.name, "remote_id": "qq-3",
                "title": track.title, "artist": track.artist, "album": track.album,
                "duration_ms": 269000, "saved_at": time.time(),
                "raw": dict(KG_ITEM),
            }
        },
        "source_map": {},
        "preferred": {},
    })
    client2 = RecordingClient()
    controller2, _engine2 = _controller(library, client2)
    controller2.play_tracks([track], 0)
    call2 = client2.resolve_calls[0]
    assert call2["source_id"] == QQ.id
    assert call2["payload"]["id"] == "qq-3"
    assert "kg-1" not in str(call2["payload"])


# ---------------------------------- 7. 跨源回退成功，播放确认后真正写库
def test_fallback_success_is_written_after_playback(library):
    track = _track(source=KG, remote="kg-1")
    library.tracks.upsert(track)
    client = RecordingClient(
        fail_sources={KG.id},
        search_by_source={WY.id: [WY_ITEM], QQ.id: []},
    )
    service, controller, engine = _setup(library, client)
    assert service.import_choice(track.id, BindingChoice.from_track(track)) is True

    controller.play_tracks([track], 0)

    assert client.search_calls, "dead KG must trigger a cross-source search"
    assert client.resolve_calls[-1]["source_id"] == WY.id
    assert service.state(track.id).verified is False
    assert library.tracks.get(track.id).source_id == KG.id

    _confirm(controller, engine)

    state = service.state(track.id)
    assert state.verified is True and state.selection_mode == "auto"
    assert library.tracks.get(track.id).source_id == WY.id


# ------------------------------- 8. 连续双击 10 次，零次跨源搜索
def test_repeated_double_clicks_never_search(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, _engine = _setup(library, client)
    assert service.manual_choose(track.id, _choice()) is True

    for _ in range(10):
        current = library.tracks.get(track.id)
        controller.play_tracks([current], 0)

    assert client.search_calls == []
    assert len(controller.loaded) == 10
    assert {call["source_id"] for call in client.resolve_calls} == {QQ.id}


# ------------------------------------------- 9. 重启后正式绑定仍然稳定
def test_binding_is_stable_after_restart(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, _engine = _setup(library, client)
    assert service.import_choice(track.id, _choice()) is True
    controller.play_tracks([track], 0)
    controller._on_position(400)  # noqa: SLF001 - 让回退逻辑无从发生

    class _RestartedLibrary:
        pass

    restarted = _RestartedLibrary()
    restarted.db = Database(library.db_path)
    restarted.tracks = TrackRepository(restarted.db)
    service2 = TrackBindingService(restarted)
    restarted.source_bindings = service2
    client2 = RecordingClient()
    controller2, _engine2 = _controller(restarted, client2)

    row = restarted.tracks.get(track.id)
    assert row is not None
    controller2.play_tracks([row], 0)

    assert client2.search_calls == []
    assert [call["source_id"] for call in client2.resolve_calls] == [QQ.id]
    assert list(client2.resolve_calls[0]["payload"].values()).count("qq-3") == 1


# ------------------------- 10. 重复导入不覆盖 manual / 有效 auto-verified
def test_reimport_never_downgrades_verified_binding(library):
    track = _track()
    library.tracks.upsert(track)
    service, _controller_, _engine = _setup(library, RecordingClient())
    assert service.import_choice(track.id, _choice()) is True
    revision = service.state(track.id).revision
    assert service.mark_play_verified(track.id, expected_revision=revision) is True
    assert service.state(track.id).verified is True

    # 同一首歌再次导入，匹配器这次给的是网易云结果。
    duplicate = _track(source=WY, remote="wy-9", raw=WY_ITEM)
    row = MatchRow(
        entry=PlaylistEntry(title="晴天", artist="周杰伦", origin_platform="wy"),
        status="matched",
        track=duplicate,
    )
    _bind_import_choices(library, [row])

    state = service.state(track.id)
    assert state.verified is True
    assert library.tracks.get(track.id).source_id == QQ.id


# ------------------------------- 11. 快速 A→B→A，迟到回调不写错歌曲
def test_rapid_switch_late_callbacks_do_not_cross(library):
    first = _track("a", KG, "kg-1")
    second = _track("b", WY, "wy-9", raw=WY_ITEM, title="稻香")
    library.tracks.upsert(first)
    library.tracks.upsert(second)
    client = RecordingClient(defer=True)
    controller, _engine = _controller(library, client)

    controller.play_tracks([first], 0)
    controller.play_tracks([second], 0)
    controller.play_tracks([first], 0)
    assert len(client.pending) == 3

    client.flush()

    assert controller._track is not None  # noqa: SLF001
    assert controller._track.id == "a"  # noqa: SLF001
    assert controller._attempt is not None  # noqa: SLF001
    assert controller._attempt["track_id"] == "a"  # noqa: SLF001
    assert len(controller.loaded) == 1


# ----------------------------------- 12. 失败必须归因到真正尝试的音源
def test_failure_is_attributed_to_the_bound_source(library):
    track = _track(source=KG, remote="kg-1")
    library.tracks.upsert(track)
    client = RecordingClient(
        fail_sources={QQ.id},
        search_by_source={KG.id: [], WY.id: []},
    )
    service, controller, _engine = _setup(library, client)
    assert service.manual_choose(track.id, _choice()) is True

    controller.play_tracks([track], 0)

    assert health.recently_failed(QQ.id) is True
    assert health.recently_failed(KG.id) is False
    assert health.recently_failed(WY.id) is False
    assert sorted({source for source, _ in client.search_calls}) == sorted([KG.id, WY.id])
    assert len(client.search_calls) == 2  # 每个源只搜一次，不会循环重搜


# ------------------------ 13. 只有短暂 playing / 无真实推进，不判 verified
def test_brief_playing_without_progress_does_not_verify(library):
    track = _track(source=QQ, remote="qq-3", raw=QQ_ITEM)
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, engine = _setup(library, client)
    assert service.import_choice(track.id, BindingChoice.from_track(track)) is True

    controller.play_tracks([track], 0)
    engine.fake_state = "playing"
    controller._on_state("playing")  # noqa: SLF001

    controller._on_position(1300)  # 一次性大跳（seek/恢复）不算推进
    assert service.state(track.id).verify_state == "pending"

    engine.fake_state = "paused"
    controller._on_position(1400)  # 暂停状态下的位置变化不算播放
    assert service.state(track.id).verify_state == "pending"


# ------------ 14. seek / 暂停 / 音质降级 / URL 过期不会改写正式绑定
def test_seek_pause_quality_and_expiry_keep_binding(library):
    track = _track()
    library.tracks.upsert(track)
    client = RecordingClient()
    service, controller, engine = _setup(library, client)
    assert service.manual_choose(track.id, _choice()) is True

    controller.play_tracks([track], 0)
    _confirm(controller, engine)
    revision = service.state(track.id).revision
    assert library.tracks.get(track.id).source_id == QQ.id

    # 真实 seek：位置一次跳很远，但绝不能因此改写绑定。
    engine.fake_state = "playing"
    controller._on_position(60_000)  # noqa: SLF001
    assert service.state(track.id).revision == revision
    assert library.tracks.get(track.id).source_id == QQ.id

    # 暂停后再恢复位置，不做播放确认。
    engine.fake_state = "paused"
    controller._on_position(61_000)  # noqa: SLF001
    assert service.state(track.id).revision == revision

    # URL 过期：同一 source/remote 换音质重试，仍然写回同一条绑定。
    engine.fake_state = "playing"
    before = len(client.resolve_calls)
    client.fail_quality_once.add((QQ.id, "standard"))
    controller._resolve_online(  # noqa: SLF001
        track, autoplay=True, force=True, tried=set(), was_playing=False
    )
    retries = client.resolve_calls[before:]
    assert [call["quality"] for call in retries] == ["standard", "higher"]
    assert {call["source_id"] for call in retries} == {QQ.id}
    assert {call["payload"]["id"] for call in retries} == {"qq-3"}
    assert service.state(track.id).revision == revision
    assert service.state(track.id).selection_mode == "manual"
    assert controller._quality == "standard"  # noqa: SLF001
