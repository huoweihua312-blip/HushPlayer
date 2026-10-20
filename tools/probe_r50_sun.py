import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r50/data")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
from hushplayer.app import HushApp
from hushplayer.core.theme import apply_theme_to_app, theme
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.transition import SunriseReveal

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1600, 1000); win.show(); app.processEvents()
host = getattr(win, "container", None) or win

def snapshot():
    app.processEvents()
    return host.grab()

dark = snapshot()
apply_theme_to_app(app, preference="light")
app.setStyleSheet(theme().qss()); win.refresh_theme(); app.processEvents()
light = snapshot()

for name, old, new, to_dark in (
    ("sunrise", dark, light, False),
    ("sunset", light, dark, True),
):
    ov = SunriseReveal(host, old, new, QPointF(0, 0), to_dark=to_dark)
    ov.freeze()
    ov.set_reveal_progress(0.45)
    app.processEvents()
    _ = host.grab().save(f"artifacts/qa/r50/{name}_45.png")
    ov.set_reveal_progress(0.75)
    app.processEvents()
    host.grab().save(f"artifacts/qa/r50/{name}_75.png")
    ov.finish()
    app.processEvents()
print("RESULT PASS", flush=True)
hush.shutdown()
