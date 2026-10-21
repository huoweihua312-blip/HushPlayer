import ctypes, time, subprocess, sys
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer\HushPlayer.exe"])
time.sleep(6)
hwnd = None
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, lp):
    global hwnd
    if u.IsWindowVisible(h):
        n = u.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, b, n + 1)
            cls = ctypes.create_unicode_buffer(256); u.GetClassNameW(h, cls, 256)
            if "HushPlayer" in b.value and cls.value.startswith("Qt"):
                hwnd = h
    return True
u.EnumWindows(cb, 0)
print("hwnd", hwnd)
if hwnd:
    u.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    rect = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(rect))
    print("before", rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    # drag the right edge 180px to the left
    y = (rect.top + rect.bottom) // 2
    x = rect.right - 3
    u.SetCursorPos(x, y); time.sleep(0.3)
    u.mouse_event(0x0002, 0, 0, 0, 0)      # left down
    time.sleep(0.15)
    for step in range(1, 19):
        u.SetCursorPos(x - step * 10, y); time.sleep(0.02)
    time.sleep(0.15)
    u.mouse_event(0x0004, 0, 0, 0, 0)      # left up
    time.sleep(1.0)
    after = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(after))
    print("after ", after.left, after.top, after.right - after.left, after.bottom - after.top)
    print("RESIZE", "PASS" if (after.right - after.left) < (rect.right - rect.left) - 100 else "FAIL")
proc.terminate()
