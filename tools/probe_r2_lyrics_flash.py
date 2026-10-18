import os, sys, time
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.services.library import LibraryQuery
from hushplayer.ui.context import ctx

def luma(pix):
    img = pix.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = img.width(), img.height()
    t = n = 0
    for y in range(0, h, max(1, h // 80)):
        for x in range(0, w, max(1, w // 120)):
            t += img.pixelColor(x, y).red(); n += 1
    return t / max(1, n)

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = hush.window
fixtures = os.path.abspath("tests/fixtures/audio")
if hush.library.stats.track_count == 0:
    hush.library.import_files([os.path.join(r, f) for r, _, fs in os.walk(fixtures) for f in fs])
tracks = hush.library.tracks_page(LibraryQuery(limit=5))
print("tracks", [t.title for t in tracks], flush=True)
ctx().player.play_tracks(tracks, 0, context="r2")
samples = []
calls = {"mood": 0, "mode": 0, "paint": 0}

def begin():
    win.open_immersive(); app.processEvents()
    imm = ctx().immersive
    imm.set_mode("lyrics", animate=False)
    app.processEvents()
    orig = imm.background.set_mood
    def spy(*a, **k):
        calls["mood"] += 1
        return orig(*a, **k)
    imm.background.set_mood = spy
    print("start luma", round(luma(imm.grab()), 1), flush=True)
    step()

def step(i=[0]):
    imm = ctx().immersive
    if imm is None:
        return
    pix = imm.grab()
    samples.append(round(luma(pix), 1))
    i[0] += 1
    if i[0] < 80:
        QTimer.singleShot(120, step)
    else:
        print("samples", samples, flush=True)
        print("mood calls", calls["mood"], flush=True)
        ctx().immersive.close_immersive(); app.quit()

QTimer.singleShot(1500, begin)
QTimer.singleShot(40000, app.quit)
app.exec()
hush.shutdown()
