"""R94: 真实 GUI 验收「恢复会话不自动播放」。

分两个进程执行（模拟真正的重启）：

    python tools/probe_r94_session.py save     # 播放一首本地曲目 -> 保存进度 -> 退出
    python tools/probe_r94_session.py restore  # 重新启动 -> 确认恢复但不自动播放

两次都使用同一个隔离数据目录 ``artifacts/qa/r94/data``。
"""

import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

BASE = os.path.abspath("artifacts/qa/r94")
DATA = os.path.join(BASE, "data")
os.makedirs(BASE, exist_ok=True)
os.environ["HUSHPLAYER_DATA_DIR"] = DATA
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"

from pathlib import Path  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402

FIX = Path("tests/fixtures/audio")
EXPECTED = Path(BASE) / "expected.json"
POSITION = 4200


def pump(ms: int = 800) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.015)


def boot() -> HushApp:
    qt = QApplication.instance() or QApplication(sys.argv[:1])
    app = HushApp(qt)
    app.start()
    for _ in range(200):
        QApplication.processEvents()
        if app.window is not None:
            break
        time.sleep(0.02)
    pump(600)
    return app


def phase_save() -> None:
    app = boot()
    files = sorted(str(p) for p in FIX.rglob("*") if p.is_file())
    app.library.import_files(files)
    pump(1200)

    tracks = app.library.tracks.list(limit=5)
    assert tracks, "夹具曲目导入失败"
    target = tracks[0]
    app.player.play_tracks([t for t in tracks if t.is_local], 0)
    pump(1200)

    # 模拟用户听到 4.2 秒：直接推进位置并让 keeper 落盘（离线环境没有真实音频输出）。
    app.player._position = POSITION  # noqa: SLF001 - 探针直接用测试缝
    app.keeper.save_now()
    app.keeper.flush()
    pump(300)

    payload = json.loads(Path(DATA, "play_queue.json").read_text(encoding="utf-8"))
    assert payload["tracks"], "会话文件没有曲目"
    assert int(payload["position_ms"]) == POSITION, payload["position_ms"]

    EXPECTED.write_text(
        json.dumps(
            {
                "current_id": app.player.current_track.id if app.player.current_track else "",
                "position": POSITION,
                "count": app.player.queue.count,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app.window.grab().save(os.path.join(BASE, "playing.png"))
    print("saved:", payload["current_id"], payload["position_ms"], "queue", len(payload["tracks"]))
    app.shutdown()


def phase_restore() -> None:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    app = boot()

    assert os.path.exists(Path(DATA, "play_queue.json"))
    print("queue  :", app.player.queue.count, "expected", expected["count"])
    print("current:", (app.player.current_track.id if app.player.current_track else None))
    print("state  :", app.player.state, "position", app.player.position)

    assert app.player.queue.count == expected["count"], "队列没有完整恢复"
    assert app.player.current_track is not None
    assert app.player.current_track.id == expected["current_id"], "恢复的不是原来的歌"
    assert app.player.state == "stopped", "恢复会话时不应自动播放"
    assert app.player.position == expected["position"], "进度没有恢复"

    pump(1500)  # 等封面/列表渲染完再截图
    app.window.grab().save(os.path.join(BASE, "restored.png"))

    # 首次点击播放才真正加载：此时才允许出现 loading/playing。
    app.player.play()
    pump(900)
    print("after play:", app.player.state, app.player.position)
    app.window.grab().save(os.path.join(BASE, "restored_playing.png"))
    print("OK", os.path.join(BASE, "restored.png"))
    app.shutdown()


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "save"
    (phase_save if phase == "save" else phase_restore)()
