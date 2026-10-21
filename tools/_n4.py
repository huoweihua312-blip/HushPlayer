import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
k = ctypes.windll.kernel32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
time.sleep(18)
PROCESS_QUERY_LIMITED = 0x1000
rows = []
def image(pid):
    h = k.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h: return ""
    buf = ctypes.create_unicode_buffer(1024); size = wintypes.DWORD(1024)
    ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    k.CloseHandle(h)
    return buf.value if ok else ""
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, lparam):
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    exe = image(pid.value)
    if "HushPlayer-1.1.15" in exe or "\\is-" in exe:
        cls = ctypes.create_unicode_buffer(128); u.GetClassNameW(h, cls, 128)
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
        rows.append(f"pid={pid.value} vis={bool(u.IsWindowVisible(h))} {cls.value} {buf.value!r}")
    return True
u.EnumWindows(cb, 0)
pathlib.Path("artifacts/qa/r67/wins3.txt").write_text("\n".join(rows) or "NO_WINDOWS", encoding="utf-8")
print("alive", proc.poll() is None, "rows", len(rows))
