import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
start = time.time()
hwnd = None
while time.time() - start < 40:
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, lparam):
        cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
        if cls.value == "TWizardForm" and u.IsWindowVisible(h):
            found.append(h)
        return True
    u.EnumWindows(cb, 0)
    if found:
        hwnd = found[0]; break
    time.sleep(0.5)
lines = [f"found={bool(hwnd)} after={time.time()-start:.1f}s exit={proc.poll()}"]
if hwnd:
    time.sleep(1.0)
    texts = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child(h, lparam):
        cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
        if cls.value == "TNewStaticText":
            n = u.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
            if buf.value.strip(): texts.append(buf.value)
        return True
    u.EnumChildWindows(hwnd, child, 0)
    for t in texts:
        if "升级安装" in t or "即将" in t:
            lines.append(repr(t))
    u.PostMessageW(hwnd, 0x0010, 0, 0)
time.sleep(1)
if proc.poll() is None:
    proc.terminate()
pathlib.Path("artifacts/qa/r67/wizard2.txt").write_text("\n".join(lines), encoding="utf-8")
print("done", lines[0])
