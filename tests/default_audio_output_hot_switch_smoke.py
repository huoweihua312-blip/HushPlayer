from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


class FakeAudioDevice:
    def __init__(self, device_id: bytes, name: str, *, is_null: bool = False) -> None:
        self._device_id = device_id
        self._name = name
        self._is_null = is_null

    def id(self) -> bytes:
        return self._device_id

    def description(self) -> str:
        return self._name

    def isNull(self) -> bool:
        return self._is_null


class FakeAudioOutput:
    def __init__(self, device: FakeAudioDevice) -> None:
        self._device = device
        self.set_device_calls: list[FakeAudioDevice] = []
        self.volume = 0.65
        self.muted = False

    def device(self) -> FakeAudioDevice:
        return self._device

    def setDevice(self, device: FakeAudioDevice) -> None:
        self._device = device
        self.set_device_calls.append(device)


def process_events_for(app: QApplication, duration_ms: int) -> None:
    deadline = time.monotonic() + duration_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def test_device_application_rules() -> None:
    old_device = FakeAudioDevice(b"speaker", "Speakers")
    same_device = FakeAudioDevice(b"speaker", "Speakers (default)")
    new_device = FakeAudioDevice(b"usb-headset", "USB Headset")
    null_device = FakeAudioDevice(b"", "", is_null=True)
    audio_output = FakeAudioOutput(old_device)
    owner = SimpleNamespace(audio_output=audio_output)
    owner.audio_device_name = MainWindow.audio_device_name

    assert not MainWindow.apply_default_audio_output(owner, same_device)
    assert audio_output.set_device_calls == []

    assert not MainWindow.apply_default_audio_output(owner, null_device)
    assert audio_output.device() is old_device
    assert audio_output.set_device_calls == []

    before_state = (audio_output.volume, audio_output.muted)
    assert MainWindow.apply_default_audio_output(owner, new_device)
    assert audio_output.device() is new_device
    assert audio_output.set_device_calls == [new_device]
    assert (audio_output.volume, audio_output.muted) == before_state


def test_main_window_lifetime_startup_and_debounce(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_sync = MainWindow.sync_default_audio_output
    sync_calls: list[MainWindow] = []
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    MainWindow.sync_default_audio_output = lambda self: sync_calls.append(self)
    try:
        window = MainWindow()
        assert sync_calls == [window]
        assert window.media_devices.parent() is window
        assert window.default_audio_output_sync_timer.parent() is window
        assert window.default_audio_output_sync_timer.isSingleShot()
        assert window.default_audio_output_sync_timer.interval() == 250

        window.schedule_default_audio_output_sync()
        process_events_for(app, 160)
        window.schedule_default_audio_output_sync()
        process_events_for(app, 160)
        assert sync_calls == [window]
        process_events_for(app, 160)
        assert sync_calls == [window, window]

        window.media_player.stop()
        window.online_source_client.stop()
        window.deleteLater()
        app.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        MainWindow.sync_default_audio_output = original_sync


def test_single_player_and_audio_output_initialization() -> None:
    source = (PROJECT_ROOT / "app" / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert source.count("self.media_player = QMediaPlayer()") == 1
    assert source.count("self.audio_output = QAudioOutput(") == 1
    assert source.count("self.media_player.setAudioOutput(self.audio_output)") == 1
    assert "self.audio_output.setDevice(default_device)" in source
    assert "self.media_devices = QMediaDevices(self)" in source


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="hushplayer-audio-device-") as temp_dir:
        root = Path(temp_dir)
        os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
        os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
        os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
        test_device_application_rules()
        test_main_window_lifetime_startup_and_debounce(app)
        test_single_player_and_audio_output_initialization()
    print("default audio output hot switch smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
