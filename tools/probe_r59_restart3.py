import os, sys
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r59/data4")
os.environ["HUSH_CONSOLE"] = "0"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
ctx().settings.set("appearance.ui_scale", "1.5"); ctx().settings.flush()
ctx().window._page("settings")._restart_app()
open("artifacts/qa/r59/restart_requested.txt","w").write("ok")
os._exit(0)
