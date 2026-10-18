import os, sys, time
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
imm = None
samples = []

def luma(pix):
    img = pix.toImage()
    total = 0; n = 0
    for y in range(0, img.height(), 40):
        for x in range(0, img.width(), 40):
            total += img.pixelColor(x, y).lightness(); n += 1
    return total / max(1, n)

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

def go():
    global imm
    win.open_immersive()
    pump(700)
    imm = ctx().immersive
    samples.append(("open", luma(imm.grab())))
    for i in range(3):
        imm.set_mode("lyrics")
        for _ in range(10):
            pump(40); samples.append((f"to-lyrics-{i}", luma(imm.grab())))
        imm.set_mode("cover")
        for _ in range(10):
            pump(40); samples.append((f"to-cover-{i}", luma(imm.grab())))
    imm.close_immersive()
    pump(300)
    base = sorted(v for _, v in samples)[len(samples)//2]
    worst = max(samples, key=lambda kv: abs(kv[1] - base))
    print(f"samples={len(samples)} median={base:.1f} worst={worst[0]}={worst[1]:.1f} delta={worst[1]-base:+.1f}", flush=True)
    print("RESULT", "PASS" if abs(worst[1]-base) < 25 else "FAIL", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(800, go)
app.exec()
