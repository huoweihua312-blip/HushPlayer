import os, sys
sys.path.insert(0, ".")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r58/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.15"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window
win.resize(880, 580); win.show(); app.processEvents()

def shoot():
    win.navigate("settings"); app.processEvents()
    print("window", win.size().toTuple(), "min", win.minimumSize().toTuple())
    print("mask_empty", win.mask().isEmpty(), "mask_rects", len(win.mask()))
    print("handles", len(getattr(win, "_edge_handles", [])), [h.isVisible() for h in getattr(win, "_edge_handles", [])][:3])
    win.grab().save("artifacts/qa/r58/settings_small.png")
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(800, shoot)
QTimer.singleShot(9000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
