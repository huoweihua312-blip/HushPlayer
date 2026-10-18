import ctypes, os, sys
sys.path.insert(0, ".")
os.environ.setdefault("HUSHPLAYER_DATA_DIR", os.path.abspath("artifacts/qa/r2/data"))
os.environ.setdefault("HUSH_CONSOLE", "0")
from ctypes import wintypes
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from hushplayer.app import HushApp
from hushplayer.ui.context import ctx

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsWindowVisible = user32.IsWindowVisible
GetClassNameW = user32.GetClassNameW
GetWindowTextW = user32.GetWindowTextW
GetWindowRect = user32.GetWindowRect

class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

def windows():
    pid = os.getpid()
    out = []
    def cb(hwnd, _):
        p = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256); GetClassNameW(hwnd, cls, 256)
            txt = ctypes.create_unicode_buffer(256); GetWindowTextW(hwnd, txt, 256)
            r = RECT(); GetWindowRect(hwnd, ctypes.byref(r))
            out.append((cls.value, txt.value, (r.l, r.t, r.r - r.l, r.b - r.t)))
        return True
    EnumWindows(EnumWindowsProc(cb), 0)
    return out

app = QApplication(sys.argv)
app.setStyle("Fusion")
hush = HushApp(app); hush.start()
win = hush.window

def phase1():
    win.navigate("search"); app.processEvents()
    page = win._pages["search"]
    print("BEFORE:", windows(), flush=True)
    page.field.setFocus()
    QTimer.singleShot(400, phase2)

def phase2():
    page = win._pages["search"]
    page.field.set_text("加木")
    app.processEvents()
    QTimer.singleShot(2500, phase3)

def phase3():
    print("AFTER:", windows(), flush=True)
    page = win._pages["search"]
    for w in QApplication.topLevelWidgets():
        print("TL", type(w).__name__, w.isVisible(), w.geometry(), flush=True)
    app.quit()

QTimer.singleShot(1200, phase1)
QTimer.singleShot(20000, app.quit)
app.exec()
hush.shutdown()
