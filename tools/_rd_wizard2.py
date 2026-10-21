import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])

def all_windows(timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        found = []
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if u.IsWindowVisible(hwnd):
                n = u.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(hwnd, buf, n + 1)
                if "HushPlayer" in buf.value and "安装" in buf.value:
                    found.append(hwnd)
            return True
        u.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.5)
    return None

hwnd = all_windows()
out = [f"WINDOW {bool(hwnd)}"]
def snapshot():
    texts, buttons, edits = [], [], []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child(h, lparam):
        cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
        if cls.value == "Static" and buf.value.strip(): texts.append(buf.value)
        if cls.value == "Button" and buf.value.strip(): buttons.append((h, buf.value))
        if cls.value == "Edit": edits.append(buf.value)
        return True
    u.EnumChildWindows(hwnd, child, 0)
    return texts, buttons, edits

if hwnd:
    time.sleep(1.0)
    texts, buttons, edits = snapshot()
    out.append("WELCOME=" + " | ".join(t for t in texts if "升级安装" in t))
    out.append("BUTTONS=" + " | ".join(t for _, t in buttons))
    nxt = next((h for h, t in buttons if t.startswith("下一步")), None)
    if nxt:
        u.SendMessageW(nxt, 0x00F5, 0, 0)
        time.sleep(1.5)
        texts2, buttons2, edits2 = snapshot()
        out.append("DIR_PAGE=" + " | ".join(t for t in texts2 if "文件夹" in t))
        out.append("EDITS=" + " ;; ".join(edits2))
    u.PostMessageW(hwnd, 0x0010, 0, 0)
pathlib.Path("artifacts/qa/r67/wizard.txt").write_text("\n".join(out), encoding="utf-8")
time.sleep(1)
proc.terminate()
print("done")
