import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r26/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
os.environ["QT_SCALE_FACTOR"] = "1.25"
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from hushplayer.core.theme import apply_theme_to_app

variant = os.environ.get("VARIANT", "current")
app = QApplication(sys.argv)
apply_theme_to_app(app, preference="dark")

from PySide6.QtWidgets import QLabel
w = QLabel("设置  所有更改都会立即保存  HushPlayer")
w.setStyleSheet("background:#15151A; color:#F4F4F6;")
w.setFont(QFont("MiSans", 13))
if variant == "nohint":
    f = w.font(); f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality); w.setFont(f)
elif variant == "default":
    f = w.font(); f.setStyleStrategy(QFont.StyleStrategy.PreferDefault); w.setFont(f)
w.resize(560, 60)
w.show(); app.processEvents()
w.grab().save(f"artifacts/qa/r26/variant_{variant}.png")
print("saved", variant, flush=True)
os._exit(0)
