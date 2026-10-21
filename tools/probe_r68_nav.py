import os, sys, traceback
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r68/data3")
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
app = QApplication(sys.argv); hush = HushApp(app); hush.start()
win = ctx().window
for route in ["home", "songs", "albums", "artists", "favorites", "recent", "search", "settings", "lyrics"]:
    try:
        win.navigate(route)
        for _ in range(3):
            app.processEvents()
        print("ok", route, flush=True)
    except Exception:
        print("FAIL", route, flush=True)
        traceback.print_exc()
        break
hush.shutdown()
