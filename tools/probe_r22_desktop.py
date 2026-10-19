import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r22/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.desktop_lyrics import ensure_desktop_lyrics

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
settings = ctx().settings

def run():
    settings.set("desktop_lyrics.x", 320)
    settings.set("desktop_lyrics.y", 210)
    settings.set("desktop_lyrics.font_size", 44)
    window = ensure_desktop_lyrics()
    app.processEvents()
    restored = (window.x(), window.y(), window._font_size)
    print("restored", restored, flush=True)
    window.move(410, 260)
    window._save_position()
    print("saved", settings.get("desktop_lyrics.x"), settings.get("desktop_lyrics.y"), flush=True)
    ok = restored == (320, 210, 44) and settings.get("desktop_lyrics.x") == 410 and settings.get("desktop_lyrics.y") == 260
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    os._exit(0)

QTimer.singleShot(800, run)
app.exec()
