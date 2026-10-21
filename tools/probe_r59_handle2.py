import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r59/data")
from PySide6.QtCore import QTimer
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.ui.widgets.frameless import EdgeHandle, FramelessWindow

app = QApplication(sys.argv)
apply_theme_to_app(app)
win = FramelessWindow(); win.setStyleSheet("#HushWindowRoot{background:#202024;}"); win.resize(900, 620); win.show()

orig = EdgeHandle.mousePressEvent
def logged(self, event):
    print("HANDLE PRESS", self.edge_name, flush=True)
    return orig(self, event)
EdgeHandle.mousePressEvent = logged
orig_start = QWindow.startSystemResize
def start_resize(self, edges):
    print("startSystemResize", edges, flush=True)
    return orig_start(self, edges)
QWindow.startSystemResize = start_resize

def dump():
    for h in win._edge_handles:
        print("handle", h.edge_name, h.geometry().getRect(), h.isVisible(), flush=True)
    print("mask empty", win.mask().isEmpty(), flush=True)
QTimer.singleShot(1200, dump)
QTimer.singleShot(20000, app.quit)
app.exec()
