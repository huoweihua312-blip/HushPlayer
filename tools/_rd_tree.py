import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
time.sleep(14)
rows = []
def dump(hwnd, depth):
    cls = ctypes.create_unicode_buffer(128); u.GetClassNameW(hwnd, cls, 128)
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rows.append(f"{'  '*depth}{cls.value} pid={pid.value} text={buf.value!r}")
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, lparam):
        dump(h, depth + 1)
        return True
    u.EnumChildWindows(hwnd, cb, 0)

tops = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def top(hwnd, lparam):
    if u.IsWindowVisible(hwnd):
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
        if "HushPlayer" in buf.value or buf.value.strip().startswith("安装"):
            tops.append(hwnd)
    return True
u.EnumWindows(top, 0)
for h in tops:
    dump(h, 0)
pathlib.Path("artifacts/qa/r67/tree.txt").write_text("\n".join(rows), encoding="utf-8")
proc.terminate()
print("tops", len(tops), "rows", len(rows))
