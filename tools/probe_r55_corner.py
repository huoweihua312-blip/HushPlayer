import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r55/data")
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1280, 820); win.show(); app.processEvents()
win.navigate("home"); app.processEvents()
host = getattr(win, "container", None) or win
img = host.grab().toImage()
print("host", host.geometry().getRect())
for name in ("sidebar", "_sidebar", "stack", "_stack", "pages", "titlebar"):
    w = getattr(win, name, None)
    if w is not None:
        print(name, w.geometry().getRect(), w.__class__.__name__)
page = win._page("home")
print("page", page.geometry().getRect(), "parent", page.parent().__class__.__name__)
for x in (238, 240, 242, 250, 300, 330, 340, 350):
    line = [img.pixelColor(x, y).name() for y in (2, 40, 70, 73, 76, 80, 90)]
    print(x, line)
img.save("artifacts/qa/r55/topleft.png")
hush.shutdown()
