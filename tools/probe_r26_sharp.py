import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r26/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.core import display
from hushplayer.core.theme import apply_theme_to_app
from hushplayer.ui.pages.page import PageHeader
from hushplayer.ui.widgets.sidebar import LogoMark

factor = float(os.environ.get("HUSH_SCALE", "1.25"))
os.environ["QT_SCALE_FACTOR"] = str(factor)
app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")
w = PageHeader("设置", "所有更改都会立即保存")
w.resize(900, 110)
w.show()
app.processEvents()
w.grab().save(f"artifacts/qa/r26/header_{factor}.png")
print("saved", factor, flush=True)
os._exit(0)
