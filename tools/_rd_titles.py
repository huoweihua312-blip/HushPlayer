import ctypes, time, subprocess
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
time.sleep(4)
titles = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    if u.IsWindowVisible(hwnd):
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip(): titles.append((hwnd, buf.value))
    return True
u.EnumWindows(cb, 0)
for h, t in titles:
    print("TITLE", repr(t))
if proc.poll() is None: proc.terminate()
