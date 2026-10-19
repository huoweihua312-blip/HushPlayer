import os, sys, faulthandler
sys.path.insert(0, ".")
faulthandler.enable()
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/settings_probe/data2")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SECTIONS

print("creating app", flush=True)
app = QApplication(sys.argv)
app.setStyle("Fusion")
print("building hush", flush=True)
hush = HushApp(app)
hush.start()
win = ctx().window
print("navigate settings", flush=True)
win.navigate("settings")
page = win._pages["settings"]
keys = [s[0] for s in SECTIONS]

def step(key):
    print("show", key, flush=True)
    page._show_section(keys.index(key))
    for _ in range(30):
        app.processEvents()
    print("grab", key, flush=True)
    win.grab().save(f"artifacts/qa/settings_{key}.png")
    print("saved", key, flush=True)

def run():
    for key in ("appearance", "playback", "online", "cache", "about", "general"):
        step(key)
    print("done", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(1200, run)
app.exec()
