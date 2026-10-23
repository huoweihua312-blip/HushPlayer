import os, sys, faulthandler
sys.path.insert(0, ".")
faulthandler.enable()
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r81/data")
os.environ["HUSH_CONSOLE"] = "0"
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
os.environ["HUSHPLAYER_MUTEX_SUFFIX"] = "r81"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SECTIONS

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app)
hush.start()
win = ctx().window
win.resize(1280, 820)
win.navigate("settings")
page = win._pages["settings"]
keys = [s[0] for s in SECTIONS]

def pump(n=40):
    for _ in range(n):
        app.processEvents()

def shot(name):
    pump()
    win.grab().save(f"artifacts/qa/r81/{name}.png")
    print("saved", name, flush=True)

def run():
    page._show_section(keys.index("appearance"))
    shot("settings_dark")
    settings = ctx().settings
    settings.set("appearance.theme_animation_mode", "off")
    settings.set("appearance.theme", "pure")
    pump(60)
    shot("settings_pure")
    win.navigate("home")
    shot("home_pure")
    win.navigate("songs")
    shot("songs_pure")
    print("done", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(1500, run)
QTimer.singleShot(30000, lambda: (hush.shutdown(), app.quit()))
app.exec()
