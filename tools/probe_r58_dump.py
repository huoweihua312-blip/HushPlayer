import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data2")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(880, 580); win.show(); app.processEvents()

def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings"); page._show_section(0); app.processEvents()
    QTimer.singleShot(600, inspect)

def dump(widget, depth=0):
    if depth > 4:
        return
    minw = widget.minimumSizeHint().width()
    if minw >= 380 or depth <= 2:
        print("  " * depth, widget.__class__.__name__, "w", widget.width(), "min", minw, flush=True)
    for child in widget.findChildren(QWidget, options=__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.FindDirectChildrenOnly):
        dump(child, depth + 1)

def inspect():
    page = win._page("settings")
    for area in page.findChildren(QScrollArea):
        if area.horizontalScrollBar().maximum() > 0:
            print("OVERFLOW SCROLL vp", area.viewport().width(), flush=True)
            dump(area.widget())
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(600, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
