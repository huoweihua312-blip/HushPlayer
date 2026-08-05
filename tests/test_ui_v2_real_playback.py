from __future__ import annotations

import os
import json
import sys
import tempfile
import time
import unittest
import wave
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from app.core.app_paths import AppPaths
from app.services.library_repository import LibraryRepository
from app.services.production_playback_controller import ProductionPlaybackController
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.models.playback_state import RepeatMode
from app.ui_v2.models.track import Track
from app.ui_v2.startup import UiV2RuntimeServices, create_ui_v2_main_window


class _FakeDevice:
    def __init__(self, device_id: bytes = b"fixture", *, is_null: bool = False) -> None:
        self._device_id = device_id
        self._is_null = is_null

    def id(self) -> bytes:
        return self._device_id

    def description(self) -> str:
        return "Fixture Output"

    def isNull(self) -> bool:
        return self._is_null


class _FakeAudioOutput(QObject):
    mutedChanged = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._device = _FakeDevice()
        self._volume = 0.70
        self._muted = False

    def device(self):
        return self._device

    def setDevice(self, device) -> None:
        self._device = device

    def volume(self) -> float:
        return self._volume

    def setVolume(self, value: float) -> None:
        self._volume = float(value)

    def isMuted(self) -> bool:
        return self._muted

    def setMuted(self, value: bool) -> None:
        value = bool(value)
        if value != self._muted:
            self._muted = value
            self.mutedChanged.emit(value)


class _FakeMediaDevices(QObject):
    audioOutputsChanged = Signal()


class _FakeMediaPlayer(QObject):
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    playbackStateChanged = Signal(object)
    mediaStatusChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self) -> None:
        super().__init__()
        self._source = QUrl()
        self._position = 0
        self._state = QMediaPlayer.PlaybackState.StoppedState
        self._audio_output = None

    def setAudioOutput(self, output) -> None:
        self._audio_output = output

    def setSource(self, source: QUrl) -> None:
        self._source = QUrl(source)

    def source(self) -> QUrl:
        return QUrl(self._source)

    def setPosition(self, value: int) -> None:
        self._position = int(value)
        self.positionChanged.emit(self._position)

    def position(self) -> int:
        return self._position

    def play(self) -> None:
        self._set_state(QMediaPlayer.PlaybackState.PlayingState)

    def pause(self) -> None:
        self._set_state(QMediaPlayer.PlaybackState.PausedState)

    def stop(self) -> None:
        self._set_state(QMediaPlayer.PlaybackState.StoppedState)

    def errorString(self) -> str:
        return "fixture media error"

    def _set_state(self, value) -> None:
        if self._state != value:
            self._state = value
            self.playbackStateChanged.emit(value)


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 800)


def _track(track_id: str, path: Path, *, online: bool = False) -> Track:
    return Track(
        id=track_id,
        title=track_id,
        artist="Fixture Artist",
        album="Fixture Album",
        duration_ms=1_000,
        source_id="fixture" if online else "local",
        source_name="Fixture",
        source_type="online" if online else "local",
        added_at=datetime(2026, 8, 5),
        is_favorite=False,
        is_missing=False,
        is_loading=False,
        artwork_path=None,
        stable_identity=(f"remote:fixture:{track_id}" if online else f"local:{str(path).casefold()}"),
        local_path="" if online else str(path),
    )


