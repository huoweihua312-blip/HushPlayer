"""Windows 集成层（SMTC / 任务栏 / 全局快捷键）的降级与开关行为。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hushplayer.core.settings import Settings
from hushplayer.services import smtc as smtc_module
from hushplayer.services.hotkeys import GlobalHotkeys
from hushplayer.services.integration import MediaIntegration
from hushplayer.services.taskbar import TaskbarProgress


class FakePlayer(QObject):
    track_changed = Signal(object)
    state_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.position = 0
        self.duration = 0
        self.current = None
        self.calls: list[str] = []

    def resume(self):
        self.calls.append("resume")

    def pause(self):
        self.calls.append("pause")

    def toggle(self):
        self.calls.append("toggle")

    def stop(self):
        self.calls.append("stop")

    def next(self):
        self.calls.append("next")

    def previous(self):
        self.calls.append("previous")

    def toggle_mute(self):
        self.calls.append("mute")

    def seek(self, value):
        self.calls.append(f"seek:{value}")


def test_smtc_degrades_without_projection(monkeypatch, qapp) -> None:
    def boom():
        raise ImportError("no winrt")

    monkeypatch.setattr(smtc_module, "_load_winrt", boom)
    service = smtc_module.SmtcService()
    assert service.available is False
    service.set_track(None)
    service.set_state("playing")
    service.set_position(1000)
    service.set_duration(2000)
    service.shutdown()


def test_hotkeys_without_hwnd_is_a_noop(qapp) -> None:
    hotkeys = GlobalHotkeys(0)
    hotkeys.set_enabled(True)
    assert hotkeys.available is False
    hotkeys.set_enabled(False)
    hotkeys.unregister()


def test_integration_forwards_player_state(monkeypatch, qapp, tmp_path) -> None:
    monkeypatch.setattr(smtc_module, "_load_winrt", lambda: (_ for _ in ()).throw(ImportError()))

    class DummyTaskbar(TaskbarProgress):
        def __init__(self) -> None:  # noqa: D401 - test double
            self.calls = []

        @property
        def available(self):
            return False

    monkeypatch.setattr("hushplayer.services.integration.TaskbarProgress", DummyTaskbar)
    settings = Settings()
    player = FakePlayer()
    integration = MediaIntegration(player, settings)

    class Track:
        title = "歌曲"
        artist = "歌手"
        album = "专辑"
        duration_ms = 1000

    player.track_changed.emit(Track())
    player.state_changed.emit("playing")
    player.duration_changed.emit(1000)
    player.position_changed.emit(400)
    integration.shutdown()


def test_integration_smtc_buttons_drive_player(monkeypatch, qapp) -> None:
    monkeypatch.setattr(smtc_module, "_load_winrt", lambda: (_ for _ in ()).throw(ImportError()))

    class DummyTaskbar(TaskbarProgress):
        def __init__(self) -> None:
            pass

        @property
        def available(self):
            return False

    monkeypatch.setattr("hushplayer.services.integration.TaskbarProgress", DummyTaskbar)
    settings = Settings()
    player = FakePlayer()
    integration = MediaIntegration(player, settings)
    integration.smtc.toggle_requested.emit()
    integration.smtc.next_requested.emit()
    integration.smtc.previous_requested.emit()
    integration.smtc.seek_requested.emit(5000)
    qapp.processEvents()
    assert "toggle" in player.calls
    assert "next" in player.calls
    assert "previous" in player.calls
    assert "seek:5000" in player.calls
    integration.shutdown()
