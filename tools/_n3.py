import ctypes, time, subprocess, pathlib
from ctypes import wintypes
u = ctypes.windll.user32
proc = subprocess.Popen([r"F:\HushPlayerBuild\out\HushPlayer-1.1.15-setup.exe"])
time.sleep(12)
rows = []
@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, lparam):
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    cls = ctypes.create_unicode_buffer(128); u.GetClassNameW(h, cls, 128)
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
    p = None
    try:
        import psutil
        p = psutil.Process(pid.value).name()
    except Exception:
        p = "?"
    rows.append(f"pid={pid.value} {p} vis={bool(u.IsWindowVisible(h))} {cls.value} {buf.value!r}")
    return True
u.EnumWindows(cb, 0)
sel = [r for r in rows if "setup" in r.lower() or "is-" in r or "Hush" in r or "安装" in r]
pathlib.Path("artifacts/qa/r67/wins2.txt").write_text("\n".join(sel) or "\n".join(rows[:40]), encoding="utf-8")
print("proc_alive", proc.poll() is None, "matched", len(sel))
