"""Per-source success/failure counters used to spot unhealthy plugins."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("online.health")

_LOCK = threading.Lock()


def health_file() -> Path:
    return paths.data_dir() / "source_health.json"


def _read() -> dict[str, dict[str, Any]]:
    path = health_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
    except FileNotFoundError:
        return {}
    except Exception:
        log.debug("cannot read source health", exc_info=True)
    return {}


def _write(data: dict[str, dict[str, Any]]) -> None:
    path = health_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        log.debug("cannot persist source health", exc_info=True)


def record_ok(source_id: str) -> None:
    if not source_id:
        return
    with _LOCK:
        data = _read()
        entry = data.setdefault(source_id, {"ok": 0, "fail": 0})
        entry["ok"] = int(entry.get("ok", 0)) + 1
        entry["last_ok"] = time.time()
        entry.pop("last_error", None)
        _write(data)


def record_fail(source_id: str, error: str = "") -> None:
    if not source_id:
        return
    with _LOCK:
        data = _read()
        entry = data.setdefault(source_id, {"ok": 0, "fail": 0})
        entry["fail"] = int(entry.get("fail", 0)) + 1
        entry["last_fail"] = time.time()
        entry["last_error"] = (error or "")[:200]
        _write(data)


def stats(source_id: str) -> dict[str, Any]:
    return _read().get(source_id, {})


def all_stats() -> dict[str, dict[str, Any]]:
    return _read()


def looks_broken(source_id: str, *, window_s: float = 1800.0) -> bool:
    """Recent, repeated failures with no later success.

    Used to skip a resolve attempt we already know will 404 (a stale plugin),
    which is what made switching tracks feel slow.
    """
    entry = stats(source_id)
    if not entry:
        return False
    fail = int(entry.get("fail", 0))
    last_fail = float(entry.get("last_fail") or 0)
    last_ok = float(entry.get("last_ok") or 0)
    if fail < 2 or last_fail <= last_ok:
        return False
    return (time.time() - last_fail) < window_s


def summary(source_id: str) -> str:
    """Short human text for the settings list; empty when nothing recorded."""
    entry = stats(source_id)
    ok = int(entry.get("ok", 0))
    fail = int(entry.get("fail", 0))
    total = ok + fail
    if not total:
        return ""
    if fail and not ok:
        return "最近解析全部失败"
    ratio = round(ok * 100 / total)
    text = f"解析成功率 {ratio}%"
    if entry.get("last_error") and fail:
        text += " · 最近有失败"
    return text


def reset() -> None:
    with _LOCK:
        _write({})
