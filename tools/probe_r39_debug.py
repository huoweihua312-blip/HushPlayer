import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r39/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.core.theme import theme
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1600, 1000); win.show(); app.processEvents()
state = {}
def go():
    print("mode_before", theme().mode, "resolved", hush._resolved_mode, "anim_setting",
          hush.settings.get("appearance.theme_animation", "?"), flush=True)
    hush.apply_theme(preference="light", animate=True)
    print("mode_after", theme().mode, flush=True)
    QTimer.singleShot(120, mid)
def mid():
    win.grab().save("artifacts/qa/r39/mid.png")
    QTimer.singleShot(700, end)
def end():
    win.grab().save("artifacts/qa/r39/end.png")
    print("mode_end", theme().mode, flush=True)
    print("RESULT PASS", flush=True); app.quit()
QTimer.singleShot(600, go); app.exec(); hush.shutdown()
