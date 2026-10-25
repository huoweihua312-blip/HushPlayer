"""R92: verify the selected/hover row band is one continuous colour.

Renders the real songs page at 150% type scale, selects row 2, hovers row 2,
then samples the same row across every column.  Any per-cell stacking or seam
shows up as different RGB values in the samples.
"""

import os
import shutil
import sys

sys.path.insert(0, ".")
base = os.path.abspath("artifacts/qa/r92")
data = os.path.join(base, "data")
os.makedirs(base, exist_ok=True)
if os.path.isdir(data):
    shutil.rmtree(data)
shutil.copytree("artifacts/qa/r90/data", data)
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


def table():
    return ctx().window.stack.currentWidget().list.table


def shot(name):
    win.grab().save(os.path.join(base, name))
    print("saved", name, flush=True)


def sample(img, y_offsets, xs):
    """Print RGB at (x, row_center + dy) for each dy/x."""
    for dy in y_offsets:
        row = [img.pixelColor(x, y).name() for x, y in xs(dy)]
        print(f"y+{dy}: " + " ".join(row), flush=True)


def step_select():
    win.navigate("songs")
    app.processEvents()
    view = table()
    row = 1
    y = view.rowViewportPosition(row) + view.rowHeight(row) // 2
    view._hover_row = row
    view.selectRow(row)
    view.viewport().update()
    app.processEvents()
    QTimer.singleShot(320, lambda: finish(y))


def finish(y):
    view = table()
    img = win.grab().toImage()
    left = view.viewport().mapTo(ctx().window, view.viewport().rect().topLeft()).y()
    y_abs = left + y
    width = view.viewport().width()
    left_x = view.viewport().mapTo(ctx().window, view.viewport().rect().topLeft()).x()
    xs = [left_x + int(width * frac) for frac in (0.05, 0.22, 0.45, 0.65, 0.84, 0.95)]
    print("ROW_Y", y_abs, "WIDTH", width, "LEFT", left_x, flush=True)
    sample(img, (0,), lambda dy: [(x, y_abs + dy) for x in xs])
    shot("band_selected.png")
    # now move the selection away and hover only row 3
    view.clearSelection()
    view._hover_row = 2
    view.viewport().update()
    app.processEvents()
    QTimer.singleShot(220, lambda: finish_hover(y))


def finish_hover(_y):
    view = table()
    img = win.grab().toImage()
    left = view.viewport().mapTo(ctx().window, view.viewport().rect().topLeft()).y()
    row = 2
    y_abs = left + view.rowViewportPosition(row) + view.rowHeight(row) // 2
    width = view.viewport().width()
    left_x = view.viewport().mapTo(ctx().window, view.viewport().rect().topLeft()).x()
    xs = [left_x + int(width * frac) for frac in (0.05, 0.22, 0.45, 0.65, 0.84, 0.95)]
    print("HOVER_Y", y_abs, "LEFT", left_x, flush=True)
    sample(img, (0,), lambda dy: [(x, y_abs + dy) for x in xs])
    shot("band_hover.png")
    app.quit()


QTimer.singleShot(600, step_select)
app.exec()
