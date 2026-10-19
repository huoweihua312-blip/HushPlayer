"""Minimal ITaskbarList3 wrapper (progress + thumbnail tooltip).

Implemented with raw ctypes COM calls so the app keeps its small dependency
footprint.  Any failure (no COM, no taskbar, older Windows) is non-fatal.
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import POINTER, byref, c_long, c_ulonglong, c_void_p
from ctypes import wintypes

from ..core.logging_setup import get_logger

log = get_logger(__name__)

CLSID_TASKBAR = uuid.UUID("{56FDF344-FD6D-11d0-958A-006097C9A090}")
IID_TASKBAR3 = uuid.UUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84}")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: uuid.UUID) -> _GUID:
    return _GUID(
        value.time_low,
        value.time_mid,
        value.time_hi_version,
        (ctypes.c_ubyte * 8)(*value.bytes[8:]),
    )


TBPF_NOPROGRESS = 0
TBPF_INDETERMINATE = 1
TBPF_NORMAL = 2
TBPF_ERROR = 4
TBPF_PAUSED = 8


class TaskbarProgress:
    """Thin wrapper around a taskbar button's progress indicator."""

    def __init__(self) -> None:
        self._ptr: c_void_p | None = None
        try:
            self._ptr = self._create()
        except Exception as exc:  # pragma: no cover - platform dependent
            log.info("任务栏进度不可用：%s", exc)
            self._ptr = None
        if self._ptr:
            log.info("任务栏进度已启用")

    @property
    def available(self) -> bool:
        return bool(self._ptr)

    def _create(self) -> c_void_p:
        ole32 = ctypes.windll.ole32
        ptr = c_void_p()
        clsid, iid = _guid(CLSID_TASKBAR), _guid(IID_TASKBAR3)
        hr = ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(ptr))
        if hr != 0:
            raise OSError(f"CoCreateInstance(ITaskbarList3) failed: 0x{hr & 0xFFFFFFFF:08X}")
        vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p)))[0]
        init = ctypes.WINFUNCTYPE(c_long, c_void_p)(vtable[3])
        init(ptr)
        return ptr

    def _call(self, index: int):  # noqa: ANN202 - ctypes signature factory
        vtable = ctypes.cast(self._ptr, POINTER(POINTER(c_void_p)))[0]
        return vtable[index]

    def set_visible(self, hwnd: int) -> bool:
        """HrInit is required once per window before progress can be shown."""
        if not self._ptr or not hwnd:
            return False
        try:
            init = ctypes.WINFUNCTYPE(c_long, c_void_p)(self._call(3))
            init(self._ptr)
            return True
        except Exception:
            return False

    def clear(self, hwnd: int) -> None:
        if not self._ptr or not hwnd:
            return
        try:
            set_state = ctypes.WINFUNCTYPE(c_long, c_void_p, c_void_p, ctypes.c_int)(self._call(10))
            set_state(self._ptr, c_void_p(hwnd), TBPF_NOPROGRESS)
        except Exception:
            pass

    def set_progress(self, hwnd: int, value: float) -> None:
        if not self._ptr or not hwnd:
            return
        value = max(0.0, min(1.0, value))
        try:
            set_value = ctypes.WINFUNCTYPE(c_long, c_void_p, c_void_p, c_ulonglong, c_ulonglong)(
                self._call(9)
            )
            set_state = ctypes.WINFUNCTYPE(c_long, c_void_p, c_void_p, ctypes.c_int)(self._call(10))
            set_value(self._ptr, c_void_p(hwnd), int(value * 1000), 1000)
            set_state(self._ptr, c_void_p(hwnd), TBPF_NORMAL if value > 0 else TBPF_NOPROGRESS)
        except Exception:
            pass

    def set_tooltip(self, hwnd: int, text: str) -> None:
        if not self._ptr or not hwnd:
            return
        try:
            set_tooltip = ctypes.WINFUNCTYPE(c_long, c_void_p, c_void_p, wintypes.LPCWSTR)(self._call(19))
            set_tooltip(self._ptr, c_void_p(hwnd), text[:255])
        except Exception:
            pass

    def release(self) -> None:
        self._ptr = None
