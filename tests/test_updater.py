"""更新检查：版本比较与清单解析（本地 HTTP 服务器，不依赖外网）。"""

from __future__ import annotations

import http.server
import json
import threading

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from hushplayer.core.settings import settings
from hushplayer.services import updater
from hushplayer.version import VERSION

MANIFEST = {
    "version": "9.9.9",
    "url": "https://example.com/HushPlayer-9.9.9-win64.zip",
    "notes": "测试更新说明",
    "published_at": "2026-03-01T10:00:00Z",
}


class _Handler(http.server.BaseHTTPRequestHandler):
    body = b"{}"
    status = 200
    content_type = "application/json"

    def log_message(self, *args):
        return

    def do_GET(self):  # noqa: N802
        self.send_response(type(self).status)
        self.send_header("Content-Type", type(self).content_type)
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)


@pytest.fixture()
def server():
    _Handler.body = json.dumps(MANIFEST).encode("utf-8")
    _Handler.status = 200
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/manifest.json"
    httpd.shutdown()
    thread.join(timeout=3)


def pump_until(predicate, timeout_ms: int = 15000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)

    def check():
        if predicate():
            loop.quit()
        else:
            QTimer.singleShot(20, check)

    QTimer.singleShot(20, check)
    timer.start(timeout_ms)
    loop.exec()
    timer.stop()
    return predicate()


def test_version_parsing_and_compare() -> None:
    assert updater.parse_version("1.2.3") == (1, 2, 3)
    assert updater.parse_version("v2.0") == (2, 0, 0)
    assert updater.parse_version("") == (0, 0, 0)
    assert updater.compare_versions("1.2.0", "1.1.9") == 1
    assert updater.compare_versions("1.0.0", "1.0.0") == 0
    assert updater.compare_versions("1.0.0", "1.0.1") == -1


def test_check_reports_new_version(server, data_dir, qapp) -> None:
    settings().set("update.manifest_url", server)
    service = updater.UpdateService()
    results: list[updater.UpdateInfo] = []
    failures: list[str] = []
    service.checked.connect(results.append)
    service.failed.connect(failures.append)
    assert service.check_async() is True
    assert pump_until(lambda: bool(results) or bool(failures)), "更新检查超时"
    assert not failures, failures
    info = results[0]
    assert info.version == "9.9.9"
    assert info.current == VERSION
    assert info.available is True
    assert info.url.endswith(".zip")
    assert info.published_at.startswith("2026-03-01")
    assert info.published_text == "2026-03-01"
    service.shutdown()


def test_up_to_date_manifest(server, data_dir, qapp) -> None:
    _Handler.body = json.dumps({"version": VERSION}).encode("utf-8")
    settings().set("update.manifest_url", server)
    service = updater.UpdateService()
    results: list[updater.UpdateInfo] = []
    service.checked.connect(results.append)
    service.check_async()
    assert pump_until(lambda: bool(results))
    assert results[0].available is False
    service.shutdown()


def test_missing_manifest_url_fails(data_dir, qapp) -> None:
    settings().set("update.manifest_url", "")
    service = updater.UpdateService()
    failures: list[str] = []
    service.failed.connect(failures.append)
    assert service.check_async() is False
    assert failures and "尚未配置更新源" in failures[0]
    service.shutdown()


def test_bad_json_reports_failure(server, data_dir, qapp) -> None:
    _Handler.body = b"<html>not json</html>"
    settings().set("update.manifest_url", server)
    service = updater.UpdateService()
    failures: list[str] = []
    service.failed.connect(failures.append)
    service.check_async()
    assert pump_until(lambda: bool(failures))
    assert "JSON" in failures[0]
    service.shutdown()


def test_http_error_reports_failure(server, data_dir, qapp) -> None:
    _Handler.status = 503
    _Handler.body = b"busy"
    settings().set("update.manifest_url", server)
    service = updater.UpdateService()
    failures: list[str] = []
    service.failed.connect(failures.append)
    service.check_async()
    assert pump_until(lambda: bool(failures))
    assert "503" in failures[0]
    service.shutdown()


def test_check_on_start_requires_url(data_dir, qapp) -> None:
    settings().set("update.manifest_url", "")
    assert updater.check_on_start_enabled() is False
    settings().set("update.manifest_url", "https://example.com/m.json")
    settings().set("update.check_on_start", True)
    assert updater.check_on_start_enabled() is True
