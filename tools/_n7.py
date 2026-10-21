import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
time.sleep(14)
rows = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, lparam):
    cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
    if cls.value in ("TWizardForm", "#32770") and buf.value.strip():
        rows.append(f"{cls.value} {buf.value!r}")
    return True
u.EnumWindows(cb, 0)
pathlib.Path("artifacts/qa/r67/wins5.txt").write_text("\n".join(rows), encoding="utf-8")
print("alive", proc.poll() is None)
