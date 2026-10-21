import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data2")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(880, 580); win.show(); app.processEvents()

def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings"); page._show_section(0); app.processEvents()
    QTimer.singleShot(600, inspect)

def inspect():
    page = win._page("settings")
    for area in page.findChildren(QScrollArea):
        bar = area.horizontalScrollBar()
        if not bar.isVisible():
            continue
        print("SCROLL", area.width(), "viewport", area.viewport().width(), "max", bar.maximum(), flush=True)
        host = area.widget()
        print(" host min", host.minimumSizeHint().width(), "hint", host.sizeHint().width(), flush=True)
        for child in host.findChildren(type(host), options=__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.FindDirectChildrenOnly):
            print("  child", child.__class__.__name__, child.width(), child.minimumSizeHint().width(), child.sizeHint().width(), flush=True)
        # walk deepest offending widgets
        worst = max(host.findChildren(__import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget),
                    key=lambda w: w.minimumSizeHint().width())
        print(" worst", worst.__class__.__name__, worst.minimumSizeHint().width(), flush=True)
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(600, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
