import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r22/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMenu
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

labels: list[str] = []

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = ctx().window

def run():
    from pathlib import Path
    files = [str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    ctx().library.import_files(files)
    win.navigate("songs")
    win.open_immersive()
    imm = ctx().immersive
    imm.set_mode("lyrics", animate=False)
    app.processEvents()
    imm._nudge_lyrics_scale(0.1)
    before = float(ctx().settings.get("lyrics.font_scale", 1.0))
    imm._nudge_lyrics_scale(-0.1)
    after = float(ctx().settings.get("lyrics.font_scale", 1.0))
    imm.show_quick_settings()
    app.processEvents()
    menu = getattr(imm, "_quick_menu", None)
    labels.extend(a.text() for a in menu.actions() if a.text())
    if menu is not None:
        menu.grab().save("artifacts/qa/r22/immersive_menu.png")
        menu.close()
    print("menu labels", labels, flush=True)
    print("scale", round(before, 2), "->", round(after, 2), flush=True)
    imm.close_immersive()
    ok = "放大歌词" in labels and "显示翻译" in labels and abs(after - 1.0) < 0.001
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    os._exit(0)

QTimer.singleShot(800, run)
app.exec()
