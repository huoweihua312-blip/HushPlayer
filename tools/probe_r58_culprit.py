import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data4")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(880, 580); win.show(); app.processEvents()

def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings")
    for index, name in ((1, "appearance"), (2, "playback"), (6, "online"), (8, "about")):
        page._show_section(index); app.processEvents()
        for area in page.findChildren(QScrollArea):
            if area.horizontalScrollBar().maximum() <= 0:
                continue
            host = area.widget()
            print(name, "vp", area.viewport().width(), "hostmin", host.minimumSizeHint().width(), flush=True)
            widest = sorted(host.findChildren(QWidget), key=lambda w: w.minimumSizeHint().width(), reverse=True)[:4]
            for w in widest:
                print("   ", w.__class__.__name__, w.minimumSizeHint().width(), w.width(), flush=True)
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(700, go)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
