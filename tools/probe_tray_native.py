import ctypes, ctypes.wintypes as w, sys, time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
                ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT),
                ("uFlags", w.UINT), ("uCallbackMessage", w.UINT), ("hIcon", w.HICON),
                ("szTip", w.WCHAR * 128), ("dwState", w.DWORD), ("dwStateMask", w.DWORD),
                ("szInfo", w.WCHAR * 256), ("uVersion", w.UINT),
                ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HICON)]

def wndproc(hwnd, msg, wp, lp):
    return user32.DefWindowProcW(hwnd, msg, wp, lp)

proc = WNDPROC(wndproc)
hinst = kernel32.GetModuleHandleW(None)
cls = WNDCLASSEXW()
cls.cbSize = ctypes.sizeof(WNDCLASSEXW); cls.lpfnWndProc = proc
cls.hInstance = hinst; cls.lpszClassName = "HushTrayProbe"
if not user32.RegisterClassExW(ctypes.byref(cls)):
    print("RegisterClass err", kernel32.GetLastError()); sys.exit(1)
hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "probe", 0, 0, 0, 0, 0, None, None, hinst, None)
print("hwnd", hwnd)

hicon = user32.LoadImageW(None, r"F:\Projects\HushPlayer-Reimagined\assets\hushplayer.ico", 1, 16, 16, 0x10)
print("hicon", hicon)
nid = NOTIFYICONDATAW()
nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW); nid.hWnd = hwnd; nid.uID = 1
nid.uFlags = 0x1 | 0x2 | 0x4  # NIF_MESSAGE | NIF_ICON | NIF_TIP
nid.uCallbackMessage = 0x0400 + 1; nid.hIcon = hicon; nid.szTip = "HushPlayer native"
ok = shell32.Shell_NotifyIconW(0, ctypes.byref(nid))  # NIM_ADD
print("Shell_NotifyIconW add", ok, "err", kernel32.GetLastError())

app = QApplication(sys.argv)
def grab():
    app.primaryScreen().grabWindow(0).save("artifacts/qa/r39/screen_native_tray.png")
    print("grabbed", flush=True)
QTimer.singleShot(2000, grab)
QTimer.singleShot(2600, app.quit)
app.exec()
shell32.Shell_NotifyIconW(2, ctypes.byref(nid))  # NIM_DELETE
print("done")
