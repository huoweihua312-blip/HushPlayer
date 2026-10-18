"""真实在线链路验证：搜索 → 播放（本地代理 + 缓存）→ 下载落盘。

在临时数据目录中运行，不触碰真实用户数据。
用法：.venv\\Scripts\\python.exe tools\\probe_online_e2e.py [关键词]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = Path(tempfile.mkdtemp(prefix="hush-e2e-"))
os.environ["HUSHPLAYER_DATA_DIR"] = str(DATA)
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.core import paths  # noqa: E402
from hushplayer.core.settings import settings  # noqa: E402
from hushplayer.audio.controller import PlayerController  # noqa: E402
from hushplayer.online import models  # noqa: E402
from hushplayer.online.client import OnlineSourceClient  # noqa: E402
from hushplayer.online.proxy import AudioProxy  # noqa: E402
from hushplayer.services.downloads import DownloadService, STATE_DONE, STATE_FAILED  # noqa: E402

settings().set("downloads.dir", str(DATA / "downloads"))
KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "晴天 周杰伦"


def pump(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def wait_for(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.03)
    return False


def main() -> int:
    app = QApplication(sys.argv[:1])
    client = OnlineSourceClient()
    proxy = AudioProxy()
    controller = PlayerController(client=client, proxy=proxy)
    downloads = DownloadService(client)

    client.log_line.connect(lambda line: print("[runner]", line.rstrip()))
    if not client.ensure_started():
        print("FAIL 无法启动在线音源运行时：", client.last_error)
        return 2
    if not wait_for(lambda: bool(client.sources), 20):
        print("FAIL 音源列表超时")
        return 2

    sources = models.build_sources(client.sources)
    wanted = os.environ.get("HUSH_PROBE_PLATFORM", "网易")
    netease = next((s for s in sources if wanted in s.platform or wanted in s.name), None)
    if netease is None:
        print(f"FAIL 没有匹配「{wanted}」的音源")
        return 2
    print(f"音源：{netease.name} ({netease.platform}) 可播放={netease.can_play} 可下载={netease.can_download}")

    found: dict = {}

    def on_search(response: dict) -> None:
        found.update(response)

    client.search(netease.id, KEYWORD, 1, on_search, timeout=30_000)
    if not wait_for(lambda: bool(found), 35):
        print("FAIL 搜索超时")
        return 2
    if not found.get("ok"):
        print("FAIL 搜索失败：", found.get("error"))
        return 2
    tracks = models.tracks_from_items(found.get("data") or [], source=netease)
    print(f"搜索「{KEYWORD}」得到 {len(tracks)} 首，首条：{tracks[0].title} - {tracks[0].artist}")
    track = next((item for item in tracks if item.duration_ms), tracks[0])

    positions: list[int] = []
    controller.position_changed.connect(positions.append)
    errors: list[str] = []
    controller.error_message.connect(errors.append)
    controller.play_tracks(tracks[:5], tracks.index(track), context="e2e 测试")
    ok = wait_for(lambda: bool(positions) and max(positions) > 2000, 45)
    print(f"播放状态={controller.state} 位置={max(positions) if positions else 0}ms 错误={errors}")
    if not ok:
        print("FAIL 播放没有前进")
        return 2
    cache_files = [p for p in paths.audio_cache_dir().glob("*") if p.suffix != ".json"]
    sizes = [p.stat().st_size for p in cache_files if p.is_file()]
    print(f"缓存文件 {len(cache_files)} 个，最大 {max(sizes) if sizes else 0} 字节")
    if not sizes or max(sizes) < 100_000:
        print("FAIL 缓存未写入")
        return 2

    done: list = []
    failed: list[str] = []
    downloads.job_finished.connect(done.append)
    downloads.job_updated.connect(lambda job: failed.append(job.error) if job.state == STATE_FAILED else None)
    job = downloads.download([track])[0]
    finished = wait_for(lambda: job.state in {STATE_DONE, STATE_FAILED}, 90)
    print(f"下载状态={job.state} 大小={job.downloaded} 路径={job.path} 错误={job.error}")
    if not finished or job.state != STATE_DONE:
        print("FAIL 下载失败")
        return 2
    saved = Path(job.path)
    if not saved.is_file() or saved.stat().st_size < 100_000:
        print("FAIL 下载文件异常")
        return 2
    print(f"下载完成：{saved.name} ({saved.stat().st_size} 字节)")

    controller.shutdown()
    downloads.shutdown()
    client.stop()
    proxy.shutdown()
    app.processEvents()
    print("OK 在线播放与下载链路验证通过")
    print("临时目录：", DATA)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
