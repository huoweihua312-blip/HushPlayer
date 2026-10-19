import os, sys, shutil, pathlib
sys.path.insert(0, ".")
import tempfile
base = pathlib.Path(tempfile.mkdtemp(prefix="hush-r6-", dir="artifacts/qa"))
(base / "music").mkdir(parents=True)
shutil.copytree("tests/fixtures/audio", base / "music", dirs_exist_ok=True)
os.environ["HUSHPLAYER_DATA_DIR"] = str((base / "data").resolve())
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
lib = hush.library
files = [str(p) for p in (base / "music").rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg", ".m4a"}]
res = lib.import_files(files)
print("imported", res.added, "updated", res.updated, flush=True)
from hushplayer.services.library import LibraryQuery
tracks = [t for t in lib.tracks_page(LibraryQuery(limit=200)) if t.title == "夜航信号"]
assert tracks, "fixture missing"
track = tracks[0]
media_dir = pathlib.Path(track.path).parent
lrc = media_dir / "01 - 夜航信号.lrc"
lrc.write_text("[00:00.00]夜航信号\n[00:02.00]第一句测试歌词\n[00:04.00]穿过无人的跑道\n[00:06.00]城市在身后退潮\n[00:08.00]我把频率调到最高\n[00:10.00]听见海的心跳\n", encoding="utf-8")

win = hush.window
player = hush.player
player.play_tracks([track], 0, context="qa")
player.seek(4500)

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

def run():
    try:
        _run()
    except Exception:
        import traceback; traceback.print_exc()
    finally:
        hush.shutdown(); app.quit()


def _run():
    win.navigate("lyrics")
    page = win._pages["lyrics"]
    pump(900)
    view = page.view
    view.set_position(20000)
    view._scroll_to_index(view.body.active_index, animate=False)  # noqa: SLF001
    pump(200)
    bar = view.scroll.verticalScrollBar()
    before = bar.value()
    print("before", before, "active", page.view.body.active_index, flush=True)
    samples = []
    page.shift_offset(300)
    samples.append(bar.value())
    for _ in range(40):
        pump(20)
        samples.append(bar.value())
    print('first10', samples[:10], flush=True)
    print("after+300", bar.value(), "active", page.view.body.active_index, "min sample", min(samples), flush=True)
    samples2 = []
    page.shift_offset(-300)
    for _ in range(40):
        pump(20)
        samples2.append(bar.value())
    print("after-reset", bar.value(), "active", page.view.body.active_index, "min sample", min(samples2), flush=True)
    ok = before > 0 and min(samples) >= before - 40 and min(samples2) >= before - 40
    page.grab().save("artifacts/qa/r6_lyrics_offset.png")
    print("PASS" if ok else "FAIL", flush=True)

QTimer.singleShot(800, run)
app.exec()
