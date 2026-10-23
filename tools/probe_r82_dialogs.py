import os, sys, time
sys.path.insert(0, ".")
os.environ["HUSHPLAYER_DATA_DIR"] = os.path.abspath("artifacts/qa/r82/data")
os.environ["HUSHPLAYER_NO_CLOSE_PROMPT"] = "1"
os.environ["HUSHPLAYER_MUTEX_SUFFIX"] = "r82"
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.dialogs import MessageDialog, TextInputDialog
from hushplayer.ui.playlist_import_dialog import PlaylistImportDialog
from hushplayer.services.playlist_import import PlaylistEntry

app = QApplication([])
hush = HushApp(app); hush.start()
win = hush.window; win.resize(1280, 820); win.show(); app.processEvents()
out = "artifacts/qa/r82"; os.makedirs(out, exist_ok=True)

def pump(ms=200):
    end = time.monotonic() + ms/1000
    while time.monotonic() < end:
        app.processEvents(); time.sleep(0.01)

def capture(dialog, name):
    dialog.show(); pump(200)
    dialog.grab().save(f"{out}/{name}.png")
    print("saved", name, dialog.size())
    dialog.close()

ENTRIES = [
    PlaylistEntry(title="夜航信号", artist="Aurora Field"),
    PlaylistEntry(title="Long Way Home", artist="The Paper Lanterns"),
    PlaylistEntry(title="凌晨四点的海", artist="Aurora Field"),
    PlaylistEntry(title="晴天", artist="周杰伦"),
    PlaylistEntry(title="家书", artist="加木"),
    PlaylistEntry(title="一首根本不存在的歌", artist="查无此人"),
]

def run(mode):
    hush.settings.set("appearance.theme", mode); hush.apply_theme(); pump(300)
    capture(MessageDialog(None, "删除歌单", "确定要删除歌单「夜间通勤」吗？删除后无法恢复。", kind="warning", buttons=[("cancel","取消"),("ok","删除")], accent="ok"), f"confirm_{mode}")
    capture(MessageDialog(None, "导入完成", "已导入 3 首歌曲，3 首未匹配。", kind="success", detail="未匹配的歌曲已导出到：\nD:\\HushPlayer\\exports\\夜间通勤-unmatched.csv", buttons=[("ok","好的")]), f"notify_{mode}")
    capture(TextInputDialog(None, "新建歌单", "给这个歌单起个名字", text="夜间通勤"), f"ask_{mode}")
    dlg = PlaylistImportDialog(win)
    dlg._accept_entries("夜间通勤 导入", ENTRIES, "来自 测试文件")
    dlg.resize(980, 700); dlg.show(); pump(200)
    dlg.online_toggle.setChecked(False)
    dlg._go_next(); pump(900)
    dlg.grab().save(f"{out}/import_table_{mode}.png"); print("saved import_table", mode, dlg._matcher.counts())
    dlg.close()

run("light"); run("dark")
hush.shutdown(); print("done")
