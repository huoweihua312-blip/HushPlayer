from __future__ import annotations

import os
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from app.services.online_media_resolver import OnlineMediaResolver
from app.services.production_playback_controller import ProductionPlaybackController
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.immersive_controls import ImmersiveControls


class _FakeAudioOutput(QObject):
    mutedChanged = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._volume = 0.65
        self._muted = False

    def device(self):
        return _FakeDevice()

    def setDevice(self, _device) -> None:
        return None

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


class _FakeDevice:
    def id(self) -> bytes:
        return b"q5b1-fixture"

    def description(self) -> str:
        return "Q5B1 Fixture Output"

    def isNull(self) -> bool:
        return False


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
        self._seekable = True

    def setAudioOutput(self, _output) -> None:
        return None

    def setSource(self, source: QUrl) -> None:
        self._source = QUrl(source)

    def source(self) -> QUrl:
        return QUrl(self._source)

    def setPosition(self, value: int) -> None:
        self._position = int(value)
        self.positionChanged.emit(self._position)

    def position(self) -> int:
        return self._position

    def isSeekable(self) -> bool:
        return self._seekable

    def play(self) -> None:
        self._set_state(QMediaPlayer.PlaybackState.PlayingState)

    def pause(self) -> None:
        self._set_state(QMediaPlayer.PlaybackState.PausedState)

    def stop(self) -> None:
        self._set_state(QMediaPlayer.PlaybackState.StoppedState)

    def errorString(self) -> str:
        return "Q5B1 fixture media error"

    def _set_state(self, value) -> None:
        if self._state != value:
            self._state = value
            self.playbackStateChanged.emit(value)


class _FakeOnlineSourceClient(QObject):
    playbackResolved = Signal(int, str, dict)
    requestFailed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.next_request_id = 1
        self.requests: dict[int, tuple[str, dict]] = {}
        self.cancelled: list[int] = []

    def resolve_playback(self, source_id: str, track: dict) -> int:
        request_id = self.next_request_id
        self.next_request_id += 1
        self.requests[request_id] = (source_id, dict(track))
        return request_id

    def cancel_request(self, request_id: int) -> None:
        self.cancelled.append(int(request_id))

    def resolve(self, request_id: int, url: str = "https://fixture.invalid/audio.mp3") -> None:
        source_id, _track = self.requests[request_id]
        self.playbackResolved.emit(request_id, source_id, {"url": url})

    def fail(self, request_id: int, message: str = "网络暂不可用") -> None:
        self.requestFailed.emit(request_id, "resolvePlayback", message)


class _FakeAudioCache:
    def __init__(self) -> None:
        self.record: dict | None = None
        self.started: list[tuple[object, dict]] = []

    def valid_cache(self, _value, *, touch: bool = True) -> dict | None:
        return dict(self.record) if isinstance(self.record, dict) else None

    def start_cache(self, value, resolution: dict) -> bool:
        self.started.append((value, dict(resolution)))
        return True


def _remote_track(track_id: str, *, source_id: str = "fixture") -> Track:
    identity = f"remote:{source_id}:{track_id}"
    return Track(
        id=track_id,
        title=f"Remote {track_id}",
        artist="Q5B1 Artist",
        album="Q5B1 Album",
        duration_ms=1_000,
        source_id=source_id,
        source_name="Fixture Source",
        source_type="online",
        added_at=datetime(2026, 8, 9),
        is_favorite=False,
        is_missing=True,
        is_loading=False,
        artwork_path=None,
        stable_identity=identity,
        availability="available",
        remote_identity=identity,
        remote_track_id=track_id,
        remote_payload={"id": track_id, "sourceId": source_id, "fixture": True},
    )


