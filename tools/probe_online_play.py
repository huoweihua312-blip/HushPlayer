"""在线播放端到端验证：音源 → 代理缓存 → QMediaPlayer。

用法：.venv\\Scripts\\python.exe tools\\probe_online_play.py
会使用临时数据目录，不触碰真实用户数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="hush-online-"))
os.environ["HUSHPLAYER_DATA_DIR"] = str(TMP)

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from hushplayer.audio.engine import PlaybackEngine  # noqa: E402
from hushplayer.core.logging_setup import setup_logging  # noqa: E402
from hushplayer.online import models  # noqa: E402
from hushplayer.online.client import OnlineSourceClient  # noqa: E402
from hushplayer.online.proxy import AudioProxy  # noqa: E402

SOURCE = sys.argv[1] if len(sys.argv) > 1 else "custom_source_52a08ed9d22b"
KEYWORD = sys.argv[2] if len(sys.argv) > 2 else "周杰伦 晴天"


def main() -> int:
    setup_logging("INFO", console=False)
    app = QCoreApplication(sys.argv)
    client = OnlineSourceClient()
    engine = PlaybackEngine()
    proxy = AudioProxy(TMP / "audio_cache")

    state = {"phase": "start", "track": None, "resource": None, "started": 0.0}
    result = {"ok": False, "error": ""}

    def fail(message: str) -> None:
        result["error"] = message
        print("FAIL:", message)
        app.quit()

    def on_search(response: dict) -> None:
        if not response.get("ok"):
            return fail(f"搜索失败: {response.get('error')}")
        items = response.get("data") or []
        print("搜索结果:", len(items))
        if not items:
            return fail("搜索无结果")
        track = models.track_from_item(items[0])
        state["track"] = track
        print("曲目:", track.title, "-", track.artist, f"({track.duration_ms}ms)")
        client.resolve_playback(
            track.source_id,
            models.runtime_track(track),
            lambda r: on_resolved(r),
        )

    def on_resolved(response: dict) -> None:
        if not response.get("ok"):
            return fail(f"解析播放地址失败: {response.get('error')}")
        resource = response.get("data") or {}
        url = resource.get("url")
        print("资源:", url[:80] if url else None, "mime=", resource.get("mimeType"))
        if not url:
            return fail("没有播放地址")
        state["resource"] = resource
        track = state["track"]
        route = proxy.register(
            f"{track.source_id}:{track.remote_id}:standard",
            url,
            resource.get("headers") or {},
            mime=resource.get("mimeType", ""),
            expires_at=resource.get("expiresAt", 0),
        )
        print("代理地址:", route)
        state["phase"] = "playing"
        state["started"] = time.time()
        engine.load(route, duration_hint=track.duration_ms, autoplay=True)

    def on_state(value: str) -> None:
        print("状态:", value)
        if value == "error":
            fail("播放器进入错误状态")

    def on_position(position: int) -> None:
        if state["phase"] != "playing":
            return
        if position < 1200:
            return
        elapsed = time.time() - state["started"]
        cache = Path(proxy.local_path(f"{state['track'].source_id}:{state['track'].remote_id}:standard"))
        size = cache.stat().st_size if cache.exists() else -1
        print(f"播放中 position={position}ms elapsed={elapsed:.1f}s cache={size}B")
        if size <= 0:
            return fail("缓存文件为空")
        result["ok"] = True
        engine.stop()
        proxy.shutdown()
        client.stop()
        app.quit()

    client.sources_changed.connect(lambda sources: None)
    client.ready.connect(lambda info: print("运行时:", info.get("runnerVersion"), info.get("protocol")))
    client.failure.connect(lambda message: fail(f"客户端失败: {message}"))
    engine.state_changed.connect(on_state)
    engine.position_changed.connect(on_position)
    engine.error_occurred.connect(lambda message, fatal: fail(f"播放错误: {message}"))

    def begin() -> None:
        print("启动音源运行时…")
        client.ensure_started()
        QTimer.singleShot(1800, lambda: client.search(SOURCE, KEYWORD, 1, on_search, timeout=30000))

    QTimer.singleShot(200, begin)
    QTimer.singleShot(45000, lambda: fail("超时"))

    app.exec()
    engine.shutdown()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
