"""单实例保护：命名互斥体互斥 + 本地套接字激活。"""

from __future__ import annotations

import os

from PySide6.QtCore import QEventLoop, QTimer

from hushplayer.core.single_instance import SingleInstance


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_second_instance_cannot_lock(qapp) -> None:
    os.environ.pop("HUSHPLAYER_ALLOW_MULTI", None)
    first = SingleInstance()
    second = SingleInstance()
    try:
        assert first.try_lock() is True
        assert second.try_lock() is False
    finally:
        second.close()
        first.close()


def test_activate_signal_is_delivered(qapp) -> None:
    first = SingleInstance()
    fired: list[int] = []
    try:
        assert first.try_lock() is True
        first.activate.connect(lambda: fired.append(1))
        assert first.notify_existing() is True
        _pump(600)
        assert fired, "主实例应收到激活请求"
    finally:
        first.close()


def test_multi_instance_env_bypasses_guard(qapp, monkeypatch) -> None:
    monkeypatch.setenv("HUSHPLAYER_ALLOW_MULTI", "1")
    guard = SingleInstance()
    try:
        assert guard.enabled is False
        assert guard.try_lock() is True
    finally:
        guard.close()
