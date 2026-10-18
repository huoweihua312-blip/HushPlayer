import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/tmp_shots/data")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFrame
from hushplayer.app import HushApp

records = []
warnings = []
def handler(mode, ctx, msg):
    if "parse stylesheet" in msg:
        warnings.append(msg)
qInstallMessageHandler(handler)

app = QApplication(sys.argv)
orig = QWidget.setStyleSheet
def patched(self, css):
    records.append((type(self).__name__, css))
    orig(self, css)
QWidget.setStyleSheet = patched
h = HushApp(app); h.start(); h.window.resize(1280, 820); h.window.show()
app.processEvents()
print("warnings", len(warnings))
for msg in warnings[:6]: print("W:", msg)
print("records", len(records))
seen = set()
for cls, css in records:
    key = (cls, css)
    if key in seen: continue
    seen.add(key)
    if not css.strip(): continue
    warnings.clear()
    w = QFrame() if cls in ("QFrame","Card") else QLabel()
    orig(w, css)
    w.show(); app.processEvents()
    if warnings:
        print("BAD", cls, repr(css[:200]))
h.shutdown()
