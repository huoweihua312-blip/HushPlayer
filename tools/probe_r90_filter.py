import os, sys, shutil
sys.path.insert(0, ".")
base = os.path.abspath("artifacts/qa/r90")
data = os.path.join(base, "data")
os.makedirs(base, exist_ok=True)
if not os.path.isdir(data):
    shutil.copytree("artifacts/qa/r62/data", data)
os.environ["HUSHPLAYER_DATA_DIR"] = data
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
win = ctx().window
win.resize(1560, 980)
win.show()
app.processEvents()

def page():
    return win.stack.currentWidget()

def shot(name):
    win.grab().save(os.path.join(base, name))
    print("saved", name, flush=True)

def step_songs(i=0):
    win.navigate("songs"); app.processEvents()
    pg = page()
    pg.filter.set_text("夜航")
    app.processEvents()
    QTimer.singleShot(350, lambda: (shot("songs_filtered.png"), step_fav()))

def step_fav():
    win.navigate("favorites"); app.processEvents()
    pg = page()
    pg.filter.set_text("夜航")
    app.processEvents()
    QTimer.singleShot(350, lambda: (shot("favorites_filtered.png"), step_empty()))

def step_empty():
    pg = page()
    pg.filter.set_text("不存在的歌")
    app.processEvents()
    QTimer.singleShot(300, lambda: (shot("filter_empty.png"), finish()))

def finish():
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(900, step_songs)
QTimer.singleShot(20000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec()
hush.shutdown()
