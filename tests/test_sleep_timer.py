"""睡眠定时：到点暂停，并把设置复位为关闭。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEventLoop, QTimer

from hushplayer.app import HushApp


class FakeSettings:
    def __init__(self) -> None:
        self.values = {"playback.sleep_timer_minutes": 15}

    def set(self, key: str, value, save: bool = True) -> None:
        self.values[key] = value

    def get(self, key: str, default=None):
        return self.values.get(key, default)


class FakePlayer:
    def __init__(self) -> None:
        self.paused = 0

    def pause(self) -> None:
        self.paused += 1


class FakeApp(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.settings = FakeSettings()
        self.player = FakePlayer()
        self.window = None
        # Bind the real slot so the timer can call it without a full HushApp.
        self._on_sleep_timer = HushApp._on_sleep_timer.__get__(self, FakeApp)


def pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_timer_pauses_and_resets(qapp) -> None:
    fake = FakeApp()
    HushApp._arm_sleep_timer(fake, 0.01)  # 600 ms
    assert fake._sleep_timer.isActive()
    pump(900)
    assert fake.player.paused == 1
    assert fake.settings.get("playback.sleep_timer_minutes") == 0


def test_zero_disables_timer(qapp) -> None:
    fake = FakeApp()
    HushApp._arm_sleep_timer(fake, 0.01)
    HushApp._arm_sleep_timer(fake, 0)
    assert not fake._sleep_timer.isActive()
    pump(700)
    assert fake.player.paused == 0
