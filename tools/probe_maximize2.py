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
w = hush.window
bar = w.titlebar

def report(tag):
    print(f"{tag}: maximized={w.isMaximized()} geo={w.geometry().getRect()} avail={w.screen().availableGeometry().getRect()}")

def s1():
    report("initial")
    btn = bar.maximize_button
    print("btn visible", btn.isVisible(), btn.geometry().getRect(), "enabled", btn.isEnabled())
    QTest.mouseClick(btn, Qt.LeftButton, Qt.NoModifier, btn.rect().center())
def s2():
    report("after click maximize button")
    QTest.mouseClick(bar.maximize_button, Qt.LeftButton, Qt.NoModifier, bar.maximize_button.rect().center())
def s3():
    report("after click again")
    QTest.mouseDClick(bar, Qt.LeftButton, Qt.NoModifier, QPoint(bar.width()//2, bar.height()//2))
def s4():
    report("after dblclick titlebar")
    app.quit()

for i, fn in enumerate([s1, s2, s3, s4]):
    QTimer.singleShot(900 + i * 700, fn)
app.exec()
hush.shutdown()
