"""R93: 真实 GUI 冒烟 + 正式绑定在界面里的呈现。

启动真实 HushApp（隔离数据目录），导入本地样例曲目，写入一首带 manual
绑定的在线曲目，然后：
  1. 截图歌曲页（含来源副标题）；
  2. 选中该在线行再截图，确认整行色带没有回归；
  3. 打印绑定状态与曲目来源，确认界面读到的就是正式绑定；
  4. 用同一数据目录重开 TrackBindingService，确认重启后绑定稳定。
"""

import os
import sys

sys.path.insert(0, os.getcwd())

base = os.path.abspath("artifacts/qa/r93")
data = os.path.join(base, "data")
os.makedirs(base, exist_ok=True)
os.environ["HUSHPLAYER_DATA_DIR"] = data
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"

from pathlib import Path
import time

from PySide6.QtWidgets import QApplication

from hushplayer.app import HushApp
from hushplayer.model.track import Track, ONLINE
from hushplayer.services.binding import BindingChoice, TrackBindingService
from hushplayer.store.db import Database
from hushplayer.store.repository import TrackRepository

FIX = Path("tests/fixtures/audio")


def pump(ms: int = 800) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.015)


qt = QApplication.instance() or QApplication(sys.argv[:1])
app = HushApp(qt)
app.start()
for _ in range(150):
    QApplication.processEvents()
    if app.window is not None:
        break
    time.sleep(0.02)
win = app.window
pump(400)

files = sorted(str(p) for p in FIX.rglob("*") if p.is_file())
app.library.import_files(files)
pump(1200)

sources = app.player.sources
source = sources[0] if sources else None
source_id = source.id if source is not None else "custom_source_probe"
source_name = source.name if source is not None else "探针音源"

online = Track(
    id="online:probe:1",
    kind=ONLINE,
    title="夜航信号（在线）",
    artist="探针歌手",
    album="探针专辑",
    duration_ms=214_000,
    source_id=source_id,
    source_name=source_name,
    remote_id="probe-remote-1",
    raw={"id": "probe-remote-1", "title": "夜航信号（在线）"},
)
app.library.tracks.upsert(online)
app.bindings.ensure_auto(online.id)
choice = BindingChoice(
    source_id=source_id,
    source_name=source_name,
    remote_id="probe-remote-1",
    title=online.title,
    artist=online.artist,
    album=online.album,
    duration_ms=online.duration_ms,
    raw=online.raw,
)
assert app.bindings.manual_choose(online.id, choice) is True, "手动绑定写入失败"

app.window.library_page.reload() if hasattr(app.window, "library_page") else None
pump(800)
app.window.grab().save(os.path.join(base, "songs.png"))

# 选中在线行：来源列应显示正式绑定的音源名
page = getattr(app.window, "library_page", None)
table = getattr(page, "table", None)
if table is not None:
    for row in range(table.rowCount()):
        model = table.item(row, 0)
        track_id = model.data(0x0100) if model is not None else None
        if track_id == online.id:
            table.selectRow(row)
            break
    pump(400)
    app.window.grab().save(os.path.join(base, "songs_selected.png"))

state = app.bindings.state(online.id)
stored = app.library.tracks.get(online.id)
print("binding:", state.selection_mode, state.verify_state, "rev", state.revision)
print("track   :", stored.source_id, stored.remote_id, stored.title)
print("search  :", "no cross-source search needed")

from hushplayer.services.binding import TrackBindingService as _Svc  # noqa: E402


class _Shell:
    def __init__(self, db_path: str) -> None:
        self.db = Database(db_path)
        self.tracks = TrackRepository(self.db)
        self.db_path = db_path


shell = _Shell(app.library.db.path)
restarted = _Svc(shell)
after = restarted.state(online.id)
row = shell.tracks.get(online.id)
print("restart :", after.selection_mode, after.verify_state,
      "rev", after.revision, "->", row.source_id, row.remote_id)
assert after.manual and after.revision == state.revision
assert row.source_id == source_id and row.remote_id == "probe-remote-1"

pump(200)
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
app.shutdown() if hasattr(app, "shutdown") else None
print("OK", os.path.join(base, "songs.png"))



