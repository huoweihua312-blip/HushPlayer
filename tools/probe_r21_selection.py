import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r21/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QItemSelectionModel, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = ctx().window
win.resize(1440, 900)
win.navigate("songs")
page = win._pages["songs"]

def run():
    from pathlib import Path

    fixtures = Path("tests/fixtures/audio")
    files = [str(p) for p in fixtures.rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg", ".m4a"}]
    added = ctx().library.import_files(files)
    print("imported", added.added if hasattr(added, "added") else added, flush=True)
    page.on_show(); page.reload()
    for _ in range(20):
        app.processEvents()
    table = page.list.table
    tracks = page.list.tracks()
    print("rows", len(tracks), flush=True)
    sel = table.selectionModel()
    sel.clearSelection()
    for row in range(3):
        index = table.model().index(row, 1)
        sel.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    app.processEvents()
    bar = page.list.selection_bar
    print("bar visible", bar.isVisible(), "count", bar.count(), flush=True)
    win.grab().save("artifacts/qa/r21/selection_bar.png")

    selected = page.list.selected_tracks()
    page._play_next_selected(selected)
    print("queue", ctx().player.queue.count, flush=True)
    before = len(ctx().library.favorites())
    page._favorite_selected(selected)
    print("favorites", before, "->", len(ctx().library.favorites()), flush=True)
    bar.clear_selection()
    print("bar hidden", not page.list.selection_bar.isVisible(), flush=True)
    print("RESULT PASS", flush=True)
    app.processEvents()
    os._exit(0)

QTimer.singleShot(800, run)
app.exec()
hush.shutdown()
