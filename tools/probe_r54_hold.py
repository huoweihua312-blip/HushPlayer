import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r54/data")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
from hushplayer.app import HushApp
from hushplayer.core.theme import apply_theme_to_app, theme
from hushplayer.ui.context import ctx
from hushplayer.ui.widgets.transition import SunMoonReveal

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1600, 1000); win.show(); app.processEvents()
host = getattr(win, "container", None) or win
def shot():
    app.processEvents(); return host.grab()
dark = shot()
apply_theme_to_app(app, preference="light"); app.setStyleSheet(theme().qss()); win.refresh_theme(); app.processEvents()
light = shot()
for name, old, new, to_dark in (("sun", dark, light, False), ("moon", light, dark, True)):
    ov = SunMoonReveal(host, old, new, QPointF(0, 0), to_dark=to_dark, pop_ms=420, hold_ms=420, icon_scale=1.2)
    for progress in (0.18, 0.28, 0.34, 0.45, 0.60, 0.75, 0.90, 1.0):
        ov.freeze(); ov.set_reveal_progress(progress); app.processEvents()
        host.grab().save(f"artifacts/qa/r54/{name}_{int(progress*100)}.png")
    ov.finish(); app.processEvents()
print("RESULT PASS", flush=True)
hush.shutdown()
