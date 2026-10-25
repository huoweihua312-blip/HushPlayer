"""下载服务：本地 HTTP 服务器提供音频，验证落盘、命名、索引与取消。"""

from __future__ import annotations

import http.server
import json
import pathlib
import threading
import time

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from hushplayer.core import paths
from hushplayer.core.settings import settings
from hushplayer.model.track import Track
from hushplayer.services import downloads as dl

PAYLOAD = b"ID3" + b"\x00" * 64 + bytes(range(256)) * 32


class _Handler(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []
    fail = False

    def log_message(self, *args):  # noqa: D401 - silence test server
        return

    def do_GET(self):  # noqa: N802 - http.server API
        type(self).hits.append(self.path)
        if type(self).fail:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"nope")
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)


@pytest.fixture()
def server():
    _Handler.hits = []
    _Handler.fail = False
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=3)


class FakeClient:
    def __init__(self, url: str, *, fail: bool = False) -> None:
        self.url = url
        self.fail = fail
        self.last_error = ""
        self.calls: list[tuple] = []

    def ensure_started(self) -> bool:
        return True

    def resolve_download(self, source_id, payload, callback, *, quality="higher", timeout=45000):
        self.calls.append((source_id, payload, quality))
        if self.fail:
            callback({"ok": False, "error": "音源拒绝提供下载地址"})
        else:
            callback({"ok": True, "data": {"url": self.url, "headers": {}, "mimeType": "audio/mpeg"}})
        return 1


def pump(ms: int = 60) -> None:
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)


def wait_for(predicate, timeout_ms: int = 15000) -> bool:
    """Poll ``predicate`` while letting the app process events.

    A nested :class:`QEventLoop` used to be used here, but it aborts with an
    access violation when the whole suite has already created dialogs and audio
    engines (Qt tears down a timer that a stale loop still owns).  Polling with
    ``processEvents`` exercises the same worker→UI hand-off without that risk.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    QApplication.processEvents()
    return predicate()


def online_track(remote: str = "123", title: str = "测试下载", artist: str = "测试歌手") -> Track:
    return Track(
        id=f"online:fake:{remote}",
        kind="online",
        title=title,
        artist=artist,
        album="测试专辑",
        duration_ms=180_000,
        source_id="fake-source",
        source_name="测试音源",
        remote_id=remote,
    )


def test_download_writes_file_and_index(server, data_dir, qapp):
    service = dl.DownloadService(FakeClient(f"{server}/song.mp3"))
    job = service.download([online_track()])[0]
    assert wait_for(lambda: job.state in {dl.STATE_DONE, dl.STATE_FAILED})
    assert job.state == dl.STATE_DONE, job.error
    path = paths.Path(job.path)
    assert path.is_file()
    assert path.stat().st_size == len(PAYLOAD)
    assert path.name.startswith("测试歌手 - 测试下载")
    assert path.suffix == ".mp3"
    index = dl.read_index()
    assert index and index[-1]["title"] == "测试下载"
    assert index[-1]["size"] == len(PAYLOAD)
    assert service.count_done() == 1
    service.shutdown()


def test_duplicate_names_get_suffix(server, data_dir, qapp):
    service = dl.DownloadService(FakeClient(f"{server}/song.mp3"))
    first = service.download([online_track(remote="1")])[0]
    assert wait_for(lambda: first.state == dl.STATE_DONE), first.error
    second = service.download([online_track(remote="2")])[0]
    assert wait_for(lambda: second.state == dl.STATE_DONE), second.error
    assert first.path != second.path
    assert "(2)" in paths.Path(second.path).name
    service.shutdown()


def test_resolver_error_is_reported(server, data_dir, qapp):
    service = dl.DownloadService(FakeClient(f"{server}/song.mp3", fail=True))
    job = service.download([online_track()])[0]
    assert wait_for(lambda: job.state == dl.STATE_FAILED)
    assert "下载地址" in job.error
    assert dl.read_index() == []
    service.shutdown()


def test_http_error_is_reported(server, data_dir, qapp):
    _Handler.fail = True
    service = dl.DownloadService(FakeClient(f"{server}/song.mp3"))
    job = service.download([online_track()])[0]
    assert wait_for(lambda: job.state == dl.STATE_FAILED)
    assert "500" in job.error
    service.shutdown()


def test_local_track_without_file_fails(data_dir, qapp):
    service = dl.DownloadService(FakeClient("http://127.0.0.1:1/x.mp3"))
    missing = Track(id="local:gone", kind="local", title="缺失", path=str(data_dir / "nope.mp3"))
    job = service.download([missing])[0]
    assert job.state == dl.STATE_FAILED
    assert "不存在" in job.error
    service.shutdown()


def test_cancel_marks_job(server, data_dir, qapp):
    service = dl.DownloadService(FakeClient(f"{server}/song.mp3"))
    job = service.download([online_track()])[0]
    service.cancel(job.id)
    assert job.state == dl.STATE_CANCELLED
    service.shutdown()


def test_index_is_reset_per_data_dir(server, data_dir, qapp):
    assert dl.read_index() == []
    assert dl.downloads_dir().is_dir()
    assert dl.index_file().name == "downloads.json"


def test_safe_filename() -> None:
    assert dl.safe_filename('a/b:c*?"<>|') == "a_b_c______"
    assert dl.safe_filename("   ") == "track"
    assert len(dl.safe_filename("x" * 400)) == 120
    assert settings().get("downloads.quality") in {"standard", "higher", "exhigh", "lossless"}

def test_retry_recovers_a_failed_download(data_dir, qapp, server) -> None:
    client = FakeClient(f"{server}/song.mp3", fail=True)
    service = dl.DownloadService(client)
    track = Track(id="online:src:r1", kind="online", title="重试测试", artist="歌手", source_id="src")
    job = service.download([track])[0]
    assert wait_for(lambda: job.state == dl.STATE_FAILED, 5000)
    assert not job.path

    client.fail = False
    service.retry(job.id)
    assert wait_for(lambda: job.state == dl.STATE_DONE, 15000)
    assert job.path and pathlib.Path(job.path).is_file()
    service.shutdown()


def test_remove_drops_job_but_keeps_history(data_dir, qapp, server) -> None:
    client = FakeClient(f"{server}/song.mp3")
    service = dl.DownloadService(client)
    track = Track(id="online:src:r2", kind="online", title="移除测试", artist="歌手", source_id="src")
    job = service.download([track])[0]
    assert wait_for(lambda: job.state == dl.STATE_DONE, 15000)
    assert len(service.history()) == 1

    service.remove(job.id)
    assert service.jobs == []
    assert len(service.history()) == 1
    service.shutdown()
