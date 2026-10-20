"""Honest tray-registration probe.

``QSystemTrayIcon`` never tells us whether the shell accepted the icon, so we
ask the shell ourselves with the same Win32 call Qt uses internally.  This also
explains *why* registration failed: a low-integrity process (for example files
that inherited a ``Low Mandatory Level`` label) is refused with
``ERROR_ACCESS_DENIED``.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from ..core.logging_setup import get_logger

log = get_logger(__name__)

NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
WM_APP = 0x8000
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


def probe_registration(hwnd: int, icon_path: str | None = None) -> tuple[bool, int]:
    """Try to add (and immediately remove) a tray icon.

    Returns ``(ok, winerror)`` where ``winerror`` is the Win32 error raised by
    the shell (0 when the call succeeded).
    """
    if not hwnd:
        return False, 0
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    hicon = 0
    if icon_path:
        hicon = user32.LoadImageW(
            None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )
    if not hicon:
        hicon = user32.LoadIconW(None, ctypes.c_wchar_p(32512))  # IDI_APPLICATION

    data = _NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
    data.hWnd = hwnd
    data.uID = 0x4850
    data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    data.uCallbackMessage = WM_APP + 0x51
    data.hIcon = hicon
    data.szTip = "HushPlayer tray probe"

    ctypes.set_last_error(0)
    ok = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)))
    error = 0 if ok else int(ctypes.get_last_error() or 0)
    if ok:
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
    return ok, error


def describe(error: int) -> str:
    if error == 5:
        return (
            "系统拒绝注册托盘图标（WinError 5：拒绝访问）——通常是程序文件带有 "
            "Low 完整性标签，把程序放到普通目录（如桌面或 AppData）后重试"
        )
    if error:
        return f"系统拒绝注册托盘图标（WinError {error}）"
    return "未知原因"
