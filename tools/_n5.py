import ctypes, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
rows = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def top(h, lparam):
    cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
    if cls.value == "#32770":
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
        if buf.value == "错误":
            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def child(c, lp):
                k = ctypes.create_unicode_buffer(64); u.GetClassNameW(c, k, 64)
                if k.value == "Static":
                    m = u.GetWindowTextLengthW(c)
                    b = ctypes.create_unicode_buffer(m + 1); u.GetWindowTextW(c, b, m + 1)
                    if b.value.strip(): rows.append(b.value)
                return True
            u.EnumChildWindows(h, child, 0)
    return True
u.EnumWindows(top, 0)
pathlib.Path("artifacts/qa/r67/error.txt").write_text("\n".join(rows), encoding="utf-8")
print("rows", len(rows))
