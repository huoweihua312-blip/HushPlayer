"""预加载：提前解析下一首在线歌曲，切歌时不再等解析。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.online.models import SourceInfo, track_from_item

SOURCE = SourceInfo(
    id="src_test", name="测试源", platform="wy", enabled=True,
    capabilities={"search": True, "playback": True},
)


class FakeClient(QObject):
    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.callbacks: list = []

    def resolve_playback(self, source_id, payload, callback, **kwargs):  # noqa: ANN001
        self.calls.append(str(payload.get("id") or payload.get("songmid") or ""))
        self.callbacks.append(callback)
        return len(self.calls)

    def stop(self) -> None:
        return None


def _track(index: int):
    item = {"id": f"r{index}", "title": f"歌曲{index}", "artist": "歌手", "duration": 200000}
    return track_from_item(item, source=SOURCE)


def test_preload_resolves_next_and_next_uses_it(qapp):
    engine = PlaybackEngine()
    client = FakeClient()
    controller = PlayerController(engine=engine, client=client)
    controller.set_volume(0.0)
    controller._sources = [SOURCE]  # noqa: SLF001 - test seam
    loaded: list = []
    engine.load = lambda *a, **kw: loaded.append((a, kw))  # type: ignore[assignment]
    controller.proxy.register = lambda *a, **kw: "http://127.0.0.1:9/audio/x"  # type: ignore[assignment]

    first, second = _track(1), _track(2)
    controller.play_tracks([first, second], 0, context="test")
    assert client.calls == ["r1"], client.calls
    client.callbacks[0]({"ok": True, "data": {"url": "https://x/1.mp3", "headers": {}}})

    controller.preload_next()
    assert client.calls == ["r1", "r2"], "下一首的解析应提前发出"
    client.callbacks[1]({"ok": True, "data": {"url": "https://x/2.mp3", "headers": {}}})
    assert second.id in controller._preloaded  # noqa: SLF001 - test seam

    before = len(client.calls)
    controller.next()
    # 切歌时消费预加载结果，不再发起新的解析请求
    assert len(client.calls) == before, client.calls
