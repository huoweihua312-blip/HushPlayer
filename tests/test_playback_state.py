"""BUG-02 回归：在线解析/缓冲阶段的暂停与终止不能把状态机卡死。

用户反馈「网易云无法正常暂停或停止」。真实机制不是 Qt 不会暂停，而是：
在线解析失败或代理取流失败后，控制器停留在 ``loading``、``_busy=True``，
于是 ``pause()`` 静默无效、``toggle()`` 无反应，传输控件看起来是死的。
这些用例用可控的假音源客户端复现那条路径。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.online.models import SourceInfo, track_from_item

ONLINE_ITEM = {
    "id": "test-remote-1",
    "title": "晴天",
    "artist": "周杰伦",
    "album": "叶惠美",
    "duration": 269000,
}

SOURCE = SourceInfo(
    id="custom_source_test",
    name="测试音源",
    platform="wy",
    enabled=True,
    user_installed=True,
    content_policy="open",
    capabilities={"search": True, "playback": True, "lyrics": True},
)


class FakeClient(QObject):
    """最小音源客户端：把 resolve 回调留在队列里，由测试决定何时失败。"""

    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pending: list = []
        self.searches: list = []

    def resolve_playback(self, source_id, payload, callback, **kwargs):  # noqa: ANN001
        self.pending.append(callback)
        return len(self.pending)

    def search(self, source_id, keyword, page=1, callback=None, **kwargs):  # noqa: ANN001
        self.searches.append((source_id, keyword))
        return 0

    def stop(self) -> None:
        return None


def make_controller(qapp) -> tuple[PlayerController, FakeClient, PlaybackEngine]:
    engine = PlaybackEngine()
    client = FakeClient()
    controller = PlayerController(engine=engine, client=client)
    controller.set_volume(0.0)
    controller._sources = [SOURCE]  # noqa: SLF001 - test seam
    return controller, client, engine


def online_track():
    return track_from_item(ONLINE_ITEM, source=SOURCE)


def test_pause_while_resolving_cancels_pending_playback(qapp) -> None:
    controller, client, engine = make_controller(qapp)
    track = online_track()
    controller.play_track(track)
    assert controller.state == "loading"
    assert controller.busy is True

    controller.pause()

    assert controller.state == "paused", "解析中的暂停应落到 paused，而不是保持 loading"
    assert controller.busy is False, "取消后必须清除 busy 标记"
    assert engine.is_playing_actual is False

    # 迟到的解析结果不能再偷偷开始播放
    client.pending[0]({"ok": True, "data": {"url": "http://127.0.0.1:9/x.mp3"}})
    assert controller.state == "paused"
    assert engine.is_playing_actual is False
    assert controller.current.id == track.id

    # 控件仍然可用：再按一次会重新发起解析
    controller.toggle()
    assert len(client.pending) == 2, "暂停后应能重新开始播放"
    assert controller.state == "loading"
    controller.stop()
    controller.shutdown()


def test_failed_resolve_settles_stopped_and_keeps_controls_alive(qapp) -> None:
    controller, client, engine = make_controller(qapp)
    errors: list[str] = []
    controller.error_message.connect(errors.append)
    controller.play_track(online_track())

    # 解析失败后控制器会依次尝试其它音质；把它们全部答成失败，模拟整条链都不可用。
    for _ in range(8):
        if not client.pending:
            break
        client.pending.pop(0)({"ok": False, "error": "音源未提供可用的播放资源（可能受版权或会员限制）"})

    assert engine.state == "stopped", "终止失败后必须离开 loading"
    assert controller.busy is False
    assert controller.state == "stopped"
    assert errors, "应给出可见的错误提示"

    # 停止后仍可以重新开始播放，说明传输控件没有被卡死
    before = len(client.pending)
    controller.toggle()
    assert len(client.pending) == before + 1
    assert controller.state == "loading"
    controller.stop()
    controller.shutdown()


def test_stop_clears_busy_and_cancels_late_result(qapp) -> None:
    controller, client, engine = make_controller(qapp)
    controller.play_track(online_track())
    controller.stop()

    assert engine.state == "stopped"
    assert controller.busy is False
    assert controller.position == 0

    client.pending[0]({"ok": True, "data": {"url": "http://127.0.0.1:9/x.mp3"}})
    assert engine.state == "stopped", "停止后迟到的解析结果不能重新开始播放"
    controller.shutdown()


def test_engine_halt_pending_leaves_pausable_state(qapp) -> None:
    engine = PlaybackEngine()
    # 一个永远连不上的地址会让 Qt 停在 loading
    engine.load("http://127.0.0.1:9/never.mp3", autoplay=True)
    assert engine.state == "loading"
    engine.halt_pending()
    assert engine.state == "paused"
    engine.stop()
    assert engine.state == "stopped"
    engine.shutdown()

def test_rapid_next_resolves_each_track_once(qapp) -> None:
    controller, client, engine = make_controller(qapp)
    tracks = [
        track_from_item({**ONLINE_ITEM, "id": f"rapid-{i}", "title": f"曲 {i}"}, source=SOURCE)
        for i in range(3)
    ]
    controller.play_tracks(tracks, 0)
    assert len(client.pending) == 1

    controller.next()
    controller.next()

    assert controller.current.id == tracks[2].id, "连按两次下一首应停在第三首"
    assert len(client.pending) == 3, "每首歌只应发起一次解析（信号与显式加载不重复）"
    controller.stop()
    controller.shutdown()
