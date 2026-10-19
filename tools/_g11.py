import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r22/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
app.setStyle("Fusion")
QTimer.singleShot(20000, lambda: (print("WATCHDOG", flush=True), os._exit(3)))
hush = HushApp(app)
print("built", flush=True)
hush.start()
print("started", flush=True)
win = ctx().window

def run():
    from pathlib import Path
    print("step import", flush=True)
    files = [str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    ctx().library.import_files(files)
    print("step navigate", flush=True)
    win.navigate("songs")
    print("step immersive", flush=True)
    win.open_immersive()
    print("step opened", flush=True)
    imm = ctx().immersive
    imm.set_mode("lyrics", animate=False)
    print("step mode", flush=True)
    imm.show_quick_settings()
    print("step menu", flush=True)
    os._exit(0)

QTimer.singleShot(600, run)
app.exec()
