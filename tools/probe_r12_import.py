import os, sys, shutil
root = os.path.abspath("artifacts/qa/r12/gui")
shutil.rmtree(root, ignore_errors=True)
os.environ["HUSHPLAYER_DATA_DIR"] = root
os.environ.setdefault("HUSH_CONSOLE", "0")
sys.path.insert(0, ".")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QScrollArea
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx
from hushplayer.ui.pages.settings import SECTIONS

URL = os.environ.get("HUSHPLAYER_PROBE_SUBSCRIPTION", "")
app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("settings", "online")
page = win._pages["settings"]
keys = [s[0] for s in SECTIONS]

def pump(seconds):
    loop = QEventLoop(); QTimer.singleShot(int(seconds * 1000), loop.quit); loop.exec()

def run():
    ctx().settings.set("online.sources_expanded", True)
    page._show_section(keys.index("online"))
    page._fill_sources()
    pump(0.8)
    before = len(ctx().client.sources)
    QInputDialog.getText = staticmethod(lambda *a, **k: (URL, True))
    toasts = []
    page._toast = lambda text, kind="info": toasts.append(text)
    page._import_subscription()
    for _ in range(30):
        pump(0.5)
        if len(ctx().client.sources) > before:
            break
    pump(1.5)
    after = len(ctx().client.sources)
    names = [t for t in (getattr(s, "name", "") for s in ctx().client.sources)]
    print("sources", before, "->", after, flush=True)
    print("toasts", toasts, flush=True)
    print("states", [getattr(s, "state", "") or getattr(s, "loaded", "") for s in ctx().client.sources][-5:], flush=True)
    for area in page.findChildren(QScrollArea):
        bar = area.verticalScrollBar(); bar.setValue(int(bar.maximum() * 0.30))
    pump(0.5)
    win.grab().save("artifacts/qa/r12/settings_subscription_imported.png")
    errors = 0
    print("RESULT", "PASS" if after > before else "FAIL", flush=True)
    hush.shutdown(); app.quit()

QTimer.singleShot(700, run)
app.exec()
