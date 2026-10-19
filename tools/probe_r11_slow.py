import os, sys, time
root = os.path.abspath("artifacts/qa/r11/slow")
os.environ["HUSHPLAYER_DATA_DIR"] = root
os.environ.setdefault("HUSH_CONSOLE", "0")
sys.path.insert(0, ".")
import shutil, pathlib
shutil.rmtree(root, ignore_errors=True)
os.makedirs(root, exist_ok=True)

from hushplayer.online import registry as registry_mod
reg = registry_mod.registry(); reg.ensure()
slow = root and pathlib.Path(root) / "slow_source.js"
slow.write_text("""
module.exports = {
  platform: "SlowTest",
  version: "1.0.0",
  search: async function (keyword) {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    return [];
  },
  getMediaSource: async function () { throw new Error("nope"); },
};
""", encoding="utf-8")
reg.install_file(slow, content_policy="user_owned")
slow.unlink(missing_ok=True)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

app = QApplication(sys.argv)
hush = HushApp(app); hush.start()
win = ctx().window
win.navigate("search")
page = win._pages["search"]

def pump(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

pump(2500)
page._on_mode(1)
started = time.monotonic()
page.field.set_text("\u6674\u5929")
page._on_submit("\u6674\u5929")
first = None
while time.monotonic() - started < 15:
    rows = page.online_list.table.model().rowCount()
    if rows and first is None:
        first = time.monotonic() - started
        print("first paint %.2fs rows=%d status=%s" % (first, rows, page.online_status.text()), flush=True)
        win.grab().save("artifacts/qa/r11/search_streaming.png")
    if getattr(page, "_finished", False):
        break
    pump(40)
print("finished %.2fs rows=%d" % (time.monotonic() - started, page.online_list.table.model().rowCount()), flush=True)
hush.shutdown(); app.quit()
