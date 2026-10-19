import os, sys, faulthandler
faulthandler.dump_traceback_later(25, exit=True)
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data5")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.mini_player import MiniPlayer

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
tracks = ctx().library.repo.list(limit=1)
print("tracks", len(tracks), flush=True)
mini = MiniPlayer(); mini._wire_track(tracks[0]); mini.show(); app.processEvents()
def shot():
    mini.grab().save("artifacts/qa/r41/mini_player.png"); print("saved", flush=True); app.quit()
QTimer.singleShot(600, shot); app.exec(); hush.shutdown(); print("done", flush=True)
