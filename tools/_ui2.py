import ctypes, time
from ctypes import wintypes
u = ctypes.windll.user32
def win():
    res = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                if b.value.startswith("安装 - "):
                    res.append(h)
        return True
    u.EnumWindows(cb, 0)
    return res[0] if res else None
def kids(h):
    out = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(ch, l):
        n = u.GetWindowTextLengthW(ch)
        t = ""
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(ch, b, n + 1)
            t = b.value
        out.append((ch, t))
        return True
    u.EnumChildWindows(h, cb, 0)
    return out
h = win()
print("window", bool(h))
if h:
    ts = [t for ch, t in kids(h) if t]
    print("checkbox", any("更改安装位置" in t for t in ts))
    btn = next((ch for ch, t in kids(h) if t.startswith("下一步")), None)
    u.SendMessageW(btn, 0x00F5, 0, 0)
    time.sleep(1.6)
    ts2 = [t for ch, t in kids(h) if t]
    print("ready_page", any("准备安装" in t for t in ts2))
    print("dir_page", any("选择目标位置" in t for t in ts2))
    u.PostMessageW(h, 0x0010, 0, 0)
