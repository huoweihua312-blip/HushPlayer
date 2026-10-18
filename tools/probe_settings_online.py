import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/settings_probe/data4")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SECTIONS

app = QApplication(sys.argv); app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("settings")
page = win._pages["settings"]
keys = [s[0] for s in SECTIONS]

def shoot():
    page._show_section(keys.index("online"))
    for _ in range(40):
        app.processEvents()
    win.grab().save("artifacts/qa/settings_online.png")
    print("saved online", flush=True)
    QTimer.singleShot(2500, shoot2)

def shoot2():
    win.grab().save("artifacts/qa/settings_online_loaded.png")
    print("saved online loaded", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(800, shoot)
app.exec()
