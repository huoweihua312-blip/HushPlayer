import os, sys, faulthandler, traceback
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r68/data2")
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
faulthandler.enable()
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
app = QApplication(sys.argv)
hush = HushApp(app)
try:
    hush.start()
    print("started ok", flush=True)
    from hushplayer.ui.context import ctx
    print("queue panel:", ctx().window.queue_panel is not None, flush=True)
    hush.shutdown()
    print("shutdown ok", flush=True)
except Exception:
    traceback.print_exc()
