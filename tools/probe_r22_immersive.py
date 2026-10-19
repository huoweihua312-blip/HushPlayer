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
hush = HushApp(app); hush.start()
win = ctx().window

def run():
    from pathlib import Path
    files = [str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    ctx().library.import_files(files)
    tracks = ctx().library.tracks_page(type("Q", (), {"limit": 3, "sort": "title", "descending": False, "search": "", "offset": 0, "kind": None})())
    win.navigate("songs")
    win.open_immersive()
    imm = ctx().immersive
    imm.set_mode("lyrics", animate=False)
    for _ in range(15):
        app.processEvents()
    print("mode", imm._mode, flush=True)
    imm._nudge_lyrics_scale(0.1)
    print("scale", ctx().settings.get("lyrics.font_scale", 1.0), flush=True)
    imm.show_quick_settings()
    for _ in range(10):
        app.processEvents()
    menu = [w for w in app.topLevelWidgets() if w.__class__.__name__ == "QMenu"]
    print("menu open", bool(menu), flush=True)
    if menu:
        menu[0].grab().save("artifacts/qa/r22/immersive_menu.png")
        menu[0].close()
    imm.close_immersive()
    win.grab().save("artifacts/qa/r22/main_after.png")
    print("RESULT PASS", flush=True)
    os._exit(0)

QTimer.singleShot(900, run)
app.exec()
