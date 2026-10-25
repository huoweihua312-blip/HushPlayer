import os, sys, shutil
sys.path.insert(0, ".")
base = os.path.abspath("artifacts/qa/r92b"); data = os.path.join(base, "data")
os.makedirs(base, exist_ok=True)
if os.path.isdir(data): shutil.rmtree(data)
shutil.copytree("artifacts/qa/r90/data", data)
os.environ["HUSHPLAYER_DATA_DIR"] = data
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1560, 980); win.show(); app.processEvents()

def blue_runs(img, y):
    w = img.width(); runs=[]; cur=None
    for x in range(w):
        c = img.pixelColor(x, y)
        hit = abs(c.red()-76)<25 and abs(c.green()-194)<25 and abs(c.blue()-255)<25
        if hit:
            if cur is None: cur=x
        elif cur is not None: runs.append((cur,x-1)); cur=None
    return runs

def check(label):
    img = win.grab().toImage()
    view = ctx().window.stack.currentWidget().list.table
    top = view.viewport().mapTo(ctx().window, view.viewport().rect().topLeft()).y()
    y = top + view.rowViewportPosition(1) + view.rowHeight(1)//2
    print(label, "blue:", blue_runs(img, y), flush=True)

def go():
    win.navigate("songs"); app.processEvents()
    view = ctx().window.stack.currentWidget().list.table
    view.selectRow(1); view._hover_row = 1; view.viewport().update(); app.processEvents()
    QTimer.singleShot(250, lambda: (check("A default"), view.clearFocus(), view.viewport().update(), app.processEvents(), QTimer.singleShot(150, lambda: (check("B nofocus"), set_policy(view)))))

def set_policy(view):
    view.setFocusPolicy(Qt.NoFocus); view.viewport().update(); app.processEvents()
    QTimer.singleShot(150, lambda: (check("C policy"), view.clearSelection(), view.viewport().update(), app.processEvents(), QTimer.singleShot(150, lambda: (check("D noselect"), app.quit()))))

QTimer.singleShot(600, go)
app.exec()
