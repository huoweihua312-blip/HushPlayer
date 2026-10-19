import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data3")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
win = ctx().window; win.show(); app.processEvents()
def go():
    ctx().player.play_tracks(ctx().library.tracks(limit=3), 0)
    win.toggle_mini_player()
    QTimer.singleShot(700, shot)
def shot():
    mini = win._mini
    mini.grab().save("artifacts/qa/r41/mini_player.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(600, go); app.exec(); hush.shutdown()
