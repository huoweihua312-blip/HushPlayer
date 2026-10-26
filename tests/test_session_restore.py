"""1.3.19 回归：音量/静音/进度的持久化，以及「恢复会话不自动播放」。

任务书问题一、问题二。核心约束：

* 播放器是音量的真实来源（音量条、快捷键、沉浸页都直接调它），变更必须写回
  设置，否则重启回到默认值；
* 恢复会话只恢复队列/当前曲目/进度，**不 load、不 resolve、不 next**；
* 恢复失败不能覆盖上一次有效的会话文件。
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest

from hushplayer.app import HushApp
from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.core import paths
from hushplayer.core.settings import Settings
from hushplayer.online.models import SourceInfo, track_from_item
from hushplayer.online.proxy import AudioProxy
from hushplayer.services.state import PlaybackKeeper, queue_file

SOURCE = SourceInfo(
    id="custom_source_test",
    name="测试音源",
    platform="wy",
    enabled=True,
    capabilities={"search": True, "playback": True},
)

ONLINE_ITEM = {
    "id": "remote-1",
    "title": "晴天",
    "artist": "周杰伦",
    "album": "叶惠美",
    "duration": 269000,
}


class SilentClient(QObject):
    """不联网的假客户端：任何 search/resolve 都会被记录下来。"""

    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.resolve_calls: list[dict] = []
        self.search_calls: list[tuple[str, str]] = []

    def search(self, source_id, keyword, page=1, callback=None, **kwargs):  # noqa: ANN001
        self.search_calls.append((source_id, keyword))
        if callback is not None:
            callback({"ok": True, "data": []})
        return 0

    def resolve_playback(self, source_id, payload, callback, **kwargs):  # noqa: ANN001
        self.resolve_calls.append(
            {"source_id": source_id, "payload": dict(payload or {}),
             "quality": str(kwargs.get("quality") or "standard")}
        )
        if callback is not None:
            callback({"ok": True, "data": {
                "url": f"https://cdn.example.com/{source_id}/1.mp3",
                "headers": {}, "mimeType": "audio/mpeg", "quality": "standard",
            }})
        return len(self.resolve_calls)

    def cancel(self, request_id) -> None:  # noqa: ANN001
        return None

    def stop(self) -> None:
        return None


def _controller(qapp, tracks=None, *, silent_queue: bool = True):
    engine = PlaybackEngine()
    client = SilentClient()
    controller = PlayerController(engine=engine, client=client)
    controller.set_volume(0.0)
    controller._sources = [SOURCE]  # noqa: SLF001 - test seam
    if tracks:
        controller._silent_current = True if silent_queue else False
        try:
            controller.queue.set_tracks(list(tracks), 0, context="专辑 · 测试")
        finally:
            controller._silent_current = False
    return controller, client, engine


def _online():
    return track_from_item(ONLINE_ITEM, source=SOURCE)


class _AppStub:
    """只带设置相关方法的 HushApp 替身（避免启动整套 GUI 服务）。"""

    _on_player_volume_changed = HushApp._on_player_volume_changed
    _on_player_muted_changed = HushApp._on_player_muted_changed
    _apply_cache_settings = HushApp._apply_cache_settings
    _configure_player = HushApp._configure_player
    _connect_settings = HushApp._connect_settings

    def __init__(self, settings, player, proxy=None) -> None:
        self.settings = settings
        self.player = player
        self.proxy = proxy

    def _on_setting_changed(self, key, value) -> None:  # noqa: ANN001
        return None


# --------------------------------------------------------------- 音量 / 静音
def test_volume_survives_restart(qapp, data_dir, monkeypatch) -> None:
    settings = Settings(paths.settings_file())
    settings.load()
    controller, _client, _engine = _controller(qapp)
    stub = _AppStub(settings, controller)
    stub._connect_settings()

    controller.set_volume(0.35)
    assert settings.get("playback.volume") == pytest.approx(0.35)
    settings.flush()

    reloaded = Settings(paths.settings_file())
    reloaded.load()
    assert reloaded.get("playback.volume") == pytest.approx(0.35)

    proxy = AudioProxy(cache_dir=data_dir / "audio")
    fresh, _c, _e = _controller(qapp)
    fresh_stub = _AppStub(reloaded, fresh, proxy)
    fresh_stub._configure_player()
    assert fresh.volume == pytest.approx(0.35)
    assert fresh._muted is False  # noqa: SLF001


def test_mute_survives_restart(qapp, data_dir) -> None:
    settings = Settings(paths.settings_file())
    settings.load()
    controller, _client, _engine = _controller(qapp)
    stub = _AppStub(settings, controller)
    stub._connect_settings()

    controller.set_muted(True)
    assert settings.get("playback.muted") is True
    settings.flush()

    reloaded = Settings(paths.settings_file())
    reloaded.load()
    assert reloaded.get("playback.muted") is True

    proxy = AudioProxy(cache_dir=data_dir / "audio")
    fresh, _c, _e = _controller(qapp)
    _AppStub(reloaded, fresh, proxy)._configure_player()
    assert fresh.muted is True
    assert fresh._muted is True  # noqa: SLF001


def test_player_volume_written_once_per_change(qapp, data_dir) -> None:
    """播放器回写设置不能形成「设置→播放器→设置」死循环或多次写盘。"""
    settings = Settings(paths.settings_file())
    settings.load()
    controller, _client, _engine = _controller(qapp)
    stub = _AppStub(settings, controller)
    stub._connect_settings()

    writes: list[tuple[str, object]] = []

    def sink(key, value) -> None:  # noqa: ANN001
        writes.append((key, value))

    settings.changed.connect(sink)

    controller.set_volume(0.5)
    controller.set_volume(0.5)  # 同一个值：第二次不应再写
    assert [key for key, _value in writes].count("playback.volume") == 1


# ------------------------------------------------------------------- 进度恢复
def test_paused_position_restores_same_track(qapp, loaded_library) -> None:
    tracks = loaded_library.tracks.list(limit=3)
    controller, _client, _engine = _controller(qapp, tracks)
    track = controller.queue.current
    assert track is not None

    controller._track = track  # noqa: SLF001 - 模拟已播放
    controller._position = 5_000  # noqa: SLF001
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    keeper.save_now()

    fresh, _c, _e = _controller(qapp)
    fresh_keeper = PlaybackKeeper(fresh, loaded_library.tracks)
    position = fresh_keeper.restore()
    fresh.restore_current(position)

    assert fresh.queue.count == 3
    assert fresh.current_track is not None and fresh.current_track.id == track.id
    assert fresh.position == 5_000
    # 只摆状态：没有真正开流。
    assert fresh._restored_pending is True  # noqa: SLF001
    assert fresh.engine.state == "stopped"


def test_seek_then_quick_exit_saves_progress(qapp, loaded_library) -> None:
    tracks = loaded_library.tracks.list(limit=2)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)

    controller._position = 1_000  # noqa: SLF001
    controller.position_changed.emit(1_000)  # 建立基线
    controller._position = 90_000  # noqa: SLF001
    controller.position_changed.emit(90_000)  # 跳变 = 用户拖动
    QTest.qWait(1_000)  # 防抖 800ms 后落盘

    raw = json.loads(open(queue_file(), "r", encoding="utf-8").read())
    assert int(raw["position_ms"]) == 90_000
    keeper.flush()


def test_shutdown_stop_does_not_clobber_saved_progress(qapp, loaded_library) -> None:
    """退出时引擎 stop() 把位置清零，不得覆盖 flush() 刚写好的真实进度。"""
    tracks = loaded_library.tracks.list(limit=3)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    controller._position = 0  # noqa: SLF001
    controller._track = controller.queue.current  # noqa: SLF001
    controller._position = 4_200  # noqa: SLF001
    keeper.flush()

    # 退出流程随后会 stop() 引擎：位置归零 + state_changed("stopped")。
    controller._position = 0  # noqa: SLF001
    controller.state_changed.emit("stopped")
    keeper.save_now()

    raw = json.loads(open(queue_file(), "r", encoding="utf-8").read())
    assert int(raw["position_ms"]) == 4_200


def test_restore_does_not_next_resolve_or_search(qapp, loaded_library) -> None:
    tracks = loaded_library.tracks.list(limit=2)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    keeper.save_now()

    fresh, client, engine = _controller(qapp)
    loads: list[str] = []
    fresh.engine.load = lambda source, **kwargs: loads.append(str(source))  # type: ignore[assignment]
    jumps: list[object] = []
    fresh.next = lambda *args, **kwargs: jumps.append((args, kwargs))  # type: ignore[assignment]

    fresh_keeper = PlaybackKeeper(fresh, loaded_library.tracks)
    position = fresh_keeper.restore()
    fresh.restore_current(position)

    assert fresh.queue.count == 2
    assert jumps == []
    assert client.resolve_calls == []
    assert client.search_calls == []
    assert loads == []
    assert engine.state == "stopped"


def test_restore_then_first_play_loads_once(qapp, loaded_library) -> None:
    tracks = loaded_library.tracks.list(limit=1)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    controller._position = 42_000  # noqa: SLF001
    keeper.save_now()

    fresh, client, _engine = _controller(qapp)
    loads: list[str] = []
    fresh.engine.load = lambda source, **kwargs: loads.append(str(source))  # type: ignore[assignment]
    fresh_keeper = PlaybackKeeper(fresh, loaded_library.tracks)
    position = fresh_keeper.restore()
    fresh.restore_current(position)
    assert loads == []

    # 恢复出来的是在线曲目之外的本地曲目：首次播放只允许加载一次。
    fresh.play()
    assert len(loads) == 1
    assert client.resolve_calls == []


def test_shuffle_restore_keeps_current_id(qapp, loaded_library) -> None:
    tracks = loaded_library.tracks.list(limit=4)
    controller, _client, _engine = _controller(qapp, tracks)
    controller.queue.set_shuffle(True)
    target = controller.queue.current
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    keeper.save_now()

    fresh, _c, _e = _controller(qapp)
    fresh_keeper = PlaybackKeeper(fresh, loaded_library.tracks)
    fresh_keeper.restore()
    assert fresh.queue.shuffle is True
    assert fresh.queue.current is not None
    assert fresh.queue.current.id == target.id


def test_missing_tracks_restore_current_id_not_row(qapp, loaded_library) -> None:
    tracks = loaded_library.tracks.list(limit=3)
    controller, _client, _engine = _controller(qapp, tracks)
    target = controller.queue.items[-1]  # 第三首
    controller.queue.set_current_row(len(tracks) - 1)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    keeper.save_now()

    # 第一首从库里消失：行号整体前移，但 current_id 仍指向第三首。
    loaded_library.tracks.delete([tracks[0].id])
    fresh, _c, _e = _controller(qapp)
    fresh_keeper = PlaybackKeeper(fresh, loaded_library.tracks)
    fresh_keeper.restore()
    assert fresh.queue.count == 2
    assert fresh.queue.current is not None
    assert fresh.queue.current.id == target.id


def test_failed_restore_keeps_previous_session_file(qapp, loaded_library, data_dir) -> None:
    tracks = loaded_library.tracks.list(limit=2)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    controller._position = 77_000  # noqa: SLF001
    keeper.save_now()
    before = open(queue_file(), "r", encoding="utf-8").read()

    # 队列全部失效：restore 返回 0，但绝不能删除上一次有效的会话文件。
    loaded_library.tracks.delete([track.id for track in loaded_library.tracks.list()])
    fresh, _c, _e = _controller(qapp)
    fresh_keeper = PlaybackKeeper(fresh, loaded_library.tracks)
    assert fresh_keeper.restore() == 0
    fresh_keeper.save_now()
    assert os.path.isfile(queue_file())
    assert open(queue_file(), "r", encoding="utf-8").read() == before

def test_failed_session_write_keeps_pending_state(qapp, loaded_library, monkeypatch) -> None:
    """会话写盘失败：保留待保存状态，不能把失败当成功。"""
    from hushplayer.services import state as state_module

    tracks = loaded_library.tracks.list(limit=2)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    controller._position = 42_000  # noqa: SLF001
    assert keeper.save_now() is True
    saved_position = keeper._last_saved_position

    controller._position = 95_000  # noqa: SLF001
    original = state_module.os.replace
    monkeypatch.setattr(
        state_module.os,
        "replace",
        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError(13, "denied")),
    )
    assert keeper.save_now() is False
    assert keeper._dirty is True
    assert keeper._last_saved_position == saved_position, "写失败不能更新已保存位置"

    payload = json.loads(open(queue_file(), "r", encoding="utf-8").read())
    assert payload["position_ms"] == 42_000, "失败时不得覆盖上一次有效会话"

    # 权限恢复后必须能把最新的 95000 落盘。
    monkeypatch.setattr(state_module.os, "replace", original)
    assert keeper.save_now() is True
    payload = json.loads(open(queue_file(), "r", encoding="utf-8").read())
    assert payload["position_ms"] == 95_000


def test_flush_retries_once_when_write_fails(qapp, loaded_library, monkeypatch) -> None:
    """退出路径再试一次：第一次失败、第二次成功时进度必须保住。"""
    from hushplayer.services import state as state_module

    tracks = loaded_library.tracks.list(limit=2)
    controller, _client, _engine = _controller(qapp, tracks)
    keeper = PlaybackKeeper(controller, loaded_library.tracks)
    controller._position = 12_500  # noqa: SLF001

    original = state_module.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(13, "denied")
        return original(src, dst)

    monkeypatch.setattr(state_module.os, "replace", flaky)
    keeper.flush()
    payload = json.loads(open(queue_file(), "r", encoding="utf-8").read())
    assert payload["position_ms"] == 12_500
    assert calls["n"] >= 2
