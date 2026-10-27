"""新增歌曲置顶探针：确认「我喜欢」与歌单都把最新添加的歌曲放在第一行。

运行：``QT_QPA_PLATFORM=offscreen python tools/probe_r97_order.py``
输出：``artifacts/qa/r97/favorites.png``、``artifacts/qa/r97/playlist.png``
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts" / "qa" / "r97"
DATA = BASE / "data"

if DATA.exists():
    shutil.rmtree(DATA)
DATA.mkdir(parents=True, exist_ok=True)

os.environ["HUSHPLAYER_DATA_DIR"] = str(DATA)
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.services.library import LibraryQuery  # noqa: E402


def pump(ms: int) -> None:
    app = QApplication.instance()
    remaining = ms
    while remaining > 0:
        app.processEvents()
        app.thread().msleep(30)
        remaining -= 30


def main() -> int:
    qt = QApplication.instance() or QApplication([])
    app = HushApp(qt)
    app.start()
    pump(800)

    music = ROOT / "tests" / "fixtures" / "audio"
    files = sorted(
        str(path)
        for path in music.rglob("*")
        if path.suffix.lower() in {".mp3", ".flac", ".ogg", ".wav", ".m4a"}
        and "corrupt" not in path.name
    )
    result = app.library.import_files(files)
    print("imported:", getattr(result, "added", "?"), "of", len(files))
    pump(2000)

    tracks = app.library.tracks_page(LibraryQuery(sort="title", limit=3))
    assert len(tracks) == 3, f"需要至少 3 首歌曲，实际 {len(tracks)}"

    # 先收藏第一首，再收藏第二首：第二首应该在最上面。
    app.library.toggle_favorite(tracks[0])
    pump(300)
    app.library.toggle_favorite(tracks[1])
    pump(600)

    favorites = [track.id for track in app.library.favorites()]
    print("favorites:", favorites[:2], "expect:", [tracks[1].id, tracks[0].id])
    assert favorites[:2] == [tracks[1].id, tracks[0].id], "我喜欢没有把最新收藏置顶"

    app.window.navigate("favorites")
    pump(900)
    app.window.resize(1280, 820)
    pump(600)
    BASE.mkdir(parents=True, exist_ok=True)
    app.window.grab().save(str(BASE / "favorites.png"))

    # 歌单：先加两首，再加第三首，第三首应该跳到第一行。
    playlist_id = app.library.create_playlist("置顶测试")
    app.library.add_to_playlist(playlist_id, tracks[:2])
    pump(300)
    app.library.add_to_playlist(playlist_id, [tracks[2]])
    pump(600)

    order = [track.id for track in app.library.playlist_tracks(playlist_id)]
    print("playlist:", order, "expect first:", tracks[2].id)
    assert order[0] == tracks[2].id, "歌单没有把最新加入的歌曲置顶"

    app.window._refresh_sidebar()
    app.window.navigate("playlist", playlist_id)
    pump(900)
    app.window.resize(1280, 820)
    pump(600)
    app.window.grab().save(str(BASE / "playlist.png"))

    print("saved", BASE / "favorites.png")
    print("saved", BASE / "playlist.png")
    app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
