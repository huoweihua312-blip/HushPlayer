import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.online.registry import registry

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

before = len(registry().entries())
removed = registry().remove("custom_source_cdfcdfed80a8")
after_remove = len(registry().entries())
restored = registry().restore_bundled()
after_restore = len(registry().entries())
print("registry", before, "->", after_remove, "restored", restored, "->", after_restore, flush=True)

win.navigate("settings", "online")
pump(1200)
win.grab().save("artifacts/qa/r2/settings_online_manage.png")
print("saved", flush=True)
hush.shutdown(); app.quit()
