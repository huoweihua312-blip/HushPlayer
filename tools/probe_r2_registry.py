import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.online.client import OnlineSourceClient
from hushplayer.online import models
app = QApplication(sys.argv)
client = OnlineSourceClient()
loop = QEventLoop()
result = {}
def on_sources(items):
    result["items"] = items; loop.quit()
client.sources_changed.connect(on_sources)
client.ensure_started()
QTimer.singleShot(40000, loop.quit)
loop.exec()
items = result.get("items", [])
print("sources", len(items), flush=True)
for info in models.build_sources(items):
    print(" ", info.id[-14:], info.label, info.enabled, info.can_play, flush=True)
print("home", client._env_home if hasattr(client, "_env_home") else "", flush=True)
client.stop()
