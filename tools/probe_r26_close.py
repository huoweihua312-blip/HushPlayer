import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r26/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window

def open_dialog():
    QTimer.singleShot(500, snap)
    win._ask_close_action()

def snap():
    dialog = app.activeModalWidget()
    if dialog is None:
        print("no dialog", flush=True); os._exit(3)
    dialog.grab().save("artifacts/qa/r26/close_dialog.png")
    print("dialog", dialog.windowTitle(), dialog.size().width(), dialog.size().height(), flush=True)
    dialog.reject()

QTimer.singleShot(700, open_dialog)
QTimer.singleShot(2500, lambda: (print("RESULT PASS", flush=True), os._exit(0)))
app.exec()
