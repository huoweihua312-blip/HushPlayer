"""Global hotkeys via RegisterHotKey + WM_HOTKEY native event filtering."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

from ..core.logging_setup import get_logger

log = get_logger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

#: action -> (modifiers, virtual key, human readable)
DEFAULT_HOTKEYS: dict[str, tuple[int, int, str]] = {
    "play_pause": (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x20, "Ctrl+Alt+Space"),
    "next": (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x27, "Ctrl+Alt+Right"),
    "previous": (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x25, "Ctrl+Alt+Left"),
    "mute": (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x4D, "Ctrl+Alt+M"),
    "show_window": (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x48, "Ctrl+Alt+H"),
}


class GlobalHotkeys(QObject, QAbstractNativeEventFilter):
    """Registers a small set of system-wide shortcuts.

    Media keys themselves are handled by SMTC; these are *extra* shortcuts for
    users whose keyboard lacks media keys.
    """

    play_pause_requested = Signal()
    next_requested = Signal()
    previous_requested = Signal()
    mute_requested = Signal()
    show_window_requested = Signal()

    _ACTIONS = {
        "play_pause": "play_pause_requested",
        "next": "next_requested",
        "previous": "previous_requested",
        "mute": "mute_requested",
        "show_window": "show_window_requested",
    }

    def __init__(self, hwnd: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._hwnd = hwnd
        self._registered: dict[int, str] = {}
        self._enabled = False

    @property
    def available(self) -> bool:
        return bool(self._registered)

    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        if enabled and not self._enabled:
            self.register()
        elif not enabled and self._enabled:
            self.unregister()

    def register(self) -> None:
        if not self._hwnd:
            return
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        user32 = ctypes.windll.user32
        for index, (action, (mods, vk, _label)) in enumerate(DEFAULT_HOTKEYS.items(), start=101):
            if user32.RegisterHotKey(wintypes.HWND(self._hwnd), index, mods, vk):
                self._registered[index] = action
            else:
                log.info("全局快捷键注册失败：%s", DEFAULT_HOTKEYS[action][2])
        if self._registered and app is not None:
            app.installNativeEventFilter(self)
        self._enabled = bool(self._registered)
        if self._enabled:
            log.info("全局快捷键已启用：%d 个", len(self._registered))

    def unregister(self) -> None:
        from PySide6.QtCore import QCoreApplication

        user32 = ctypes.windll.user32
        for hotkey_id in list(self._registered):
            try:
                user32.UnregisterHotKey(wintypes.HWND(self._hwnd), hotkey_id)
            except Exception:
                pass
        self._registered.clear()
        self._enabled = False
        app = QCoreApplication.instance()
        if app is not None:
            try:
                app.removeNativeEventFilter(self)
            except Exception:
                pass

    def nativeEventFilter(self, event_type, message):  # noqa: N802, ANN001
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message != WM_HOTKEY:
            return False, 0
        action = self._registered.get(int(msg.wParam))
        if not action:
            return False, 0
        name = self._ACTIONS.get(action)
        if name:
            getattr(self, name).emit()
        return True, 0
