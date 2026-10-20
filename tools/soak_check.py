"""Soak:循环播放 + 页面/沉浸/主题切换，定期记录 RSS 与句柄数。

用法： .venv\\Scripts\\python.exe tools\\soak_check.py [分钟]
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("HUSHPLAYER_DATA_DIR", str(Path("artifacts/qa/soak_data").resolve()))
os.environ.setdefault("HUSHPLAYER_NO_CLOSE_PROMPT", "1")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.ui.context import ctx  # noqa: E402

MINUTES = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
LOG = Path("artifacts/qa/soak.log")
LOG.parent.mkdir(parents=True, exist_ok=True)


def rss_mb() -> float:
    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PMC()
    counters.cb = ctypes.sizeof(PMC)
    api = ctypes.windll.psapi.GetProcessMemoryInfo
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    api.restype = ctypes.c_int
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    api(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / (1024 * 1024)


def handles() -> int:
    count = ctypes.c_ulong(0)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    api = kernel.GetProcessHandleCount
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    api.restype = ctypes.c_int
    api(kernel.GetCurrentProcess(), ctypes.byref(count))
    return int(count.value)


def log(line: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


app = QApplication(sys.argv)
hush = HushApp(app)
hush.start()
win = ctx().window
win.show()

tracks = [p for p in Path("tests/fixtures/audio").rglob("*") if p.is_file()]
ctx().library.import_files([str(p) for p in tracks])
log(f"start tracks={len(tracks)} rss={rss_mb():.1f}MB handles={handles()}")

state = {"cycles": 0, "pages": ["home", "songs", "albums", "artists", "search", "lyrics"]}
start = time.monotonic()
deadline = start + MINUTES * 60


def step() -> None:
    try:
        _step()
    except Exception as exc:  # noqa: BLE001 - soak must keep running
        log(f"step error: {type(exc).__name__}: {exc}")
        if time.monotonic() < deadline:
            QTimer.singleShot(700, step)


def _step() -> None:
    if time.monotonic() >= deadline:
        log(f"done cycles={state['cycles']} rss={rss_mb():.1f}MB handles={handles()}")
        app.quit()
        return
    state["cycles"] += 1
    player = ctx().player
    page = state["pages"][state["cycles"] % len(state["pages"])]
    win.navigate(page)
    if state["cycles"] % 2 == 0:
        if player.queue.count == 0:
            songs = ctx().library.search_local("", limit=12)
            if songs:
                player.play_tracks(songs, 0)
        else:
            player.next()
    if state["cycles"] % 3 == 0:
        player.seek(player.position + 4000)
    if state["cycles"] % 7 == 0:
        win.toggle_desktop_lyrics()
    if state["cycles"] % 11 == 0:
        current = str(hush.settings.get("appearance.theme", "system"))
        hush.settings.set("appearance.theme", "light" if current == "dark" else "dark")
    if state["cycles"] % 15 == 0:
        log(f"cycle={state['cycles']} page={page} rss={rss_mb():.1f}MB handles={handles()}")
    QTimer.singleShot(700, step)


QTimer.singleShot(1200, step)
QTimer.singleShot(int(MINUTES * 60 * 1000) + 15000, app.quit)
app.exec()
hush.shutdown()
log(f"exit rss={rss_mb():.1f}MB handles={handles()}")
print("SOAK DONE", flush=True)
