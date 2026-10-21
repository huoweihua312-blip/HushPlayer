import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
time.sleep(5)
titles = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    if u.IsWindowVisible(hwnd):
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip(): titles.append(f"{hwnd}\t{buf.value}")
    return True
u.EnumWindows(cb, 0)
pathlib.Path("artifacts/qa/r67/titles.txt").write_text("\n".join(titles), encoding="utf-8")
if proc.poll() is None: proc.terminate()
print("written", len(titles))
