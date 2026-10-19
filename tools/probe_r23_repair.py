import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r23/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
import shutil
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("settings", "library")
page = win._pages["settings"]
library = ctx().library

music = Path("artifacts/qa/r23/music")
moved = Path("artifacts/qa/r23/moved")
if music.exists():
    shutil.rmtree(music)
if moved.exists():
    shutil.rmtree(moved)

def run():
    shutil.copytree("tests/fixtures/audio", music)
    files = [str(p) for p in music.rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    library.import_files(files)
    ctx().settings.set("library.folders", [str(music.resolve())])
    shutil.copytree(music, moved)
    shutil.rmtree(music)
    print("missing before", library.missing_count(), flush=True)

    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(moved.resolve()))
    page._repair_missing()
    app.processEvents()
    print("missing after", library.missing_count(), flush=True)
    folders = ctx().settings.get("library.folders", [])
    print("folders", folders[-1].endswith("moved"), flush=True)
    win.grab().save("artifacts/qa/r23/settings_library.png")
    print("RESULT", "PASS" if library.missing_count() == 0 else "FAIL", flush=True)
    os._exit(0)

QTimer.singleShot(800, run)
app.exec()
