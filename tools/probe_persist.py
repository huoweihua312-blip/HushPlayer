import os, sys, json
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/probe_persist/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp

phase = sys.argv[1]
app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
w = hush.window

def report(tag):
    print(f"{tag}: maximized={w.isMaximized()} geo={w.geometry().getRect()} normal={w.normal_geometry().getRect()}", flush=True)

def s1():
    report("start")
    if phase == "maximize":
        QTest.mouseClick(w.titlebar.maximize_button, Qt.LeftButton, Qt.NoModifier, w.titlebar.maximize_button.rect().center())
        QTimer.singleShot(600, s2)
    else:
        QTest.mouseClick(w.titlebar.maximize_button, Qt.LeftButton, Qt.NoModifier, w.titlebar.maximize_button.rect().center())
        QTimer.singleShot(600, s2)

def s2():
    report("after click")
    if phase == "maximize":
        w.close()
    else:
        app.quit()

QTimer.singleShot(900, s1)
app.exec()
hush.shutdown()
print("saved:", json.dumps(json.load(open(os.path.join(os.environ["HUSHPLAYER_DATA_DIR"], "settings.json"), encoding="utf-8"))["general"]["window"], ensure_ascii=False), flush=True)
