"""单实例保护：第二次启动时激活已有窗口，而不是再开一个播放器。

实现分两层，都不写注册表、不需要管理员权限：

* **命名内核互斥体**（``Local\\<APP_ID>.mutex``）判定主实例，进程崩溃后由系统自动回收；
* **激活请求文件**（数据目录下的 ``activate.request``）把「请置前」传给主实例，
  主实例用轻量定时器轮询该文件的修改时间，收到后发送 :attr:`SingleInstance.activate`。

相比 QLocalSocket，这条链路在 Windows 上不依赖管道时序，跨进程与同进程都稳定。
设置 ``HUSHPLAYER_ALLOW_MULTI=1`` 可禁用该保护（便于开发时同时开多个实例）。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .logging_setup import get_logger
from .paths import data_dir
from ..version import APP_ID

log = get_logger("core.single_instance")

MUTEX_NAME = f"Local\\{APP_ID}.mutex"
REQUEST_NAME = "activate.request"
_POLL_MS = 400
_ERROR_ALREADY_EXISTS = 183


def request_file() -> Path:
    return data_dir() / REQUEST_NAME


class SingleInstance(QObject):
    """``try_lock()`` 成功表示本进程是主实例；失败时用 ``notify_existing()`` 唤醒它。"""

    activate = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mutex = None
        self._seen = 0.0
        self._timer: QTimer | None = None
        self._enabled = os.environ.get("HUSHPLAYER_ALLOW_MULTI", "").strip() not in {"1", "true", "yes"}

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------ mutex
    def _acquire_mutex(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:  # pragma: no cover - 非 Windows
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            log.warning("创建单实例互斥体失败，本轮允许多开")
            return True
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._mutex = handle
        return True

    def try_lock(self) -> bool:
        if not self._enabled:
            return True
        if not self._acquire_mutex():
            log.info("检测到已有 HushPlayer 实例正在运行")
            return False
        path = request_file()
        try:
            self._seen = path.stat().st_mtime
        except OSError:
            self._seen = 0.0
        timer = QTimer(self)
        timer.setInterval(_POLL_MS)
        timer.timeout.connect(self._poll_request)
        timer.start()
        self._timer = timer
        return True

    # ----------------------------------------------------------------- notify
    def notify_existing(self) -> bool:
        path = request_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{os.getpid()} {time.time():.3f}", encoding="utf-8")
        except OSError as exc:
            log.warning("无法写入激活请求：%s", exc)
            return False
        return True

    def _poll_request(self) -> None:
        path = request_file()
        try:
            stamp = path.stat().st_mtime
        except OSError:
            return
        if stamp <= self._seen:
            return
        self._seen = stamp
        try:
            path.unlink()
        except OSError:
            pass
        log.info("收到第二个实例的激活请求")
        self.activate.emit()

    def close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._mutex is not None:
            try:
                import ctypes

                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._mutex)
            except OSError:
                pass
            self._mutex = None
