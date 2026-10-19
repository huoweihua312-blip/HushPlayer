import os, sys, faulthandler
faulthandler.dump_traceback_later(20, exit=True)
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data10")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
items = ctx().library.tracks.list(limit=1)
from hushplayer.ui.mini_player import MiniPlayer
mini = MiniPlayer(); mini._wire_track(items[0]); mini.show(); app.processEvents()
print("ready", flush=True)
pm = mini.grab(); print("grabbed", pm.size(), flush=True)
print("saved", pm.save("artifacts/qa/r41/mini_v4.png"), flush=True)
mini.close(); hush.shutdown(); print("done", flush=True)
