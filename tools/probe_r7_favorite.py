import os, sys, time, traceback
sys.path.insert(0, ".")
import shutil
_data = os.path.abspath("artifacts/qa/r7/data")
shutil.rmtree(_data, ignore_errors=True)
os.environ["HUSHPLAYER_DATA_DIR"] = _data
os.environ["HUSH_CONSOLE"] = "0"
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

errors = []
sys.excepthook = lambda *a: errors.append("".join(traceback.format_exception(*a)))

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = hush.window
lib = hush.library

files = [str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
lib.import_files(files)

def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)

def pump_until(pred, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred(): return True
        app.processEvents(); time.sleep(0.02)
    return False

def step1():
    track = lib.search_local("夜航", limit=1)[0]
    ctx().player.play_tracks([track], 0, context="qa")
    pump_until(lambda: ctx().player.state in ("playing", "paused"), 8)
    print("state", ctx().player.state, flush=True)
    win.navigate("favorites")
    pump(0.4)
    page = win._pages["favorites"]
    lib.set_favorite(track, True)
    pump(0.6)
    page._sync_current()
    page.list.ensure_current_visible()
    print("favorites rows", page.list.table.model().rowCount(), "errors", len(errors), flush=True)
    win.grab().save("artifacts/qa/r7/favorites_playing.png")
    QTimer.singleShot(200, step2)

def step2():
    if errors:
        print("EXCEPTIONS:\n" + "\n".join(errors), flush=True)
    else:
        print("RESULT PASS", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(900, step1)
app.exec()
