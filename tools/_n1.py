import ctypes, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
rows = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, lparam):
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
    cls = ctypes.create_unicode_buffer(128); u.GetClassNameW(h, cls, 128)
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    if pid.value and buf.value.strip():
        rows.append(f"pid={pid.value} vis={bool(u.IsWindowVisible(h))} {cls.value} {buf.value!r}")
    return True
u.EnumWindows(cb, 0)
pathlib.Path("artifacts/qa/r67/wins.txt").write_text("\n".join(rows), encoding="utf-8")
print("rows", len(rows))
