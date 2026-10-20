import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r55/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1280, 820); win.show(); app.processEvents()
def go():
    win.navigate("home"); app.processEvents()
    QTimer.singleShot(600, shot)
def shot():
    host = getattr(win, "container", None) or win
    host.grab().save("artifacts/qa/r55/topleft_real.png")
    from PIL import Image
    im = Image.open("artifacts/qa/r55/topleft_real.png")
    im.crop((200, 0, 520, 160)).resize((640, 320), Image.NEAREST).save("artifacts/qa/r55/topleft_zoom.png")
    print("SIZE", im.size, flush=True)
    print("RESULT PASS", flush=True)
    app.quit()
QTimer.singleShot(700, go)
QTimer.singleShot(12000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
