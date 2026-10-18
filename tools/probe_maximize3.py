import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/probe_max/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
w = hush.window; bar = w.titlebar
orig = w.toggle_maximize
def traced():
    print("toggle_maximize called; isMaximized=", w.isMaximized(), "geo=", w.geometry().getRect(), flush=True)
    orig()
    print("  -> isMaximized=", w.isMaximized(), "geo=", w.geometry().getRect(), flush=True)
w.toggle_maximize = traced
btn = bar.maximize_button
btn.clicked.connect(lambda: print("clicked signal", flush=True))

def s1():
    print("initial", w.isMaximized(), w.geometry().getRect(), flush=True)
    print("bar geom", bar.geometry().getRect(), "btn", btn.geometry().getRect(), "parent", btn.parent().__class__.__name__, flush=True)
    QTest.mouseClick(btn, Qt.LeftButton, Qt.NoModifier, btn.rect().center())
def s2():
    print("after click1", w.isMaximized(), w.geometry().getRect(), flush=True)
    w.toggle_maximize()
def s3():
    print("after direct toggle", w.isMaximized(), w.geometry().getRect(), flush=True)
    app.quit()
for i, fn in enumerate([s1, s2, s3]):
    QTimer.singleShot(900 + i*800, fn)
app.exec(); hush.shutdown()
