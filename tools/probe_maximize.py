import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/probe_max/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp

app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
w = hush.window

def report(tag):
    scr = w.screen().availableGeometry()
    print(f"{tag}: maximized={w.isMaximized()} state={w.windowState().value} geo={w.geometry().getRect()} avail={scr.getRect()} dpr={w.devicePixelRatioF()}")

def step1():
    report("initial")
    w.toggle_maximize()
def step2():
    report("after toggle_maximize")
    w.toggle_maximize()
def step3():
    report("after restore")
    import ctypes
    hwnd = int(w.winId())
    ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
def step4():
    report("after ShowWindow(MAXIMIZE)")
    app.quit()

for i, fn in enumerate([step1, step2, step3, step4]):
    QTimer.singleShot(1200 + i * 900, fn)
app.exec()
hush.shutdown()

