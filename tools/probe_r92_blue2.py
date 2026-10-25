import os, sys, shutil
sys.path.insert(0, ".")
base = os.path.abspath("artifacts/qa/r92c"); data = os.path.join(base, "data")
os.makedirs(base, exist_ok=True)
shutil.rmtree(data, ignore_errors=True)
shutil.copytree("artifacts/qa/r90/data", data)
os.environ["HUSHPLAYER_DATA_DIR"] = data
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
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
def top_y(view):
    return view.viewport().mapTo(ctx().window, view.viewport().rect().topLeft()).y() + view.rowViewportPosition(1) + view.rowHeight(1)//2
def check(label):
    view = ctx().window.stack.currentWidget().list.table
    print(label, runs(win.grab().toImage(), top_y(view)), flush=True)
def go():
    win.navigate("songs"); app.processEvents()
    view = ctx().window.stack.currentWidget().list.table
    view.selectRow(1); view._hover_row = 1; view.viewport().update(); app.processEvents()
    QTimer.singleShot(250, lambda: (check("A"), tweak_pal(view)))
def tweak_pal(view):
    pal = view.palette()
    pal.setColor(QPalette.ColorRole.Highlight, QColor(0,0,0,0))
    view.setPalette(pal); view.viewport().update(); app.processEvents()
    QTimer.singleShot(200, lambda: (check("B highlight=transparent"), tweak_qss(view)))
def tweak_qss(view):
    view.setStyleSheet(view.styleSheet() + " QTableView::item:selected{border:0px;background:transparent;}")
    view.viewport().update(); app.processEvents()
    QTimer.singleShot(200, lambda: (check("C qss border0"), app.quit()))
QTimer.singleShot(600, go)
app.exec()
