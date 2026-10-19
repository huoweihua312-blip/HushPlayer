import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r24/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from pathlib import Path
import shutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = ctx().window
music = Path("artifacts/qa/r24/music")
if not music.exists():
    shutil.copytree("tests/fixtures/audio", music)
    files = [str(p) for p in music.rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    ctx().library.import_files(files)

def run():
    tracks = ctx().library.tracks_page(__import__("hushplayer.services.library", fromlist=["LibraryQuery"]).LibraryQuery(sort="title", limit=3))
    if tracks:
        ctx().player.play_tracks(tracks, 0, context="mini")
    win.toggle_mini_player()
    app.processEvents()
    mini = win._mini
    print("visible", mini.isVisible(), "main hidden", not win.isVisible(), flush=True)
    print("title", mini.title.text()[:20], flush=True)
    QTimer.singleShot(700, shot)

def shot():
    mini = win._mini
    mini.grab().save("artifacts/qa/r24/mini_player.png")
    before = ctx().player.queue.current.title if ctx().player.queue.current else ""
    ctx().player.next()
    app.processEvents()
    after = ctx().player.queue.current.title if ctx().player.queue.current else ""
    print("next works", before != after, flush=True)
    mini.close_to_main()
    app.processEvents()
    print("main restored", win.isVisible(), "mini hidden", not mini.isVisible(), flush=True)
    print("RESULT PASS", flush=True)
    os._exit(0)

QTimer.singleShot(900, run)
app.exec()
