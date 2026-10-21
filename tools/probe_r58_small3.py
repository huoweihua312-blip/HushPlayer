import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data3")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1016, 807); win.show(); app.processEvents()

def report(tag):
    page = win._page("settings")
    bars = []
    for area in page.findChildren(QScrollArea):
        bar = area.horizontalScrollBar()
        if bar.maximum() > 0:
            bars.append((area.viewport().width(), bar.maximum()))
    print(tag, "nav", page._nav.width(), "header_h", page.header.height(), "hscroll", bars, flush=True)

def shot(tag):
    win.grab().save(f"artifacts/qa/r58/{tag}.png"); report(tag)

def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings"); page._show_section(0); app.processEvents()
    QTimer.singleShot(500, lambda: (shot("small_1016"), step2()))

def step2():
    win.resize(880, 580); app.processEvents()
    QTimer.singleShot(600, lambda: (shot("small_880"), done()))

def done():
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(600, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
