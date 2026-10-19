import os, sys, faulthandler
faulthandler.dump_traceback_later(15, exit=True)
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r41/data9")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
print("imports ok", flush=True)
app = QApplication(sys.argv); hush = HushApp(app); hush.start()
print("app ok", flush=True)
from hushplayer.ui.mini_player import MiniPlayer
mini = MiniPlayer()
print("constructed", mini.size(), flush=True)
mini.show(); print("shown", flush=True)
app.processEvents(); print("events ok", flush=True)
mini.close(); hush.shutdown(); print("done", flush=True)
