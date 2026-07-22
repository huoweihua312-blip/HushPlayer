from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import closing
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, QProcess, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton

from app.models.media_item import MediaItem
from app.services.online_audio_cache import OnlineAudioCacheService
import app.ui.main_window as main_window_module
from app.ui.main_window import MainWindow, SettingsDialog


def wait_until(predicate, timeout_ms: int = 5000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class AudioFixtureHandler(BaseHTTPRequestHandler):
    payload = (
        b"RIFF"
        + (16384).to_bytes(4, "little")
        + b"WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00"
        + b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00"
        + b"data"
        + (16348).to_bytes(4, "little")
        + bytes((index % 251 for index in range(16348)))
    )
    request_counts: dict[str, int] = {}

    def log_message(self, _format: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        type(self).request_counts[path] = type(self).request_counts.get(path, 0) + 1
        if path == "/invalid":
            body = (b"<!doctype html><html><body>expired</body></html>" * 40)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        payload = type(self).payload
        self.send_response(200)
        if path != "/opaque":
            self.send_header("Content-Type", "audio/wav")
        if path != "/no-content-length":
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if path == "/slow":
            for offset in range(0, len(payload), 512):
                try:
                    self.wfile.write(payload[offset : offset + 512])
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(0.025)
            return
        self.wfile.write(payload)


class FixtureServer:
    def __init__(self) -> None:
        AudioFixtureHandler.request_counts = {}
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(AudioFixtureHandler),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FixtureServer":
        self.thread.start()
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.server.server_port}{path}"


class SettingsDialogThemeManagerStub(QObject):
    """Provide the SettingsDialog theme notification contract without app state."""

    themeChanged = Signal(str)


def track(track_id: str, quality: str = "standard") -> dict:
    return {
        "sourceId": "open_fixture",
        "id": track_id,
        "title": f"Fixture {track_id}",
        "artist": "HushPlayer tests",
        "quality": quality,
        "availability": "available",
        "capabilities": {"playback": True},
    }


def cache_one(
    service: OnlineAudioCacheService,
    server: FixtureServer,
    value: dict,
    path: str = "/audio",
) -> dict:
    assert service.start_cache(
        value,
        {
            "url": server.url(path),
            "headers": {},
            "quality": value.get("quality") or "standard",
        },
    )
    assert wait_until(lambda: service.active_count() == 0)
    record = service.valid_cache(value, touch=False)
    assert record is not None
    return record


def test_cache_service(app: QApplication, server: FixtureServer) -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_audio_cache_") as temp_dir:
        root = Path(temp_dir)
        cache_root = root / "qt-cache" / "audio"
        sentinel_root = root / "user-state"
        sentinel_root.mkdir(parents=True)
        sentinels = {
            name: sentinel_root / name
            for name in (
                "playlists.json",
                "stats.json",
                "lyrics-cache.json",
                "cover-cache.img",
            )
        }
        for path in sentinels.values():
            path.write_text("untouched", encoding="utf-8")

        service = OnlineAudioCacheService(cache_root)
        assert service.cache_root == cache_root.resolve()
        assert service.files_dir == cache_root.resolve() / "audio"
        assert service.temp_dir == cache_root.resolve() / "temp"
        assert service.index_path == cache_root.resolve() / "cache_index.sqlite3"

        class SettingsHost(QMainWindow):
            def __init__(self) -> None:
                super().__init__()
                self.theme_manager = SettingsDialogThemeManagerStub(self)

            def get_hush_settings(self) -> dict:
                return {}

        settings_host = SettingsHost()
        settings_host.online_audio_cache = service
        dialog = SettingsDialog(settings_host)
        settings_host.theme_manager.themeChanged.emit("dark")
        app.processEvents()
        assert str(cache_root.resolve()) in dialog.audio_cache_path_label.text()
        assert "已缓存歌曲" in dialog.audio_cache_summary_label.text()
        button_texts = {button.text() for button in dialog.findChildren(QPushButton)}
        assert {
            "打开缓存目录",
            "清理未完成缓存",
            "清理全部音频缓存",
        } <= button_texts

        dialog.resize(520, 520)
        dialog.show()
        dialog.settings_scroll.setFixedHeight(260)
        app.processEvents()
        vertical_bar = dialog.settings_scroll.verticalScrollBar()
        horizontal_bar = dialog.settings_scroll.horizontalScrollBar()
        assert vertical_bar.maximum() > 0
        assert (
            dialog.settings_scroll.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert horizontal_bar.maximum() == 0, {
            "maximum": horizontal_bar.maximum(),
            "content_width": dialog.settings_scroll_content.width(),
            "viewport_width": dialog.settings_scroll.viewport().width(),
            "minimum_hint": dialog.settings_scroll_content.minimumSizeHint().width(),
            "size_hint": dialog.settings_scroll_content.sizeHint().width(),
        }
        assert dialog.settings_scroll_content.width() <= (
            dialog.settings_scroll.viewport().width()
        )
        title_label = next(
            label
            for label in dialog.findChildren(QLabel)
            if label.objectName() == "settingsDialogTitle"
        )
        save_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "保存设置"
        )
        assert not dialog.settings_scroll_content.isAncestorOf(title_label)
        assert not dialog.settings_scroll_content.isAncestorOf(save_button)

        bottom_button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "清理全部音频缓存"
        )
        vertical_bar.setValue(vertical_bar.maximum())
        app.processEvents()
        bottom_top = bottom_button.mapTo(
            dialog.settings_scroll.viewport(), QPoint(0, 0)
        ).y()
        assert bottom_top < dialog.settings_scroll.viewport().height()
        assert bottom_top + bottom_button.height() > 0

        vertical_bar.setValue(0)
        viewport_wheel_event = QWheelEvent(
            QPointF(2, 2),
            QPointF(2, 2),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(
            dialog.settings_scroll.viewport(), viewport_wheel_event
        )
        assert vertical_bar.value() > 0

        vertical_bar.setValue(0)
        slider_value = dialog.alpha_slider.value()
        wheel_event = QWheelEvent(
            QPointF(2, 2),
            QPointF(2, 2),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        assert dialog.eventFilter(dialog.alpha_slider, wheel_event)
        assert vertical_bar.value() > 0
        assert dialog.alpha_slider.value() == slider_value

        vertical_bar.setValue(0)
        combo_index = dialog.floating_color_combo.currentIndex()
        touchpad_event = QWheelEvent(
            QPointF(2, 2),
            QPointF(2, 2),
            QPoint(0, -24),
            QPoint(),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        assert dialog.eventFilter(dialog.floating_color_combo, touchpad_event)
        assert vertical_bar.value() > 0
        assert dialog.floating_color_combo.currentIndex() == combo_index

        tall_height = dialog.settings_scroll_content.sizeHint().height() + 24
        dialog.settings_scroll.setFixedHeight(tall_height)
        app.processEvents()
        assert vertical_bar.maximum() == 0
        assert dialog.restore_checkbox.isEnabled()
        assert dialog.floating_color_combo.count() >= 1
        assert dialog.music_scan_import_mode_combo.count() >= 1
        assert all(button.isEnabled() for button in dialog.findChildren(QPushButton))
        original_restore = dialog.restore_checkbox.isChecked()
        dialog.restore_checkbox.setChecked(not original_restore)
        assert dialog.restore_checkbox.isChecked() is (not original_restore)
        dialog.alpha_slider.setValue(50)
        assert dialog.alpha_slider.value() == 50
        assert dialog.alpha_label.text() == "50%"
        dialog.music_scan_import_mode_combo.setCurrentIndex(1)
        assert dialog.music_scan_import_mode_combo.currentIndex() == 1

        opened_urls: list[QUrl] = []
        original_desktop_services = main_window_module.QDesktopServices
        main_window_module.QDesktopServices = SimpleNamespace(
            openUrl=lambda url: opened_urls.append(url) or True
        )
        try:
            open_host = SimpleNamespace(online_audio_cache=service)
            assert MainWindow.open_online_audio_cache_directory(open_host)
        finally:
            main_window_module.QDesktopServices = original_desktop_services
        assert len(opened_urls) == 1
        assert Path(opened_urls[0].toLocalFile()).resolve() == cache_root.resolve()

        dialog.deleteLater()
        settings_host.deleteLater()
        app.processEvents()

        first = track("first")
        expected_key = hashlib.sha256(
            b"open_fixture\0first\0standard"
        ).hexdigest()
        assert service.cache_key_for(first) == expected_key
        completed: list[tuple[str, str]] = []
        failures: list[tuple[str, str]] = []
        service.cacheCompleted.connect(
            lambda cache_key, path: completed.append((cache_key, path))
        )
        service.cacheFailed.connect(
            lambda cache_key, message: failures.append((cache_key, message))
        )

        assert service.start_cache(
            first,
            {
                "url": server.url("/audio"),
                "headers": {"Referer": "https://example.invalid/fixture"},
                "quality": "standard",
            },
        )
        assert not service.start_cache(
            first,
            {"url": server.url("/audio"), "headers": {}, "quality": "standard"},
        )
        assert wait_until(lambda: service.active_count() == 0)
        assert len(completed) == 1
        assert AudioFixtureHandler.request_counts["/audio"] == 1
        first_record = service.valid_cache(first)
        assert first_record is not None
        first_path = Path(first_record["local_path"])
        assert first_path.is_file()
        assert first_path.parent == service.files_dir
        assert first_path.suffix == ".wav"
        assert first_path.stat().st_size == len(AudioFixtureHandler.payload)
        assert first_record["expected_size"] == len(AudioFixtureHandler.payload)
        assert first_record["mime_type"] == "audio/wav"
        assert first_record["status"] == "complete"

        with closing(sqlite3.connect(service.index_path)) as database:
            columns = {
                row[1]
                for row in database.execute(
                    "PRAGMA table_info(cache_entries)"
                ).fetchall()
            }
        assert {
            "cache_key",
            "stable_identity",
            "source_id",
            "track_id",
            "quality",
            "local_path",
            "temporary_path",
            "status",
            "mime_type",
            "file_extension",
            "file_size",
            "expected_size",
            "created_at",
            "completed_at",
            "last_accessed_at",
            "last_error",
        } <= columns
        assert not {"url", "headers", "cookie", "token"} & columns

        request_count = dict(AudioFixtureHandler.request_counts)
        assert service.valid_cache(first, touch=False) is not None
        assert AudioFixtureHandler.request_counts == request_count

        no_length = cache_one(service, server, track("no-length"), "/no-content-length")
        assert no_length["file_size"] == len(AudioFixtureHandler.payload)
        opaque = cache_one(service, server, track("opaque"), "/opaque")
        assert Path(opaque["local_path"]).suffix == ".bin"

        invalid = track("invalid")
        assert service.start_cache(
            invalid,
            {"url": server.url("/invalid"), "headers": {}, "quality": "standard"},
        )
        assert wait_until(lambda: service.active_count() == 0)
        assert service.valid_cache(invalid, touch=False) is None
        assert failures
        assert not list(service.temp_dir.glob("*.part"))

        missing = track("missing")
        missing_record = cache_one(service, server, missing)
        Path(missing_record["local_path"]).unlink()
        assert service.valid_cache(missing, touch=False) is None
        assert service.cache_record(missing) is None

        damaged = track("damaged")
        damaged_record = cache_one(service, server, damaged)
        Path(damaged_record["local_path"]).write_bytes(b"<html>" * 400)
        assert service.valid_cache(damaged, touch=False) is None
        assert service.cache_record(damaged) is None

        generic_first = dict(first)
        generic_first.pop("quality")
        deletion = service.delete_cache(generic_first)
        assert deletion["removed"] == 1
        assert not first_path.exists()

        protected = track("protected")
        protected_record = cache_one(service, server, protected)
        protected_delete = service.delete_cache(
            protected,
            protected_cache_key=str(protected_record["cache_key"]),
        )
        assert protected_delete["skipped"] == 1
        assert service.valid_cache(protected, touch=False) is not None
        removable = track("removable")
        removable_record = cache_one(service, server, removable)
        outcome = service.clear_all(
            protected_cache_key=str(protected_record["cache_key"])
        )
        assert outcome["skipped"] == 1
        assert service.valid_cache(protected, touch=False) is not None
        assert service.valid_cache(removable, touch=False) is None
        assert not Path(removable_record["local_path"]).exists()

        slow = track("slow")
        assert service.start_cache(
            slow,
            {"url": server.url("/slow"), "headers": {}, "quality": "standard"},
        )
        assert wait_until(lambda: service.active_count() == 1)
        incomplete = service.clear_incomplete()
        assert incomplete["cancelled"] == 1
        assert service.active_count() == 0
        assert not list(service.temp_dir.glob("*.part"))
        time.sleep(0.15)
        app.processEvents()
        assert service.valid_cache(slow, touch=False) is None

        slow_all = track("slow-all")
        assert service.start_cache(
            slow_all,
            {"url": server.url("/slow"), "headers": {}, "quality": "standard"},
        )
        assert wait_until(lambda: service.active_count() == 1)
        cleared = service.clear_all(
            protected_cache_key=str(protected_record["cache_key"])
        )
        assert cleared["cancelled"] == 1
        assert service.active_count() == 0
        time.sleep(0.15)
        app.processEvents()
        assert service.valid_cache(slow_all, touch=False) is None
        assert service.valid_cache(protected, touch=False) is not None
        assert all(path.read_text(encoding="utf-8") == "untouched" for path in sentinels.values())

        assert service.findChildren(QThread) == []
        assert service.findChildren(QProcess) == []
        service.shutdown()
        service.shutdown()
        assert service.active_count() == 0
        service.deleteLater()
        app.processEvents()

        orphan = service.files_dir / f"{'a' * 64}.bin"
        stale_part = service.temp_dir / f"{'b' * 64}.part"
        orphan.write_bytes(AudioFixtureHandler.payload)
        stale_part.write_bytes(b"unfinished")
        reopened = OnlineAudioCacheService(cache_root)
        assert reopened.valid_cache(protected, touch=False) is not None
        assert not orphan.exists()
        assert not stale_part.exists()
        assert reopened.active_count() == 0
        assert reopened.findChildren(QThread) == []
        assert reopened.findChildren(QProcess) == []
        reopened.index_path.unlink()
        rebuilt_stats = reopened.statistics()
        assert rebuilt_stats["complete_count"] == 0
        assert reopened.index_path.is_file()
        rebuilt_clear = reopened.clear_all()
        assert rebuilt_clear["bytes"] >= len(AudioFixtureHandler.payload)
        assert not Path(protected_record["local_path"]).exists()
        reopened.shutdown()
        reopened.deleteLater()
        app.processEvents()


class FakeTimer:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class FakePlayer:
    def __init__(self, source: str = "https://example.invalid/expired", position: int = 42000) -> None:
        self._source = QUrl(source)
        self._position = position
        self.play_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0

    def source(self) -> QUrl:
        return self._source

    def setSource(self, source: QUrl) -> None:
        self._source = source

    def position(self) -> int:
        return self._position

    def play(self) -> None:
        self.play_calls += 1

    def pause(self) -> None:
        self.pause_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def playbackState(self):
        return QMediaPlayer.PlaybackState.StoppedState


def test_playback_integration() -> None:
    online = MediaItem.from_online(track("playback"))
    cached_path = str(PROJECT_ROOT / "build" / "isolated-cache-fixture.wav")
    cache_record = {
        "cache_key": "f" * 64,
        "local_path": cached_path,
        "file_size": 4096,
    }

    class CacheHit:
        def valid_cache(self, _value, **_kwargs):
            return dict(cache_record)

    resolved_requests: list[dict] = []
    started_sources: list[tuple[str, dict]] = []
    request_harness = SimpleNamespace(
        playback_generation=7,
        current_queue_identity=online.stable_identity,
        media_loading_generation=0,
        pending_online_playback_request=0,
        pending_online_playback_generation=0,
        pending_online_playback_identity="",
        pending_online_keep_target_on_failure=False,
        pending_online_preserve_session=False,
        pending_online_resume_position=0,
        pending_online_track=None,
        pending_online_media_item=None,
        pending_online_ui_snapshot=None,
        online_audio_cache=CacheHit(),
        online_source_client=SimpleNamespace(
            resolve_playback=lambda *_args: resolved_requests.append({}) or 91,
            cancel_request=lambda _request: True,
        ),
        cancel_pending_online_metadata=lambda: None,
        start_online_media_source=lambda _media, source, _generation, _identity, **kwargs: (
            started_sources.append((source.toLocalFile(), dict(kwargs))) or True
        ),
        finish_online_resume_failure=lambda _message: None,
    )
    MainWindow.request_online_playback(
        request_harness,
        online.to_legacy_online(),
        playback_generation=7,
        queue_identity=online.stable_identity,
    )
    assert not resolved_requests
    assert len(started_sources) == 1
    assert Path(started_sources[0][0]).resolve() == Path(cached_path).resolve()
    assert started_sources[0][1] == {
        "preserve_session": False,
        "restore_position": 0,
        "cache_key": "f" * 64,
    }

    cache_resume_calls: list[dict] = []
    resume_harness = SimpleNamespace(
        online_resume_in_progress=False,
        current_media_item=online,
        current_track_kind="online",
        media_player=FakePlayer(position=54321),
        last_recorded_position=53000,
        online_audio_cache=CacheHit(),
        playback_generation=3,
        current_track_identity=lambda: online.stable_identity,
        begin_playback_generation=lambda _identity: 4,
        start_online_media_source=lambda _media, source, generation, identity, **kwargs: (
            cache_resume_calls.append(
                {
                    "source": source.toLocalFile(),
                    "generation": generation,
                    "identity": identity,
                    **kwargs,
                }
            )
            or True
        ),
        finish_online_resume_failure=lambda message: (_ for _ in ()).throw(
            AssertionError(message)
        ),
    )
    MainWindow.resume_online_playback(resume_harness)
    assert Path(cache_resume_calls[0]["source"]).resolve() == Path(cached_path).resolve()
    assert cache_resume_calls[0]["restore_position"] == 54321
    assert cache_resume_calls[0]["preserve_session"] is True

    class CacheMiss:
        def valid_cache(self, _value, **_kwargs):
            return None

    refreshed: list[dict] = []
    retry_harness = SimpleNamespace(
        online_resume_in_progress=False,
        online_resume_retry_started=False,
        online_resume_generation=0,
        online_resume_identity="",
        online_resume_position=0,
        current_media_item=online,
        current_track_kind="online",
        current_queue_identity=online.stable_identity,
        media_player=FakePlayer(position=23000),
        last_recorded_position=21000,
        online_audio_cache=CacheMiss(),
        online_resume_timer=FakeTimer(),
        playback_generation=9,
        current_track_identity=lambda: online.stable_identity,
        request_online_playback=lambda value, **kwargs: refreshed.append(
            {"track": value, **kwargs}
        ),
        finish_online_resume_failure=lambda message: (_ for _ in ()).throw(
            AssertionError(message)
        ),
        play_current_song=lambda: None,
    )
    MainWindow.resume_online_playback(retry_harness)
    assert retry_harness.media_player.play_calls == 1
    assert retry_harness.online_resume_timer.started == 1
    MainWindow.retry_online_resume(retry_harness)
    assert len(refreshed) == 1
    assert refreshed[0]["preserve_session"] is True
    assert refreshed[0]["resume_position"] == 23000
    assert refreshed[0]["playback_generation"] == 9

    stale_starts: list[bool] = []
    stale_harness = SimpleNamespace(
        pending_online_playback_request=41,
        pending_online_track=online.to_legacy_online(),
        pending_online_media_item=online,
        pending_online_playback_generation=10,
        pending_online_playback_identity=online.stable_identity,
        pending_online_keep_target_on_failure=False,
        pending_online_preserve_session=False,
        pending_online_resume_position=0,
        playback_generation=11,
        current_queue_identity="remote:open_fixture:other",
        cancel_pending_online_metadata=lambda: None,
        reset_online_resume_recovery=lambda: None,
        start_online_media_source=lambda *_args, **_kwargs: stale_starts.append(True),
    )
    MainWindow.on_online_playback_resolved(
        stale_harness,
        41,
        online.source_id,
        {"url": "https://example.invalid/new.wav", "headers": {}},
    )
    assert not stale_starts

    first_play_order: list[tuple[str, object]] = []
    fresh = MediaItem.from_online({**track("fresh"), "quality": ""})
    first_play_harness = SimpleNamespace(
        pending_online_playback_request=42,
        pending_online_track=fresh.to_legacy_online(),
        pending_online_media_item=fresh,
        pending_online_playback_generation=12,
        pending_online_playback_identity=fresh.stable_identity,
        pending_online_keep_target_on_failure=False,
        pending_online_preserve_session=False,
        pending_online_resume_position=0,
        pending_online_ui_snapshot={},
        playback_generation=12,
        current_queue_identity=fresh.stable_identity,
        cancel_pending_online_metadata=lambda: None,
        refresh_remote_song_item=lambda *_args, **_kwargs: None,
        start_online_media_source=lambda media, *_args, **_kwargs: (
            first_play_order.append(("play", media.quality)) or True
        ),
        start_online_audio_cache=lambda media, resolution: (
            first_play_order.append(
                ("cache", (media.quality, resolution.get("quality")))
            )
            or True
        ),
    )
    MainWindow.on_online_playback_resolved(
        first_play_harness,
        42,
        fresh.source_id,
        {"url": "https://example.invalid/fresh", "headers": {}},
    )
    assert first_play_order == [
        ("play", "standard"),
        ("cache", ("standard", "standard")),
    ]

    local_play_calls: list[bool] = []
    local_harness = SimpleNamespace(
        media_player=FakePlayer(source="", position=1000),
        current_track_kind="local",
        play_current_song=lambda: local_play_calls.append(True),
        reset_online_resume_recovery=lambda: None,
    )
    MainWindow.toggle_play(local_harness)
    assert local_play_calls == [True]

    protection_harness = SimpleNamespace(
        current_media_item=online,
        current_online_cache_key="f" * 64,
    )
    assert MainWindow.protected_online_audio_cache_key(protection_harness) == "f" * 64
    protection_harness.current_media_item = MediaItem.from_local(
        {"path": str(PROJECT_ROOT / "local-fixture.wav")}
    )
    assert MainWindow.protected_online_audio_cache_key(protection_harness) == ""

    clear_calls: list[tuple[str, str]] = []
    clear_harness = SimpleNamespace(
        current_media_item=online,
        current_online_cache_key="f" * 64,
        online_audio_cache=SimpleNamespace(
            clear_incomplete=lambda **kwargs: (
                clear_calls.append(("incomplete", kwargs["protected_cache_key"]))
                or {"removed": 2}
            ),
            clear_all=lambda **kwargs: (
                clear_calls.append(("all", kwargs["protected_cache_key"]))
                or {"removed": 3, "skipped": 1}
            ),
        ),
        protected_online_audio_cache_key=lambda: "f" * 64,
        set_online_status_message=lambda message: clear_calls.append(("status", message)),
    )
    assert MainWindow.clear_incomplete_online_audio_cache(clear_harness) == 2
    assert MainWindow.clear_all_online_audio_cache(clear_harness)["removed"] == 3
    assert clear_calls[0] == ("incomplete", "f" * 64)
    assert clear_calls[1] == ("all", "f" * 64)
    assert clear_calls[2][0] == "status"


def test_source_cache_permissions() -> None:
    media_item = MediaItem.from_online(track("policy"))

    def allowed(source: dict) -> bool:
        harness = SimpleNamespace(get_registered_source_safely=lambda _source_id: source)
        return MainWindow.online_source_allows_audio_cache(harness, media_item)

    assert allowed(
        {
            "contentPolicy": "open",
            "capabilities": {"playback": True, "download": False},
        }
    )
    assert allowed(
        {
            "contentPolicy": "user_owned",
            "capabilities": {"playback": False, "download": True},
        }
    )
    assert not allowed(
        {
            "contentPolicy": "unknown",
            "capabilities": {"playback": True, "download": True},
        }
    )
    assert not allowed(
        {
            "contentPolicy": "closed",
            "capabilities": {"playback": True, "download": True},
        }
    )
    assert not allowed(
        {
            "enabled": False,
            "contentPolicy": "open",
            "capabilities": {"playback": True, "download": True},
        }
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with FixtureServer() as server:
        test_cache_service(app, server)
    test_playback_integration()
    test_source_cache_permissions()
    print("online audio cache smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
