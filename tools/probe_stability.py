import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/stability/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.services.library import LibraryQuery

def luma(pix):
    img = pix.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = img.width(), img.height()
    total = n = 0
    for y in range(0, h, max(1, h // 90)):
        for x in range(0, w, max(1, w // 160)):
            total += img.pixelColor(x, y).red(); n += 1
    return total / max(1, n)

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = hush.window
ctx().player.play_tracks(hush.library.tracks_page(LibraryQuery(limit=3)), 0, context="stability")
rows = []

def step():
    win.show(); app.processEvents()
    base = luma(win.grab())
    for i in range(5):
        win.open_immersive(); app.processEvents()
        imm = ctx().immersive
        first = luma(imm.grab())
        for mode in ("lyrics", "cover"):
            imm.set_mode(mode, animate=False); app.processEvents()
            luma(imm.grab())
        ctx().immersive.close_immersive(); app.processEvents()
        after = luma(win.grab())
        rows.append((i, round(base,1), round(first,1), round(after,1), abs(first-base) < 40 and abs(after-base) < 40))
    bar = win.titlebar
    QTest.mouseClick(bar.maximize_button, Qt.MouseButton.LeftButton); app.processEvents()
    m1, g1 = win.isMaximized(), (win.width(), win.height())
    QTest.mouseClick(bar.maximize_button, Qt.MouseButton.LeftButton); app.processEvents()
    m2, g2 = win.isMaximized(), (win.width(), win.height())
    print("immersive loop:", rows, flush=True)
    print("maximize:", m1, g1, "restore:", m2, g2, flush=True)
    win.close(); app.quit()

QTimer.singleShot(1500, step)
QTimer.singleShot(45000, app.quit)
app.exec()
hush.shutdown()
