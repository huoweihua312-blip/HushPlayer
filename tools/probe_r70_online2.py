import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r70/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1280, 900); win.show(); app.processEvents()
def go():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings"); page._show_section(6); app.processEvents()
    for area in page.findChildren(QScrollArea):
        bar = area.verticalScrollBar()
        if bar.maximum() > 0:
            bar.setValue(bar.maximum())
    app.processEvents()
    QTimer.singleShot(600, shot)
def shot():
    win.grab().save("artifacts/qa/r70/settings_online2.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(700, go)
QTimer.singleShot(10000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
