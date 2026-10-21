import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r59/data")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.ui.widgets.frameless import FramelessWindow, EdgeHandle

app = QApplication(sys.argv)
apply_theme_to_app(app)
win = FramelessWindow()
win.setStyleSheet("#HushWindowRoot{background:#202024;}")
win.resize(900, 620)
win.show()

orig = EdgeHandle.mousePressEvent
def logged(self, event):
    print("HANDLE PRESS", self.edge_name, event.button(), flush=True)
    return orig(self, event)
EdgeHandle.mousePressEvent = logged

def start_resize(self, edges):
    print("startSystemResize called", edges, flush=True)
    return orig_start(self, edges)
from PySide6.QtGui import QWindow
orig_start = QWindow.startSystemResize
QWindow.startSystemResize = start_resize

def report():
    print("GEOM", win.geometry().getRect(), flush=True)

QTimer.singleShot(1500, report)
QTimer.singleShot(1501, lambda: print("PID", os.getpid(), flush=True))
QTimer.singleShot(9000, app.quit)
app.exec()
