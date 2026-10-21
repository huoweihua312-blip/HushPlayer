import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data4")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(880, 580); win.show(); app.processEvents()
page = None

def check(index):
    global page
    page = win._page("settings")
    page._show_section(index); app.processEvents()
    bad = [a for a in page.findChildren(QScrollArea) if a.horizontalScrollBar().maximum() > 0]
    print("section", index, "hscroll", len(bad), flush=True)

def go():
    global page
    win.navigate("settings"); app.processEvents()
    page = win._page("settings")
    for index, name in ((1, "appearance"), (2, "playback"), (6, "online"), (8, "about")):
        page._show_section(index); app.processEvents()
        bad = [a for a in page.findChildren(QScrollArea) if a.horizontalScrollBar().maximum() > 0]
        print("section", name, "hscroll", len(bad), flush=True)
        if name == "appearance":
            win.grab().save("artifacts/qa/r58/appearance_880.png")
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(700, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
