import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r53/data")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window; win.resize(1200, 800); win.show(); app.processEvents()
hush.settings.set("appearance.theme_animation_mode", "sunrise")
hush.settings.set("appearance.theme", "dark"); app.processEvents()
def flip():
    hush.settings.set("appearance.theme", "light"); app.processEvents()
    hush.settings.set("appearance.theme", "dark"); app.processEvents()
    hush.settings.set("appearance.theme", "light"); app.processEvents()
    print("RESULT PASS", flush=True)
    app.quit()
QTimer.singleShot(200, flip)
QTimer.singleShot(6000, lambda: (print("TIMEOUT", flush=True), app.quit()))
app.exec(); hush.shutdown()
