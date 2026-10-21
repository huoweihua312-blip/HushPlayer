import ctypes, time, sys
from ctypes import wintypes
u = ctypes.windll.user32
Edit = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(hwnd, cls, 64)
    if cls.value == "Edit":
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip(): Edit.append(buf.value)
    return True
u.EnumWindows(cb, 0)
for e in Edit: print("EDIT", e)
