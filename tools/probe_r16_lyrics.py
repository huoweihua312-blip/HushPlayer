import os, sys, pathlib
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r16/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.lyrics_search import LyricsSearchDialog

OUT = pathlib.Path("artifacts/qa/r16"); OUT.mkdir(parents=True, exist_ok=True)

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("lyrics")
page = win._pages["lyrics"]

def pump(sec):
    loop = QEventLoop(); QTimer.singleShot(int(sec * 1000), loop.quit); loop.exec()

def run():
    dialog = LyricsSearchDialog(win, initial="晴天 周杰伦")
    dialog.show()
    for _ in range(40):
        pump(0.25)
        if dialog.list.count() > 0 or "没有找到" in dialog.status.text():
            break
    pump(0.3)
    print("results", dialog.list.count(), "status", dialog.status.text(), flush=True)
    print("step: results shown", flush=True)
    dialog.list.setCurrentRow(0)
    pump(0.2)
    dialog.grab().save(str(OUT / "lyrics_search.png"))

    print("step: before accept", flush=True)
    if dialog.list.count():
        dialog._accept()
        print("step: accepted", flush=True)
        cand = dialog.candidate
        track = ctx().player.current
        if track is None:
            from hushplayer.model.track import Track
            track = Track(id="local:demo", kind="local", title="晴天", artist="周杰伦", duration_ms=269000)
        print("step: applying", flush=True)
        result = ctx().lyrics.apply_candidate(track, cand)
        print("step: applied", flush=True)
        page._track = track
        page._apply_result(result)
        page.view.set_document(result.document, keep_position=False)
        pump(0.4)
        win.grab().save(str(OUT / "lyrics_applied.png"))
        print("applied lines", len(result.document.lines), "kind", result.document.kind, "provider", result.provider, flush=True)
        print("RESULT PASS", flush=True)
    else:
        print("RESULT NO-RESULTS", flush=True)
    app.processEvents()
    os._exit(0)

QTimer.singleShot(700, run)
QTimer.singleShot(30000, lambda: os._exit(2))
app.exec()
