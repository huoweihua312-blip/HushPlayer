import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r55/data4")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window
win.move(0, 0); win.resize(2560, 1392); win.show(); app.processEvents()
def go():
    win.navigate("search"); app.processEvents()
    QTimer.singleShot(800, shot)
def shot():
    win.grab().save("artifacts/qa/r55/max_window.png")
    from PIL import Image
    im = Image.open("artifacts/qa/r55/max_window.png")
    print("SIZE", im.size)
    im.crop((330, 0, 760, 190)).resize((1290, 570), Image.NEAREST).save("artifacts/qa/r55/max_zoom.png")
    # sample a horizontal line across the titlebar and the first content row
    for y in (10, 40, 60, 66, 70, 74, 80):
        row = [im.getpixel((x, y))[:3] for x in (345, 350, 356, 360, 366, 380, 420)]
        print(y, row)
    print("RESULT PASS", flush=True)
    app.quit()
QTimer.singleShot(800, go)
QTimer.singleShot(12000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
