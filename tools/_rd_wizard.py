import ctypes, time, sys
from ctypes import wintypes
u = ctypes.windll.user32
setup = r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"
import subprocess
proc = subprocess.Popen([setup])

def find_window(title_part, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        found = []
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
                if title_part in buf.value:
                    found.append(hwnd)
            return True
        u.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.4)
    return None

hwnd = find_window("安装 - HushPlayer")
print("WINDOW", bool(hwnd))
time.sleep(1.5)
texts, buttons, edits = [], [], []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def child(h, lparam):
    cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
    if cls.value == "Static" and buf.value.strip(): texts.append(buf.value)
    if cls.value == "Button" and buf.value.strip(): buttons.append((h, buf.value))
    if cls.value == "Edit" and buf.value.strip(): edits.append(buf.value)
    return True
u.EnumChildWindows(hwnd, child, 0)
print("WELCOME", [t for t in texts if "升级安装" in t][:1])
next_btn = next((h for h, t in buttons if t.startswith("下一步")), None)
print("NEXT", bool(next_btn))
if next_btn:
    u.SendMessageW(next_btn, 0x00F5, 0, 0)  # BM_CLICK
    time.sleep(1.5)
    edits.clear(); texts.clear()
    u.EnumChildWindows(hwnd, child, 0)
    print("PAGE_TEXT", [t for t in texts if "文件夹" in t][:2])
    print("EDITS", edits)
u.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
time.sleep(0.5)
if proc.poll() is None:
    proc.terminate()