class UiV2RealPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="hushplayer-v2-playback-")
        root = Path(self.temporary_directory.name)
        self.first_path = root / "first.wav"
        self.second_path = root / "second.wav"
        _write_wav(self.first_path)
        _write_wav(self.second_path)
        self.player = _FakeMediaPlayer()
        self.output = _FakeAudioOutput()
        self.controller = ProductionPlaybackController(
            media_player=self.player,
            audio_output=self.output,
            media_devices=_FakeMediaDevices(),
        )
        self.adapter = PlaybackAdapter(timer_enabled=False, controller=self.controller)
        self.first = _track("first", self.first_path)
        self.second = _track("second", self.second_path)

    def tearDown(self) -> None:
        self.controller.shutdown()
        self.temporary_directory.cleanup()

    def test_real_adapter_uses_one_controller_queue_and_local_wav_sources(self) -> None:
        self.adapter.set_queue((self.first, self.second))
        self.assertEqual(
            [track.id for track in self.adapter.queue_tracks],
            ["first", "second"],
        )
        self.assertEqual(len(self.controller.queue.items), 2)

        self.adapter.play_track("first")
        self.assertEqual(self.adapter.state.current_track, self.first)
        self.assertTrue(self.adapter.state.is_playing)
        self.assertEqual(Path(self.player.source().toLocalFile()), self.first_path)

        self.player.durationChanged.emit(1_000)
        self.adapter.seek(400)
        self.assertEqual(self.player.position(), 400)
        self.assertEqual(self.adapter.state.position_ms, 400)

        self.adapter.pause()
        self.assertFalse(self.adapter.state.is_playing)
        self.adapter.play_next()
        self.assertEqual(self.adapter.state.current_track, self.second)
        self.assertEqual(Path(self.player.source().toLocalFile()), self.second_path)

    def test_end_of_media_is_deduplicated_and_mode_state_follows_controller(self) -> None:
        self.adapter.set_queue((self.first, self.second))
        self.adapter.play_track("first")
        self.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertEqual(self.adapter.state.current_track, self.second)
        self.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertEqual(self.adapter.state.current_track, self.second)

        self.adapter.cycle_repeat_mode()
        self.assertEqual(self.adapter.state.repeat_mode, RepeatMode.ONE)
        self.assertEqual(self.controller.play_mode, "single_loop")
        self.adapter.cycle_repeat_mode()
        self.assertEqual(self.adapter.state.repeat_mode, RepeatMode.OFF)
        self.assertEqual(self.controller.play_mode, "sequence")
        self.adapter.toggle_shuffle()
        self.assertTrue(self.adapter.state.shuffle_enabled)
        self.assertEqual(self.controller.play_mode, "shuffle")

    def test_online_tracks_are_not_placed_in_the_formal_local_queue(self) -> None:
        online = _track("remote", self.first_path, online=True)
        errors: list[str] = []
        self.adapter.error_occurred.connect(errors.append)
        self.adapter.set_queue((online, self.first))
        self.assertEqual([track.id for track in self.adapter.queue_tracks], ["first"])
        self.adapter.play_track("remote")
        self.assertFalse(self.adapter.state.is_playing)
        self.assertEqual(errors, ["Online playback is not available in this version."])

    def test_missing_or_failed_local_media_does_not_leave_playing_state(self) -> None:
        missing = _track("missing", self.first_path.parent / "missing.wav")
        errors: list[str] = []
        self.adapter.error_occurred.connect(errors.append)
        self.adapter.set_queue((missing,))
        self.adapter.play_track("missing")
        self.assertFalse(self.adapter.state.is_playing)
        self.assertEqual(errors, ["The local audio file is unavailable."])

        self.adapter.set_queue((self.first,))
        self.adapter.play_track("first")
        self.assertTrue(self.adapter.state.is_playing)
        self.player.errorOccurred.emit(
            QMediaPlayer.Error.ResourceError,
            "fixture corruption",
        )
        self.assertFalse(self.adapter.state.is_playing)
        self.assertEqual(errors[-1], "fixture corruption")

    def test_volume_mute_and_audio_device_change_keep_position(self) -> None:
        self.adapter.set_queue((self.first,))
        self.adapter.play_track("first")
        self.player.durationChanged.emit(1_000)
        self.adapter.seek(550)
        self.adapter.set_volume(42)
        self.adapter.set_muted(True)
        self.assertEqual(self.adapter.state.volume, 42)
        self.assertTrue(self.adapter.state.is_muted)

        self.assertTrue(self.controller.apply_default_audio_output(_FakeDevice(b"usb")))
        self.assertEqual(self.player.position(), 550)
        self.assertEqual(self.adapter.state.position_ms, 550)

    def test_production_controller_owns_the_qt_backend_for_a_generated_wav(self) -> None:
        controller = ProductionPlaybackController()
        try:
            self.assertIsInstance(controller.media_player, QMediaPlayer)
            controller.set_queue((self.adapter._queue_item_from_track(self.first),))
            self.assertTrue(controller.play_item(self.first.stable_identity))
            self.assertEqual(
                Path(controller.media_player.source().toLocalFile()),
                self.first_path,
            )
        finally:
            controller.shutdown()

    def test_real_main_window_reuses_the_controller_for_player_bar_and_immersive(self) -> None:
        root = Path(self.temporary_directory.name)
        library_file = root / "library.json"
        playlists_file = root / "playlists.json"
        stats_file = root / "stats.json"
        remote_file = root / "remote_tracks.json"
        settings_file = root / "settings.json"
        library_file.write_text(
            json.dumps(
                [
                    {
                        "path": str(self.first_path),
                        "title": "first",
                        "artist": "Fixture Artist",
                        "album": "Fixture Album",
                        "duration": 1,
                        "added_at": 1,
                    },
                    {
                        "path": str(self.second_path),
                        "title": "second",
                        "artist": "Fixture Artist",
                        "album": "Fixture Album",
                        "duration": 1,
                        "added_at": 2,
                    },
                ]
            ),
            encoding="utf-8",
        )
        playlists_file.write_text(json.dumps({"liked": {"members": []}}), encoding="utf-8")
        stats_file.write_text("{}", encoding="utf-8")
        remote_file.write_text(json.dumps({"version": 1, "tracks": {}}), encoding="utf-8")
        settings_file.write_text(json.dumps({"appearance_mode": "dark", "volume": 65}), encoding="utf-8")
        services = UiV2RuntimeServices(
            paths=AppPaths.resolve(),
            settings_path=settings_file,
            repository=LibraryRepository(library_file, playlists_file, stats_file),
            remote_tracks=RemoteTrackStore(remote_file),
            playback_adapter=self.adapter,
            lyrics_adapter=LyricsAdapter(),
        )
        window = create_ui_v2_main_window(
            data_mode="real",
            services=services,
            initialize_storage=False,
        )
        try:
            deadline = time.monotonic() + 3.0
            while (
                window.real_library_adapter is not None
                and window.real_library_adapter.state == "loading"
                and time.monotonic() < deadline
            ):
                self.app.processEvents()
                time.sleep(0.005)
            self.assertEqual(window.real_library_adapter.state, "loaded")
            self.assertTrue(window.player_bar._transport_available)
            self.assertTrue(window.library_page.track_table._playback_enabled)
            tracks = window.library_collection.tracks()
            window._play_tracks(tracks, tracks[0].id)
            self.assertEqual(self.adapter.state.current_track.id, tracks[0].id)
            self.assertIs(window.player_bar.adapter, self.adapter)
            window.navigation_adapter.set_route("immersive_lyrics")
            self.app.processEvents()
            self.assertIs(window.immersive_shell.playback_adapter, self.adapter)
            self.assertIs(self.adapter.controller, self.controller)
        finally:
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
