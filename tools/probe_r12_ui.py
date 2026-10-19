import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r12/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SECTIONS

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("settings", "online")
page = win._pages["settings"]
keys = [s[0] for s in SECTIONS]

def pump(seconds):
    loop = QEventLoop(); QTimer.singleShot(int(seconds * 1000), loop.quit); loop.exec()

def shoot():
    page._show_section(keys.index("online"))
    page._fill_sources()
    pump(1.2)
    win.grab().save("artifacts/qa/r12/settings_subscription_row.png")
    print("rows", [s.name for s in ctx().client.sources] if hasattr(ctx().client.sources[0], "name") else len(ctx().client.sources), flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(600, shoot)
app.exec()
