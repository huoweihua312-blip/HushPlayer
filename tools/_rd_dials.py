import ctypes, time, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
rows = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    if u.IsWindowVisible(hwnd):
        cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(hwnd, cls, 64)
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
        if cls.value in ("#32770", "TWizardForm", "TFormSetup"):
            rows.append(f"{cls.value} {buf.value!r}")
    return True
u.EnumWindows(cb, 0)
pathlib.Path("artifacts/qa/r67/dialogs.txt").write_text("\n".join(rows), encoding="utf-8")
print("windows", rows)
