import os, sys, shutil
sys.path.insert(0, ".")
base = os.path.abspath("artifacts/qa/r92d"); data = os.path.join(base, "data")
os.makedirs(base, exist_ok=True)
shutil.rmtree(data, ignore_errors=True); shutil.copytree("artifacts/qa/r90/data", data)
os.environ["HUSHPLAYER_DATA_DIR"] = data
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QStyleFactory, QAbstractItemView
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1560, 980); win.show(); app.processEvents()
def runs(img, y):
    out=[]; cur=None
    for x in range(img.width()):
        c=img.pixelColor(x,y)
        hit=abs(c.red()-76)<25 and abs(c.green()-194)<25 and abs(c.blue()-255)<25
        if hit:
            if cur is None: cur=x
        elif cur is not None: out.append((cur,x-1)); cur=None
    return out
def view(): return ctx().window.stack.currentWidget().list.table
def yof(v): return v.viewport().mapTo(ctx().window, v.viewport().rect().topLeft()).y() + v.rowViewportPosition(1) + v.rowHeight(1)//2
def check(label):
    v = view(); print(label, runs(win.grab().toImage(), yof(v)), flush=True)
def go():
    win.navigate("songs"); app.processEvents()
    v = view(); v.selectRow(1); v._hover_row = 1; v.viewport().update(); app.processEvents()
    QTimer.singleShot(200, lambda: (check("A"), step2()))
def step2():
    v = view(); v.setStyle(QStyleFactory.create("Fusion")); v.viewport().update(); app.processEvents()
    QTimer.singleShot(200, lambda: (check("B style=Fusion"), step3()))
def step3():
    v = view(); v.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems); v.viewport().update(); app.processEvents()
    QTimer.singleShot(200, lambda: (check("C SelectItems"), step4()))
def step4():
    v = view(); v.setStyleSheet(""); v.viewport().update(); app.processEvents()
    QTimer.singleShot(200, lambda: (check("D no local qss"), app.quit()))
QTimer.singleShot(600, go)
app.exec()