class OnlinePlaybackQ5B1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="hushplayer-q5b1-")
        self.local_path = Path(self.temporary_directory.name) / "local.wav"
        self.local_path.write_bytes(b"fixture")
        self.client = _FakeOnlineSourceClient()
        self.cache = _FakeAudioCache()
        self.catalog = [
            {
                "id": "fixture",
                "selectable": True,
                "capabilities": {"search": True, "playback": True},
            }
        ]
        self.resolver = OnlineMediaResolver(
            self.client,
            source_catalog_provider=lambda: self.catalog,
            source_catalog_loaded=lambda: True,
        )
        self.player = _FakeMediaPlayer()
        self.controller = ProductionPlaybackController(
            media_player=self.player,
            audio_output=_FakeAudioOutput(),
            media_devices=_FakeMediaDevices(),
            online_resolver=self.resolver,
            online_audio_cache=self.cache,
            online_cache_allowed=lambda _media_item: True,
        )
        self.adapter = PlaybackAdapter(timer_enabled=False, controller=self.controller)

    def tearDown(self) -> None:
        self.controller.shutdown()
        self.resolver.shutdown()
        self.temporary_directory.cleanup()

    def _process_events(self) -> None:
        self.app.processEvents()

    def _local_track(self) -> Track:
        return Track(
            id="local",
            title="Local",
            artist="Local Artist",
            album="Local Album",
            duration_ms=1_000,
            source_id="local",
            source_name="本地音乐",
            source_type="local",
            added_at=datetime(2026, 8, 9),
            is_favorite=False,
            is_missing=False,
            is_loading=False,
            artwork_path=None,
            stable_identity=f"local:{str(self.local_path).casefold()}",
            local_path=str(self.local_path),
        )

    def test_resolve_plays_remote_media_with_one_existing_player(self) -> None:
        remote = _remote_track("one")
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)

        self.assertEqual(self.controller.playback_status, "resolving")
        self.assertFalse(self.controller.is_playing)
        self.assertEqual(len(self.client.requests), 1)
        request_id, (source_id, payload) = next(iter(self.client.requests.items()))
        self.assertEqual(source_id, "fixture")
        self.assertEqual(payload["remoteStableId"], remote.stable_identity)

        self.client.resolve(request_id)
        self.assertTrue(self.controller.is_playing)
        self.assertEqual(self.controller.playback_status, "playing")
        self.assertEqual(self.player.source().toString(), "https://fixture.invalid/audio.mp3")
        self.assertEqual(self.controller.current_item.stable_identity, remote.stable_identity)
        self.assertTrue(self.controller.seek(400))
        self.assertEqual(self.player.position(), 400)
        self.controller.pause()
        self.assertEqual(self.controller.playback_status, "paused")
        self.assertTrue(self.controller.play())

    def test_immersive_mute_button_controls_shared_output_and_restores_zero_volume(self) -> None:
        controls = ImmersiveControls(get_theme("dark"))
        controls.bind_playback(self.adapter)
        self.adapter.set_volume(68)

        controls.volume_button.click()
        self.assertTrue(self.controller.is_muted)
        self.assertTrue(self.adapter.state.is_muted)
        self.assertEqual(controls.volume_button.toolTip(), "取消静音")

        controls.volume_button.click()
        self.assertFalse(self.controller.is_muted)
        self.assertFalse(self.adapter.state.is_muted)

        self.adapter.set_volume(0)
        controls.volume_button.click()
        self.assertFalse(self.controller.is_muted)
        self.assertEqual(self.controller.volume, 68)
        self.assertEqual(self.adapter.state.volume, 68)

    def test_complete_cache_hit_skips_online_resolve(self) -> None:
        remote = _remote_track("cached")
        self.cache.record = {
            "status": "complete",
            "cache_key": "cache-hit",
            "local_path": str(self.local_path),
            "file_size": self.local_path.stat().st_size,
        }
        self.adapter.set_queue((remote,))

        self.adapter.play_track(remote.id)

        self.assertEqual(self.client.requests, {})
        self.assertEqual(Path(self.player.source().toLocalFile()), self.local_path)
        self.assertTrue(self.controller.is_playing)
        self.assertEqual(self.controller._online_cache_key, "cache-hit")

    def test_resolved_remote_starts_policy_allowed_cache(self) -> None:
        remote = _remote_track("cache-after-resolve")
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)
        request_id = next(iter(self.client.requests))

        self.client.resolve(request_id)

        self.assertEqual(len(self.cache.started), 1)
        cached_media, resolution = self.cache.started[0]
        self.assertEqual(cached_media.stable_identity, remote.stable_identity)
        self.assertEqual(resolution["url"], "https://fixture.invalid/audio.mp3")

    def test_invalid_remote_media_refreshes_once_then_stops_retrying(self) -> None:
        remote = _remote_track("recover-once")
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)
        first_request = next(iter(self.client.requests))
        self.client.resolve(first_request)

        self.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.InvalidMedia)

        self.assertEqual(self.controller.playback_status, "resolving")
        self.assertEqual(len(self.client.requests), 2)
        second_request = max(self.client.requests)
        self.client.resolve(second_request)
        self.assertTrue(self.controller.is_playing)

        self.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.InvalidMedia)

        self.assertEqual(len(self.client.requests), 2)
        self.assertEqual(self.controller.playback_status, "error")

    def test_stale_invalid_media_during_initial_resolve_does_not_fail(self) -> None:
        remote = _remote_track("initial-invalid")
        errors: list[str] = []
        self.controller.error_occurred.connect(errors.append)
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)

        self.player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.InvalidMedia)

        self.assertEqual(self.controller.playback_status, "resolving")
        self.assertEqual(len(self.client.requests), 1)
        self.assertEqual(errors, [])

        self.client.resolve(next(iter(self.client.requests)))
        self.assertTrue(self.controller.is_playing)

    def test_remote_state_signal_is_identity_aware_for_resolve_lifecycle(self) -> None:
        remote = _remote_track("state-signal")
        events = []
        self.controller.remote_track_state_changed.connect(
            lambda identity, state, detail, payload: events.append(
                (identity, state, detail, dict(payload or {}))
            )
        )
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)
        request_id = next(iter(self.client.requests))
        self.assertEqual(events[-1][0:2], (remote.stable_identity, "resolving"))

        self.client.resolve(request_id)
        self.assertEqual(events[-1][0:2], (remote.stable_identity, "playable"))

    def test_source_capability_denial_is_unavailable_without_client_request(self) -> None:
        self.catalog[0]["capabilities"]["playback"] = False
        errors: list[str] = []
        self.controller.error_occurred.connect(errors.append)
        remote = _remote_track("blocked")
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)
        self._process_events()

        self.assertEqual(self.controller.playback_status, "unavailable")
        self.assertFalse(self.controller.is_playing)
        self.assertEqual(self.client.requests, {})
        self.assertEqual(len(errors), 1)
        self.assertIn("当前来源不可用", errors[0])

    def test_stale_resolution_cannot_replace_newer_local_or_remote_item(self) -> None:
        first = _remote_track("first")
        second = _remote_track("second")
        local = self._local_track()
        self.adapter.set_queue((first, second, local))

        self.adapter.play_track(first.id)
        first_request = next(iter(self.client.requests))
        self.adapter.play_track(second.id)
        second_request = max(self.client.requests)
        self.assertIn(first_request, self.client.cancelled)
        self.adapter.play_track(local.id)
        self.assertIn(second_request, self.client.cancelled)

        self.client.resolve(first_request)
        self.client.resolve(second_request)
        self.assertEqual(self.controller.current_item.stable_identity, local.stable_identity)
        self.assertEqual(Path(self.player.source().toLocalFile()), self.local_path)
        self.assertTrue(self.controller.is_playing)

    def test_switching_remote_tracks_keeps_the_new_queue_for_resolution(self) -> None:
        first = _remote_track("switch-first")
        second = _remote_track("switch-second")
        self.adapter.set_queue((first,))
        self.adapter.play_track(first.id)
        first_request = next(iter(self.client.requests))

        self.adapter.set_queue((second,), preserve_current_context=True)
        self.adapter.play_track(second.id)
        second_request = max(self.client.requests)

        self.assertIn(first_request, self.client.cancelled)
        self.assertEqual(
            self.controller.current_item.stable_identity,
            second.stable_identity,
        )
        self.assertEqual(self.controller.playback_status, "resolving")
        self.client.resolve(second_request)
        self.assertTrue(self.controller.is_playing)

    def test_provider_raw_survives_online_queue_projection(self) -> None:
        remote = _remote_track("provider-raw")
        remote = replace(
            remote,
            remote_payload={
                "id": remote.remote_track_id,
                "sourceId": remote.source_id,
                "raw": {
                    "id": remote.remote_track_id,
                    "qualities": {"standard": {"format": "mp3"}},
                },
            },
        )

        queue_item = PlaybackAdapter._queue_item_from_track(remote)
        payload = queue_item.media_item.to_legacy_online()

        self.assertEqual(
            payload["raw"]["qualities"]["standard"]["format"],
            "mp3",
        )
        self.assertEqual(payload["raw"]["id"], remote.remote_track_id)

    def test_playback_source_override_keeps_original_queue_identity(self) -> None:
        remote = _remote_track("original", source_id="old-source")
        remote = replace(
            remote,
            remote_payload={
                "id": remote.remote_track_id,
                "sourceId": remote.source_id,
                "playback_source": {
                    "source_id": "new-source",
                    "source_name": "新来源",
                    "remote_id": "new-remote-id",
                    "title": remote.title,
                    "artist": remote.artist,
                    "album": remote.album,
                    "duration": remote.duration_ms,
                    "raw": {"provider": "new-source"},
                },
            },
        )

        queue_item = PlaybackAdapter._queue_item_from_track(remote)
        payload = queue_item.media_item.to_legacy_online()

        self.assertEqual(queue_item.stable_identity, remote.stable_identity)
        self.assertEqual(payload["remoteStableId"], remote.stable_identity)
        self.assertEqual(payload["sourceId"], "new-source")
        self.assertEqual(payload["id"], "new-remote-id")
        self.assertEqual(payload["raw"]["provider"], "new-source")

    def test_resolve_timeout_closes_the_remote_state(self) -> None:
        remote = _remote_track("timeout")
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)
        request_id = max(self.client.requests)
        token = self.resolver.active_token

        self.resolver._on_timeout(token)

        self.assertIn(request_id, self.client.cancelled)
        self.assertEqual(self.controller.playback_status, "error")
        self.assertFalse(self.controller.is_playing)
        self.assertEqual(self.resolver.active_token, 0)

    def test_mixed_queue_uses_same_controller_for_remote_then_local(self) -> None:
        local = self._local_track()
        remote = _remote_track("mixed")
        self.adapter.set_queue((local, remote))
        self.adapter.play_track(local.id)
        self.assertEqual(len(self.controller.queue.items), 2)
        self.assertTrue(self.controller.play_next())
        request_id = max(self.client.requests)
        self.client.resolve(request_id)
        self.assertEqual(self.controller.current_item.stable_identity, remote.stable_identity)
        self.assertIs(self.adapter.controller, self.controller)
        self.assertIsNotNone(self.controller.media_player)
        self.assertIsNotNone(self.controller.audio_output)
        self.controller.play_next()
        self.assertEqual(self.controller.current_item.stable_identity, local.stable_identity)
        self.assertEqual(Path(self.player.source().toLocalFile()), self.local_path)

    def test_invalid_resolution_headers_and_network_failure_are_safe_errors(self) -> None:
        remote = _remote_track("errors")
        self.adapter.set_queue((remote,))
        errors: list[str] = []
        self.controller.error_occurred.connect(errors.append)

        self.adapter.play_track(remote.id)
        request_id = max(self.client.requests)
        self.client.resolve(request_id, "file:///not-an-http-url")
        self.assertEqual(self.controller.playback_status, "error")
        self.assertIn("播放地址无效", errors[-1])

        self.adapter.play_track(remote.id)
        request_id = max(self.client.requests)
        source_id, _ = self.client.requests[request_id]
        self.client.playbackResolved.emit(request_id, source_id, {"url": "https://fixture.invalid/a", "headers": {"Authorization": "x"}})
        self.assertIn("请求头", errors[-1])

        self.adapter.play_track(remote.id)
        request_id = max(self.client.requests)
        self.client.fail(request_id)
        self.assertEqual(self.controller.playback_status, "error")
        self.assertIn("网络暂不可用", errors[-1])

    def test_resolver_shutdown_cancels_active_request_and_ignores_late_result(self) -> None:
        remote = _remote_track("shutdown")
        self.adapter.set_queue((remote,))
        self.adapter.play_track(remote.id)
        request_id = max(self.client.requests)
        self.resolver.shutdown()
        self.client.resolve(request_id)

        self.assertIn(request_id, self.client.cancelled)
        self.assertFalse(self.controller.is_playing)
        self.assertEqual(self.controller.current_item.stable_identity, remote.stable_identity)

    def test_rapid_switches_keep_the_last_generation(self) -> None:
        first = _remote_track("rapid-a")
        second = _remote_track("rapid-b")
        self.adapter.set_queue((first, second))
        for _ in range(50):
            self.adapter.play_track(first.id)
            self.adapter.play_track(second.id)
        final_request = max(self.client.requests)
        self.client.resolve(final_request)

        self.assertEqual(self.controller.current_item.stable_identity, second.stable_identity)
        self.assertTrue(self.controller.is_playing)
        self.assertGreaterEqual(len(self.client.cancelled), 99)

    def test_remote_queue_storage_strips_transient_url_and_keeps_identity(self) -> None:
        remote = _remote_track("persist")
        self.adapter.set_queue((remote,))
        stored = self.controller.queue.items[0].to_storage_value()

        self.assertEqual(stored["stable_identity"], remote.stable_identity)
        provider_data = stored["media_item"]["extra"]["provider_data"]
        self.assertNotIn("url", provider_data)


if __name__ == "__main__":
    unittest.main()
