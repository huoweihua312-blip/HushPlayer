"""在线音源：Node 运行时协议、错误处理与真实搜索/解析。

真实网络用例标记为 ``network``，无网络时会 skip，不会伪造结果。
所有等待都跑真实的 Qt 事件循环（``QEventLoop``），避免忙等导致 QProcess 重入。
"""

from __future__ import annotations

import shutil

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from hushplayer.online import models
from hushplayer.online.client import OnlineSourceClient

pytestmark = pytest.mark.network


def node_available() -> bool:
    return bool(shutil.which("node"))


def wait_for_signal(signal, timeout: float = 30.0):
    """跑事件循环直到 signal 触发，返回其参数列表（超时返回 None）。"""
    loop = QEventLoop()
    payload: list = []

    def on_signal(*args):
        payload.extend(args)
        loop.quit()

    signal.connect(on_signal)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(int(timeout * 1000))
    loop.exec()
    timer.stop()
    try:
        signal.disconnect(on_signal)
    except (RuntimeError, TypeError):
        pass
    return payload or None


def call(client: OnlineSourceClient, method: str, *args, timeout: float = 40.0, **kwargs):
    """调用客户端方法并等待其回调，返回 response dict（超时返回 None）。"""
    loop = QEventLoop()
    result: dict = {}

    def callback(response):
        result.update(response)
        loop.quit()

    getattr(client, method)(*args, callback, **kwargs)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(int(timeout * 1000))
    loop.exec()
    timer.stop()
    return result or None


_KEEP_ALIVE: list[OnlineSourceClient] = []


@pytest.fixture(scope="module")
def client(qapp):
    """整个模块共用一个 Node 运行时：反复创建/销毁 QProcess 在 PySide6 上不稳定。"""
    if not node_available():
        pytest.skip("未安装 Node.js，跳过在线音源集成测试")
    instance = OnlineSourceClient()
    started = instance.ensure_started()
    assert started, instance.last_error
    _KEEP_ALIVE.append(instance)
    yield instance
    instance.stop()
    assert instance.running is False


def _netease(client: OnlineSourceClient):
    """网易云音源的 platform 值随插件不同（wy / netease / 网易音乐），按名称匹配。"""
    for source in models.build_sources(client.sources):
        if "网易" in f"{source.platform}{source.name}{source.label}":
            return source
    return None


def ensure_sources(client: OnlineSourceClient) -> None:
    if not client.sources:
        wait_for_signal(client.sources_changed, timeout=25.0)
    assert client.sources, "音源列表加载超时"


def test_lists_real_sources(client) -> None:
    ensure_sources(client)
    sources = models.build_sources(client.sources)
    assert sources, "至少应有一个已安装音源"
    playable = [source for source in sources if source.can_play]
    assert playable, "网易云/酷我等音源应支持播放"
    for source in sources:
        assert source.id and source.name
        assert source.label


def test_search_returns_real_items(client) -> None:
    ensure_sources(client)
    netease = _netease(client)
    if netease is None:
        pytest.skip("没有安装网易云音源")
    response = call(client, "search", netease.id, "夜航", 1, timeout=45.0)
    assert response is not None, "搜索超时"
    assert response.get("ok") is True, response
    items = response.get("data") or []
    assert items, "应返回真实搜索结果"
    track = models.track_from_item(items[0], source=netease)
    assert track.kind == "online"
    assert track.title
    assert track.source_id == netease.id
    assert track.id.startswith("online:")
    assert models.runtime_track(track).get("id")


def test_resolve_playback_returns_http_url(client) -> None:
    ensure_sources(client)
    netease = _netease(client)
    if netease is None:
        pytest.skip("没有安装网易云音源")
    response = call(client, "search", netease.id, "晴天 周杰伦", 1, timeout=45.0)
    assert response is not None, "搜索超时"
    if not response.get("ok") or not response.get("data"):
        pytest.skip(f"搜索无结果（可能是网络受限）：{response.get('error')}")
    track = models.track_from_item(response["data"][0], source=netease)
    resolved = call(
        client,
        "resolve_playback",
        netease.id,
        models.runtime_track(track),
        quality="standard",
        timeout=45.0,
    )
    assert resolved is not None, "播放地址解析超时"
    assert resolved.get("ok") is True, resolved
    url = (resolved.get("data") or {}).get("url", "")
    assert url.startswith("http"), url


def test_unknown_source_reports_error(client) -> None:
    ensure_sources(client)
    response = call(client, "search", "does-not-exist", "test", 1, timeout=20.0)
    assert response is not None
    assert response.get("ok") is False
    assert response.get("error")


def test_stop_is_clean(client) -> None:
    assert client.running is True
    client.stop()
    assert client.running is False
