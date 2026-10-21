import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data2")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1016, 807); win.show(); app.processEvents()

def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings"); page._show_section(0); app.processEvents()
    win.resize(880, 580); app.processEvents()
    QTimer.singleShot(700, inspect)

def inspect():
    page = win._page("settings")
    print("PAGE", page.width(), page.minimumSizeHint().width(), flush=True)
    for area in page.findChildren(QScrollArea):
        bar = area.horizontalScrollBar()
        print("SCROLL", area.__class__.__name__, "w", area.width(), "vp", area.viewport().width(),
              "max", bar.maximum(), "policy", area.horizontalScrollBarPolicy(), flush=True)
        host = area.widget()
        if host is not None:
            print("   host min", host.minimumSizeHint().width(), "w", host.width(), flush=True)
            for child in host.findChildren(QWidget):
                if child.parent() is host and child.minimumSizeHint().width() > area.viewport().width():
                    print("   wide child", child.__class__.__name__, child.minimumSizeHint().width(), flush=True)
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(700, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
