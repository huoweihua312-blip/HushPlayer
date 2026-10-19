import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r37/data2")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.model.track import Track
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
win = ctx().window; win.resize(1400, 900)
win.navigate("songs"); app.processEvents()
page = win._page("songs")
tracks = [
    Track(
        id=f"kw:row{i}",
        title=f"茶花开了，该回家了 第{i+1}版（现场）",
        artist="王睿卓、加木",
        album="茶花开了，该回家了",
        duration_ms=180000,
        source_id="kw",
        source_name="酷我",
    )
    for i in range(8)
]
page.list.set_tracks(tracks)
def shot():
    win.grab().save("artifacts/qa/r37/offline_rows.png")
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(900, shot); app.exec(); hush.shutdown()
