"""单实例保护：命名互斥体互斥 + 本地套接字激活。"""

from __future__ import annotations

import os
import uuid

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from hushplayer.core import single_instance
from hushplayer.core.single_instance import SingleInstance


@pytest.fixture(autouse=True)
def isolated_single_instance(monkeypatch, tmp_path):
    """Do not fight a real HushPlayer that the user has open right now.

    The guard keys off a machine-wide named mutex; without isolation, running
    the app while the test suite executes makes ``try_lock()`` fail for the
    first test instance. Each test gets its own mutex and request file.
    """
    token = uuid.uuid4().hex
    monkeypatch.setenv("HUSHPLAYER_MUTEX_SUFFIX", f"-test-{token}")
    monkeypatch.setattr(single_instance, "REQUEST_NAME", f"activate-{token}.request")
    monkeypatch.setattr(single_instance, "request_file", lambda: tmp_path / "activate.request")
    yield


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
