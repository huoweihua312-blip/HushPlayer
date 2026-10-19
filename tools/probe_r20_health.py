import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r20/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QScrollArea
from hushplayer.app import HushApp
from hushplayer.online import health
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("settings", "online")
page = win._pages["settings"]
health.reset()
health.record_ok("custom_source_52a08ed9d22b")
health.record_ok("custom_source_52a08ed9d22b")
health.record_fail("custom_source_52a08ed9d22b", "HTTP 404")
health.record_fail("custom_source_91ed34e4e9e2", "HTTP 404")

def shot():
    page._fill_sources()
    for _ in range(20):
        app.processEvents()
    for area in page.findChildren(QScrollArea):
        bar = area.verticalScrollBar(); bar.setValue(int(bar.maximum() * 0.18))
    app.processEvents()
    win.grab().save("artifacts/qa/r20/settings_health.png")
    print("subscription url", repr(ctx().settings.get("online.subscription_url", "")), flush=True)
    print("has check button", any("检查更新" in b.text() for b in page.findChildren(type(page.clear_button)) if hasattr(b, "text")), flush=True)
    print("RESULT PASS", flush=True)
    app.quit()

QTimer.singleShot(900, shot)
app.exec()
hush.shutdown()
