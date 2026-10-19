import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data8")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.mini_player import MiniPlayer

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
tracks = ctx().library.tracks.list(limit=1)
mini = MiniPlayer(); mini._wire_track(tracks[0]); mini.show(); app.processEvents()
print("visible", mini.isVisible(), "size", mini.size(), flush=True)
def shot():
    pm = QPixmap(mini.size()); pm.fill()
    mini.render(pm)
    print("save", pm.save("artifacts/qa/r41/mini_v3.png"), flush=True)
    app.quit()
QTimer.singleShot(700, shot); app.exec(); hush.shutdown(); print("done", flush=True)
