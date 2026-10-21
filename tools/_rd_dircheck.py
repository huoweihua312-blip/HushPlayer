import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
SETUP = r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"

def find_wizard(timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        found = []
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(hwnd, cls, 64)
            if cls.value == "TWizardForm" and u.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        u.EnumWindows(cb, 0)
        if found: return found[0]
        time.sleep(0.5)
    return None

def children(hwnd):
    result = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, lparam):
        cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
        result.append((h, cls.value, buf.value))
        return True
    u.EnumChildWindows(hwnd, cb, 0)
    return result

lines = []
def run(step, click_next):
    proc = subprocess.Popen([SETUP])
    hwnd = find_wizard()
    lines.append(f"[{step}] window={bool(hwnd)}")
    if not hwnd:
        proc.terminate(); return
    time.sleep(1.0)
    nodes = children(hwnd)
    welcome = [t for _, c, t in nodes if c == "TNewStaticText" and "升级安装" in t]
    edits = [t for _, c, t in nodes if c == "TNewEdit"]
    lines.append(f"[{step}] welcome={welcome[0].splitlines()[-1] if welcome else ''!r}")
    lines.append(f"[{step}] edits_before={edits}")
    if click_next:
        btn = next((h for h, c, t in nodes if c == "TNewButton" and t.startswith("下一步")), None)
        if btn:
            u.SendMessageW(btn, 0x00F5, 0, 0)
            time.sleep(1.5)
            nodes2 = children(hwnd)
            edits2 = [t for _, c, t in nodes2 if c == "TNewEdit"]
            page = [t for _, c, t in nodes2 if c == "TNewStaticText" and "文件夹" in t]
            lines.append(f"[{step}] dir_page={page[0].splitlines()[0] if page else ''!r}")
            lines.append(f"[{step}] edits_after={edits2}")
        else:
            lines.append(f"[{step}] next_button_missing")
    u.PostMessageW(hwnd, 0x0010, 0, 0)
    time.sleep(1.0)
    proc.terminate()

run("with_key", True)
pathlib.Path("artifacts/qa/r67/dircheck.txt").write_text("\n".join(lines), encoding="utf-8")
print("done")
