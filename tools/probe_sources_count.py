import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/settings_probe/data5")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.online import models

app = QApplication(sys.argv); app.setStyle("Fusion")
hush = HushApp(app); hush.start()
client = ctx().client
client.sources_changed.connect(lambda s: print("sources_changed:", len(s), flush=True))

def probe(tag):
    raw = client.sources
    print(tag, "running", client.running, "raw", len(raw), "built", len(models.build_sources(raw)), "err", client.last_error, flush=True)

QTimer.singleShot(1000, lambda: probe("t1"))
QTimer.singleShot(3000, lambda: probe("t3"))
QTimer.singleShot(3500, lambda: (hush.shutdown(), app.quit()))
app.exec()
