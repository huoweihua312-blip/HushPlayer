"""Smoke coverage for the formal online audio cache and source policy."""

from __future__ import annotations

import hashlib
import os
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.services.cache_maintenance import clear_missing_cache_files
from app.services.online_audio_cache import OnlineAudioCacheService
from app.services.online_discovery_runtime import OnlineDiscoveryRuntime


def wait_until(predicate, timeout_ms: int = 5000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


class AudioFixtureHandler(BaseHTTPRequestHandler):
    payload = (
        b"RIFF"
        + (16384).to_bytes(4, "little")
        + b"WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00"
        + b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00"
        + b"data"
        + (16348).to_bytes(4, "little")
        + bytes(index % 251 for index in range(16348))
    )

    def log_message(self, _format: str, *args) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/invalid":
            body = b"<!doctype html><html><body>expired</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)


class FixtureServer:
    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(AudioFixtureHandler))
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


def cache_one(service: OnlineAudioCacheService, server: FixtureServer, value: dict, path: str) -> dict:
    assert service.start_cache(
        value,
        {"url": server.url(path), "headers": {}, "quality": value.get("quality")},
    )
    assert wait_until(lambda: service.active_count() == 0)
    record = service.valid_cache(value, touch=False)
    assert record is not None
    return record


def test_cache_service(app: QApplication, server: FixtureServer) -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_audio_cache_") as temp_dir:
        root = Path(temp_dir)
        cache_root = root / "qt-cache" / "audio"
        sentinel = root / "user-state" / "playlists.json"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("untouched", encoding="utf-8")
        service = OnlineAudioCacheService(cache_root)
        try:
            assert service.cache_root == cache_root.resolve()
            assert service.files_dir == cache_root.resolve() / "audio"
            assert service.temp_dir == cache_root.resolve() / "temp"
            assert service.index_path == cache_root.resolve() / "cache_index.sqlite3"

            first = track("first")
            expected_key = hashlib.sha256(b"open_fixture\0first\0standard").hexdigest()
            assert service.cache_key_for(first) == expected_key
            first_record = cache_one(service, server, first, "/audio")
            assert first_record["cache_key"] == expected_key
            assert Path(first_record["local_path"]).is_file()
            assert not service.start_cache(
                first,
                {"url": server.url("/audio"), "headers": {}, "quality": "standard"},
            )
            assert service.statistics()["complete_count"] == 1

            invalid = track("invalid")
            assert service.start_cache(
                invalid,
                {"url": server.url("/invalid"), "headers": {}, "quality": "standard"},
            )
            assert wait_until(lambda: service.active_count() == 0)
            assert service.valid_cache(invalid, touch=False) is None

            damaged = track("damaged")
            damaged_record = cache_one(service, server, damaged, "/audio")
            Path(damaged_record["local_path"]).write_bytes(b"broken")
            assert service.valid_cache(damaged, touch=False) is None

            protected = track("protected")
            removable = track("removable")
            protected_record = cache_one(service, server, protected, "/audio")
            cache_one(service, server, removable, "/audio")
            clear_result = service.clear_all(
                protected_cache_key=str(protected_record["cache_key"]),
            )
            assert clear_result["skipped"] == 1
            assert service.valid_cache(protected, touch=False) is not None
            assert service.valid_cache(removable, touch=False) is None
            assert sentinel.read_text(encoding="utf-8") == "untouched"
        finally:
            service.shutdown()
            service.shutdown()


class _SourceRegistry:
    def __init__(self, source: dict) -> None:
        self.source = source

    def get_source(self, source_id: str) -> dict | None:
        return self.source if source_id == "open_fixture" else None


def test_source_cache_permissions() -> None:
    class RuntimeHarness:
        pass

    media_item = MediaItem.from_online(track("policy"))
    runtime = RuntimeHarness()
    for source, expected in (
        ({"contentPolicy": "open", "capabilities": {"playback": True}}, True),
        ({"contentPolicy": "user_owned", "capabilities": {"download": True}}, True),
        ({"contentPolicy": "unknown", "capabilities": {"playback": True}}, False),
        ({"enabled": False, "contentPolicy": "open", "capabilities": {"playback": True}}, False),
    ):
        runtime.source_registry = _SourceRegistry(source)
        # This is the production runtime method, with only its registry seam stubbed.
        assert OnlineDiscoveryRuntime.online_source_allows_audio_cache(runtime, media_item) is expected


def test_failed_metadata_cache_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_cache_cleanup_") as temp_dir:
        root = Path(temp_dir)
        covers = root / "covers"
        lyrics = root / "lyrics" / "online"
        covers.mkdir(parents=True)
        lyrics.mkdir(parents=True)
        (covers / "failed.missing").write_text("", encoding="utf-8")
        (lyrics / "failed.missing").write_text("", encoding="utf-8")
        (covers / "keep.txt").write_text("keep", encoding="utf-8")

        result = clear_missing_cache_files((covers, lyrics))

        assert result["removed"] == 2
        assert result["errors"] == []
        assert not (covers / "failed.missing").exists()
        assert not (lyrics / "failed.missing").exists()
        assert (covers / "keep.txt").read_text(encoding="utf-8") == "keep"


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with FixtureServer() as server:
        test_cache_service(app, server)
    test_source_cache_permissions()
    test_failed_metadata_cache_cleanup()
    print("online audio cache smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
