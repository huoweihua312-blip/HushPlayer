import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r38/data")
os.environ["HUSHPLAYER_TYPE_SCALE"] = "1.5"
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from hushplayer.app import HushApp
from hushplayer.core.settings import Settings
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
ctx().library.import_files([str(p) for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()])
win = ctx().window; win.resize(1600, 1000)

def switch():
    win.navigate("settings"); app.processEvents()
    page = win._page("settings")
    page._show_section(1); app.processEvents()
    hush.settings.set("appearance.theme", "light")
    hush.apply_theme()
    QTimer.singleShot(240, mid)
def mid():
    win.grab().save("artifacts/qa/r38/theme_mid.png")
    QTimer.singleShot(900, close_dialog)

def close_dialog():
    hush.settings.set("general.close_action", "ask")
    QTimer.singleShot(350, shoot_dialog)
    win.close()

def shoot_dialog():
    dlg = QApplication.activeModalWidget()
    if dlg is not None:
        dlg.grab().save("artifacts/qa/r38/close_dialog.png")
        dlg.reject()
    QTimer.singleShot(200, finish)

def finish():
    print("RESULT PASS", flush=True); app.quit()

QTimer.singleShot(900, switch); app.exec(); hush.shutdown()
