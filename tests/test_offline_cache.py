"""1.3.19 回归：完整磁盘缓存优先于联网解析。

任务书问题三。核心约束（与真实缓存文件、真实 HTTP 下载一起验证）：

* 完整缓存命中时**不调用 search / resolve_playback**，插件被禁用、断网也能播；
* 缓存校验必须同时满足：索引 complete、实际大小与索引一致、缓存键与音质匹配；
* 截断文件、半截文件、坏索引不能被当成完整音频；
* 缓存只是音频来源，不能改写正式绑定身份（手动绑定换源后不得播旧源缓存）；
* 音质档位与插件实际返回不一致时仍能找到缓存；
* 容量清理不得删除正在播放的条目。
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import QObject, Signal

from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.online.models import SourceInfo, track_from_item
from hushplayer.online.proxy import AudioProxy, token_for, valid_cache_file

WY = SourceInfo(
    id="custom_source_wy",
    name="网易云",
    platform="wy",
    enabled=True,
    capabilities={"search": True, "playback": True},
)
QQ = SourceInfo(
    id="custom_source_qq",
    name="QQ音乐",
    platform="qq",
    enabled=True,
    capabilities={"search": True, "playback": True},
)
KG = SourceInfo(
    id="custom_source_kg",
    name="酷狗",
    platform="kg",
    enabled=True,
    capabilities={"search": True, "playback": True},
)

ITEM = {
    "id": "wy-9",
    "title": "夜航信号",
    "artist": "Aurora Field",
    "album": "夜间电台",
    "duration": 269000,
}


class SilentClient(QObject):
    """记录一切联网调用的假客户端；resolve 永远成功，方便判断是否真的没联网。"""

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
            {
                "source_id": source_id,
                "payload": dict(payload or {}),
                "quality": str(kwargs.get("quality") or "standard"),
            }
        )
        if callback is not None:
            callback(
                {
                    "ok": True,
                    "data": {
                        "url": f"https://cdn.example.com/{source_id}/1.mp3",
                        "headers": {},
                        "mimeType": "audio/mpeg",
                        "quality": "standard",
                    },
                }
            )
        return len(self.resolve_calls)

    def cancel(self, request_id) -> None:  # noqa: ANN001
        return None

    def stop(self) -> None:
        return None


class _State:
    revision = 3
    manual = True
    verified = True


class FakeBinding:
    """只实现控制器用到的绑定接口，用于「手动换源」场景。"""

    def __init__(self, target) -> None:  # noqa: ANN001
        self.target = target

    def get_target(self, track_id):  # noqa: ANN001
        return self.target

    def state(self, track_id):  # noqa: ANN001
        return _State()

    def mark_failed(self, track_id, *, expected_revision: int):  # noqa: ANN001
        return True

    def mark_play_verified(self, track_id, *, expected_revision: int, choice=None):  # noqa: ANN001
        return True

    def adopt_verified_fallback(self, track_id, choice, *, expected_revision: int):  # noqa: ANN001
        return True

    def notify_updated(self, track_id) -> None:  # noqa: ANN001
        return None


def _controller(qapp, proxy, *, binding=None, sources=(WY,)):
    engine = PlaybackEngine()
    client = SilentClient()
    loads: list[str] = []

    def fake_load(source, *, duration_hint: int = 0, autoplay: bool = True) -> None:  # noqa: ANN001
        loads.append(str(source))
        engine._state = "playing" if autoplay else "paused"

    engine.load = fake_load  # type: ignore[method-assign]
    controller = PlayerController(
        engine=engine, client=client, proxy=proxy, binding=binding
    )
    controller.set_volume(0.0)
    controller._sources = list(sources)  # noqa: SLF001 - test seam
    return controller, client, loads, engine


def _play(controller, track) -> None:  # noqa: ANN001
    controller.play_tracks([track], 0)


def _write_cache(
    proxy: AudioProxy,
    cache_key: str,
    *,
    size: int = 2048,
    suffix: str = ".mp3",
    overrides: dict | None = None,
):
    token = token_for(cache_key)
    media = proxy.cache_dir / f"{token}{suffix}"
    media.write_bytes(b"\x00" * size)
    meta = {
        "complete": True,
        "size": size,
        "key": cache_key,
        "quality": cache_key.rsplit(":", 1)[-1],
        "url": "http://example.invalid/audio.mp3",
    }
    meta.update(overrides or {})
    (proxy.cache_dir / f"{token}.meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return media


@pytest.fixture()
def proxy(data_dir):
    return AudioProxy(cache_dir=data_dir / "audio")


def test_complete_cache_skips_resolve_and_search(qapp, proxy) -> None:
    track = track_from_item(ITEM, source=WY)
    media = _write_cache(proxy, f"{WY.id}:{track.remote_id}:standard")

    controller, client, loads, _engine = _controller(qapp, proxy)
    _play(controller, track)

    assert loads == [str(media)]
    assert client.resolve_calls == []
    assert client.search_calls == []


def test_cache_plays_when_source_plugin_is_unavailable(qapp, proxy) -> None:
    track = track_from_item(ITEM, source=WY)
    media = _write_cache(proxy, f"{WY.id}:{track.remote_id}:standard")

    controller, client, loads, _engine = _controller(qapp, proxy, sources=())
    _play(controller, track)

    assert loads == [str(media)]
    assert client.resolve_calls == []


def test_truncated_cache_is_rejected_and_online_used(qapp, proxy) -> None:
    track = track_from_item(ITEM, source=WY)
    media = _write_cache(proxy, f"{WY.id}:{track.remote_id}:standard", size=2048)
    media.write_bytes(b"\x00" * 500)  # 截断：索引说 2048，实际 500

    assert proxy.local_path(f"{WY.id}:{track.remote_id}:standard") == ""
    assert not media.exists(), "损坏条目应被清理，避免下次继续误判"

    controller, client, loads, _engine = _controller(qapp, proxy)
    _play(controller, track)

    assert len(client.resolve_calls) == 1
    # 在线路径播放的是本地代理地址（真正的音频流由代理负责），不是缓存文件。
    assert loads and loads[-1].startswith("http://127.0.0.1:")


def test_missing_cache_falls_back_to_online(qapp, proxy) -> None:
    track = track_from_item(ITEM, source=WY)
    controller, client, loads, _engine = _controller(qapp, proxy)
    _play(controller, track)

    assert len(client.resolve_calls) == 1
    assert client.resolve_calls[0]["source_id"] == WY.id
    assert loads and loads[-1].startswith("http://127.0.0.1:")


def test_cache_disabled_skips_local_playback(qapp, proxy) -> None:
    track = track_from_item(ITEM, source=WY)
    _write_cache(proxy, f"{WY.id}:{track.remote_id}:standard")

    controller, client, loads, _engine = _controller(qapp, proxy)
    controller.configure(cache_enabled=False)
    _play(controller, track)

    assert len(client.resolve_calls) == 1
    # 在线路径播放的是本地代理地址（真正的音频流由代理负责），不是缓存文件。
    assert loads and loads[-1].startswith("http://127.0.0.1:")


def test_corrupt_meta_is_not_trusted(qapp, proxy) -> None:
    track = track_from_item(ITEM, source=WY)
    _write_cache(
        proxy,
        f"{WY.id}:{track.remote_id}:standard",
        overrides={"complete": False},
    )

    controller, client, loads, _engine = _controller(qapp, proxy)
    _play(controller, track)

    assert len(client.resolve_calls) == 1
    # 在线路径播放的是本地代理地址（真正的音频流由代理负责），不是缓存文件。
    assert loads and loads[-1].startswith("http://127.0.0.1:")


def test_quality_variant_cache_is_found(qapp, proxy) -> None:
    """插件可能返回 320k，请求的是 standard；不同扩展名也要能命中。"""
    track = track_from_item(ITEM, source=WY)
    media = _write_cache(
        proxy, f"{WY.id}:{track.remote_id}:320k", suffix=".flac"
    )

    controller, client, loads, _engine = _controller(qapp, proxy)
    _play(controller, track)

    assert loads == [str(media)]
    assert client.resolve_calls == []


def test_manual_rebind_never_plays_old_source_cache(qapp, proxy) -> None:
    # 队列里还是旧身份（酷狗），但正式绑定已是 QQ：只允许播 QQ。
    queued = track_from_item(dict(ITEM, id="kg-1"), source=KG)
    bound = track_from_item(dict(ITEM, id="qq-3"), source=QQ)
    _write_cache(proxy, f"{KG.id}:kg-1:standard")

    controller, client, loads, _engine = _controller(
        qapp, proxy, binding=FakeBinding(bound), sources=(KG, QQ)
    )
    _play(controller, queued)

    assert client.resolve_calls and client.resolve_calls[0]["source_id"] == QQ.id
    assert client.resolve_calls[0]["payload"]["id"] == "qq-3"
    assert not any("kg-1" in path for path in loads)


def test_prune_keeps_playing_entry(proxy) -> None:
    keys = [f"{WY.id}:{i}:standard" for i in range(1, 4)]
    files = []
    for index, key in enumerate(keys):
        media = _write_cache(proxy, key, size=1000)
        stamp = time.time() - (30 - index * 10)
        os.utime(media, (stamp, stamp))
        files.append(media)

    proxy.note_playing(keys[1])  # b 正在播放
    # 预算只够留下一个条目：最旧的 a 与最新的 c 都应被清掉，b 因正在播放而保留。
    proxy.prune(900)

    assert files[1].exists(), "正在播放的缓存不能被清理"
    assert not files[0].exists()
    assert not files[2].exists()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    payload = b"\xff\xfb" + b"\x00" * 2998

    def log_message(self, fmt, *args):  # noqa: ANN001, D102
        return None

    def do_GET(self) -> None:  # noqa: N802
        body = self.payload
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_real_download_is_stored_with_identity_and_reused(qapp, proxy) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/song.mp3"
    key = f"{WY.id}:wy-9:higher"
    try:
        proxy.register(key, url, {}, mime="audio/mpeg", ext=".mp3", quality="higher")

        path = ""
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            path = proxy.local_path(key)
            if path:
                break
            time.sleep(0.05)

        assert path, "真实 HTTP 下载完成后应能命中缓存"
        hit = valid_cache_file(proxy.cache_dir, key)
        assert hit is not None and hit[1]["quality"] == "higher"
        assert os.path.getsize(path) == len(_Handler.payload)

        again = proxy.register(
            key, url, {}, mime="audio/mpeg", ext=".mp3", quality="higher"
        )
        assert again.startswith("http://127.0.0.1:")
        assert proxy.local_path(key) == path
    finally:
        server.shutdown()
        server.server_close()
