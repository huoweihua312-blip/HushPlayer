from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QApplication

from app.services.app_update_service import (
    MAX_MANIFEST_BYTES,
    MAX_SETUP_BYTES,
    AppUpdateService,
    UpdateManifest,
    UpdateValidationError,
    parse_update_manifest,
    select_update_release_notes,
    verify_installer_file,
)
from app.ui import main_window as main_window_module
from app.ui.main_window import MainWindow
from app.ui.update_dialog import UpdateDialog


class FixtureServer:
    def __init__(self) -> None:
        self.routes: dict[str, dict] = {}
        self.request_paths: list[str] = []
        self._request_lock = threading.Lock()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                with fixture._request_lock:
                    fixture.request_paths.append(self.path)
                route = fixture.routes.get(self.path)
                if route is None:
                    self.send_error(404)
                    return
                delay = float(route.get("delay", 0))
                if delay:
                    time.sleep(delay)
                body = bytes(route.get("body", b""))
                status = int(route.get("status", 200))
                self.send_response(status)
                location = route.get("location")
                if location:
                    self.send_header("Location", str(location))
                self.send_header(
                    "Content-Type",
                    str(route.get("content_type", "application/octet-stream")),
                )
                self.send_header(
                    "Content-Length",
                    str(route.get("content_length", len(body))),
                )
                self.end_headers()
                chunk_size = max(1, int(route.get("chunk_size", len(body) or 1)))
                chunk_delay = float(route.get("chunk_delay", 0))
                for offset in range(0, len(body), chunk_size):
                    try:
                        self.wfile.write(body[offset : offset + chunk_size])
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        break
                    if chunk_delay:
                        time.sleep(chunk_delay)

            def log_message(self, _format: str, *_args) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request_count(self, path: str) -> int:
        with self._request_lock:
            return self.request_paths.count(path)


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    app = QCoreApplication.instance()
    while time.monotonic() < deadline:
        if predicate():
            return True
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    if app is not None:
        app.processEvents()
    return bool(predicate())


def manifest_document(
    setup_url: str,
    setup: bytes,
    *,
    version: str = "0.5.0-beta.6",
    numeric_version: str = "0.5.0.6",
    sha256: str | None = None,
    setup_size: int | None = None,
    release_history: object | None = None,
) -> dict:
    document = {
        "schema_version": 1,
        "channel": "beta",
        "version": version,
        "numeric_version": numeric_version,
        "architecture": "win-x64",
        "mandatory": False,
        "setup_url": setup_url,
        "setup_size": len(setup) if setup_size is None else setup_size,
        "sha256": sha256 or hashlib.sha256(setup).hexdigest(),
        "release_notes": ["更新服务自动测试"],
    }
    if release_history is not None:
        document["release_history"] = release_history
    return document


def encoded_manifest(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def assert_manifest_rejected(document: dict, expected: str) -> None:
    try:
        parse_update_manifest(encoded_manifest(document))
    except UpdateValidationError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError(f"manifest unexpectedly accepted: {document}")


def parser_checks(setup: bytes) -> None:
    valid = manifest_document("https://example.com/HushPlayer-setup.exe", setup)
    manifest = parse_update_manifest(encoded_manifest(valid))
    assert manifest.is_newer
    assert manifest.numeric_version == (0, 5, 0, 6)
    assert manifest.installer_filename == "HushPlayer-0.5.0-beta.6-win-x64-setup.exe"
    assert manifest.release_history == ()

    same = dict(valid, version="0.5.0-beta.5", numeric_version="0.5.0.5")
    old = dict(valid, version="0.5.0-beta.4", numeric_version="0.5.0.4")
    assert not parse_update_manifest(encoded_manifest(same)).is_newer
    assert not parse_update_manifest(encoded_manifest(old)).is_newer

    missing = dict(valid)
    missing.pop("sha256")
    assert_manifest_rejected(missing, "缺少字段")
    assert_manifest_rejected(dict(valid, setup_url="http://example.com/a.exe"), "HTTPS")
    assert_manifest_rejected(dict(valid, channel="stable"), "通道")
    assert_manifest_rejected(dict(valid, architecture="win-arm64"), "架构")
    assert_manifest_rejected(dict(valid, sha256="not-a-hash"), "SHA-256")
    assert_manifest_rejected(dict(valid, setup_size=0), "安装包大小")
    assert_manifest_rejected(
        dict(valid, setup_size=MAX_SETUP_BYTES + 1),
        "安装包大小",
    )
    assert_manifest_rejected(
        dict(valid, numeric_version="0.5.0.5"),
        "version 与 numeric_version",
    )
    try:
        parse_update_manifest(b"x" * (MAX_MANIFEST_BYTES + 1))
    except UpdateValidationError as error:
        assert "128 KB" in str(error)
    else:
        raise AssertionError("oversized manifest accepted")


def release_history_entry(sequence: int, notes: list[str]) -> dict:
    return {
        "version": f"0.5.0-beta.{sequence}",
        "numeric_version": f"0.5.0.{sequence}",
        "release_date": f"2026-07-{sequence:02d}",
        "notes": notes,
    }


def release_history_checks(setup: bytes) -> None:
    ordered_history = [
        release_history_entry(8, ["beta.8 历史日志"]),
        release_history_entry(6, ["beta.6 历史日志"]),
        release_history_entry(7, ["beta.7 历史日志"]),
        release_history_entry(7, ["重复 beta.7 日志"]),
        {"version": "invalid", "numeric_version": "0.5.0.9"},
    ]
    logger = logging.getLogger("app.services.app_update_service")
    messages: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    handler = CaptureHandler()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        manifest = parse_update_manifest(
            encoded_manifest(
                manifest_document(
                    "https://example.com/HushPlayer-setup.exe",
                    setup,
                    version="0.5.0-beta.8",
                    numeric_version="0.5.0.8",
                    release_history=ordered_history,
                )
            )
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert [item.version for item in manifest.release_history] == [
        "0.5.0-beta.6",
        "0.5.0-beta.7",
        "0.5.0-beta.8",
    ]
    assert manifest.release_history[1].notes == ("beta.7 历史日志",)
    assert any("duplicate release_history" in message for message in messages)
    assert any("invalid release_history" in message for message in messages)

    beta_five_to_beta_eight = select_update_release_notes(manifest)
    assert [item.version for item in beta_five_to_beta_eight] == [
        "0.5.0-beta.6",
        "0.5.0-beta.7",
        "0.5.0-beta.8",
    ]
    assert all(
        note != "更新服务自动测试"
        for item in beta_five_to_beta_eight
        for note in item.notes
    )

    beta_five_to_beta_six = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                release_history=[release_history_entry(6, ["beta.6 历史日志"])],
            )
        )
    )
    assert [item.version for item in select_update_release_notes(beta_five_to_beta_six)] == [
        "0.5.0-beta.6"
    ]
    assert [
        item.version
        for item in select_update_release_notes(
            manifest,
            current_numeric_version="0.5.0.7",
        )
    ] == ["0.5.0-beta.8"]

    legacy = parse_update_manifest(
        encoded_manifest(
            manifest_document("https://example.com/HushPlayer-setup.exe", setup)
        )
    )
    legacy_sections = select_update_release_notes(legacy)
    assert len(legacy_sections) == 1
    assert legacy_sections[0].release_date is None
    assert legacy_sections[0].notes == ("更新服务自动测试",)

    empty_history = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                release_history=[],
            )
        )
    )
    assert select_update_release_notes(empty_history) == legacy_sections

    unmatched_history = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                release_history=[release_history_entry(4, ["已安装的旧版本日志"])],
            )
        )
    )
    assert select_update_release_notes(unmatched_history) == legacy_sections

    partial_history = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                version="0.5.0-beta.8",
                numeric_version="0.5.0.8",
                release_history=[
                    release_history_entry(6, ["仍可显示的 beta.6 日志"]),
                    {
                        "version": "0.5.0-beta.7",
                        "numeric_version": "invalid",
                        "release_date": "2026-07-07",
                        "notes": ["损坏条目"],
                    },
                ],
            )
        )
    )
    partial_sections = select_update_release_notes(partial_history)
    assert [item.version for item in partial_sections] == [
        "0.5.0-beta.6",
        "0.5.0-beta.8",
    ]
    assert partial_sections[-1].release_date is None
    assert partial_sections[-1].notes == ("更新服务自动测试",)

    invalid_date_history = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                version="0.5.0-beta.8",
                numeric_version="0.5.0.8",
                release_history=[
                    release_history_entry(6, ["仍可显示的 beta.6 日志"]),
                    {
                        "version": "0.5.0-beta.7",
                        "numeric_version": "0.5.0.7",
                        "release_date": "2026-07-XX",
                        "notes": ["无效日期条目"],
                    },
                ],
            )
        )
    )
    invalid_date_sections = select_update_release_notes(invalid_date_history)
    assert [item.version for item in invalid_date_sections] == [
        "0.5.0-beta.6",
        "0.5.0-beta.8",
    ]
    assert invalid_date_sections[-1].notes == ("更新服务自动测试",)

    all_invalid_history = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                release_history=[
                    {
                        "version": "0.5.0-beta.6",
                        "numeric_version": "0.5.0.6",
                        "release_date": "2026-07-XX",
                        "notes": ["无效日期条目"],
                    },
                ],
            )
        )
    )
    assert select_update_release_notes(all_invalid_history) == legacy_sections

    malformed_history = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                release_history="not-a-list",
            )
        )
    )
    assert select_update_release_notes(malformed_history) == legacy_sections

    same_version = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                version="0.5.0-beta.5",
                numeric_version="0.5.0.5",
                release_history=[release_history_entry(5, ["不应显示"])],
            )
        )
    )
    assert select_update_release_notes(same_version) == ()


def configure_manifest_route(
    server: FixtureServer,
    document: dict,
    *,
    path: str = "/manifest",
    status: int = 200,
    delay: float = 0,
    content_type: str = "application/json",
) -> None:
    server.routes[path] = {
        "status": status,
        "body": encoded_manifest(document),
        "content_type": content_type,
        "delay": delay,
    }


def manifest_source_fallback_checks(
    root: Path,
    server: FixtureServer,
    setup: bytes,
) -> None:
    """Exercise the production-style ordered manifest sources without real network."""

    def dispose_service(service: AppUpdateService) -> None:
        service.shutdown()
        service.deleteLater()
        QCoreApplication.sendPostedEvents(service, QEvent.Type.DeferredDelete)

    def begin_manifest_output_capture():
        output = io.StringIO()
        capture = contextlib.redirect_stdout(output)
        capture.__enter__()
        return output, capture

    def end_manifest_output_capture(capture) -> None:
        capture.__exit__(None, None, None)

    def source_paths(case: str) -> tuple[str, str]:
        return (f"/gitcode-{case}", f"/github-{case}")

    def source_service(case: str) -> AppUpdateService:
        gitcode_path, github_path = source_paths(case)
        return AppUpdateService(
            manifest_sources=(
                ("GitCode", f"{server.base_url}{gitcode_path}"),
                ("GitHub", f"{server.base_url}{github_path}"),
            ),
            updates_dir=root / f"source-{case}",
            allow_insecure_localhost=True,
        )

    def valid_document(case: str) -> dict:
        return manifest_document(f"{server.base_url}/setup-{case}.exe", setup)

    def expect_fallback(case: str, gitcode_route: dict) -> None:
        gitcode_path, github_path = source_paths(case)
        server.routes[gitcode_path] = gitcode_route
        configure_manifest_route(
            server,
            valid_document(case),
            path=github_path,
        )
        service = source_service(case)
        available: list[tuple[UpdateManifest, bool]] = []
        failures: list[tuple[str, bool]] = []
        service.updateAvailable.connect(
            lambda manifest, manual: available.append((manifest, manual))
        )
        service.checkFailed.connect(
            lambda message, manual: failures.append((message, manual))
        )
        output, capture = begin_manifest_output_capture()
        try:
            assert service.check_for_updates(manual=True)
            assert wait_until(lambda: bool(available))
            assert len(available) == 1
            assert not failures
            assert service._last_successful_manifest_source == "GitHub"
            assert "正在尝试备用更新源：GitHub" in output.getvalue()
            assert "更新清单获取成功：GitHub" in output.getvalue()
            assert server.request_count(gitcode_path) == 1
            assert server.request_count(github_path) == 1
        finally:
            dispose_service(service)
            end_manifest_output_capture(capture)

    primary_case = "primary-success"
    gitcode_path, github_path = source_paths(primary_case)
    configure_manifest_route(
        server,
        valid_document(primary_case),
        path=gitcode_path,
        content_type="application/octet-stream;charset=UTF-8",
    )
    service = source_service(primary_case)
    available: list[tuple[UpdateManifest, bool]] = []
    service.updateAvailable.connect(
        lambda manifest, manual: available.append((manifest, manual))
    )
    output, capture = begin_manifest_output_capture()
    try:
        assert service.check_for_updates(manual=False)
        assert wait_until(lambda: bool(available))
        assert len(available) == 1
        assert service._last_successful_manifest_source == "GitCode"
        assert "更新清单获取成功：GitCode" in output.getvalue()
        assert server.request_count(gitcode_path) == 1
        assert server.request_count(github_path) == 0
        request = service._build_manifest_request(f"{server.base_url}{gitcode_path}")
        assert request.attribute(QNetworkRequest.Attribute.Http2AllowedAttribute) is False
    finally:
        dispose_service(service)
        end_manifest_output_capture(capture)

    expect_fallback(
        "http-error",
        {
            "status": 500,
            "body": b"server error",
            "content_type": "text/plain",
        },
    )

    timeout_case = "timeout"
    service = source_service(timeout_case)

    class ReplySignal:
        def __init__(self) -> None:
            self._callbacks: list = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, *args) -> None:
            for callback in tuple(self._callbacks):
                callback(*args)

    class TimeoutReply:
        def __init__(self, payload: bytes = b"", *, status: int = 200) -> None:
            self.readyRead = ReplySignal()
            self.downloadProgress = ReplySignal()
            self.finished = ReplySignal()
            self.aborted = False
            self.deleted = False
            self._payload = payload
            self._status = status

        def abort(self) -> None:
            self.aborted = True

        def readAll(self) -> bytes:
            payload, self._payload = self._payload, b""
            return payload

        def attribute(self, attribute):
            if attribute == QNetworkRequest.Attribute.HttpStatusCodeAttribute:
                return self._status
            return None

        @staticmethod
        def url() -> QUrl:
            return QUrl("http://127.0.0.1/controlled-manifest")

        @staticmethod
        def error():
            return QNetworkReply.NetworkError.NoError

        @staticmethod
        def errorString() -> str:
            return ""

        def deleteLater(self) -> None:
            self.deleted = True

    class TimeoutNetwork:
        def __init__(self, replies: list[TimeoutReply]) -> None:
            self.replies = list(replies)
            self.requests: list[QNetworkRequest] = []

        def get(self, request: QNetworkRequest) -> TimeoutReply:
            self.requests.append(request)
            return self.replies.pop(0)

    timeout_reply = TimeoutReply()
    timeout_network = TimeoutNetwork([timeout_reply])
    service.network = timeout_network  # type: ignore[assignment]
    fallback_sources: list[str] = []

    def record_timeout_fallback() -> None:
        next_index = service._check_source_index + 1
        fallback_sources.append(service.manifest_sources[next_index][0])

    service._queue_next_manifest_source = record_timeout_fallback  # type: ignore[method-assign]
    try:
        # A controlled reply covers the timeout transition without relying on
        # a real socket timeout in the Python/PySide test runtime.  The same
        # GitCode → GitHub completion path is exercised with the HTTP fixture.
        assert service.check_for_updates(manual=False)
        assert len(timeout_network.requests) == 1
        service._on_check_timeout()
        timeout_reply.finished.emit()
        assert timeout_reply.aborted
        assert timeout_reply.deleted
        assert fallback_sources == ["GitHub"]
        assert timeout_network.requests[0].url().path().endswith("gitcode-timeout")
    finally:
        dispose_service(service)

    def expect_controlled_parse_fallback(case: str, payload: bytes) -> None:
        service = source_service(case)
        reply = TimeoutReply(payload)
        service.network = TimeoutNetwork([reply])  # type: ignore[assignment]
        fallback_sources: list[str] = []

        def record_parse_fallback() -> None:
            next_index = service._check_source_index + 1
            fallback_sources.append(service.manifest_sources[next_index][0])

        service._queue_next_manifest_source = record_parse_fallback  # type: ignore[method-assign]
        output, capture = begin_manifest_output_capture()
        try:
            assert service.check_for_updates(manual=False)
            reply.finished.emit()
            assert reply.deleted
            assert service._last_successful_manifest_source is None
            assert "更新清单获取成功：" not in output.getvalue()
            assert fallback_sources == ["GitHub"]
        finally:
            dispose_service(service)
            end_manifest_output_capture(capture)

    expect_controlled_parse_fallback("invalid-json", b"not-json")

    invalid_case = "invalid-schema"
    invalid_document = valid_document(invalid_case)
    invalid_document["channel"] = "stable"
    expect_controlled_parse_fallback(
        invalid_case,
        encoded_manifest(invalid_document),
    )

    expect_controlled_parse_fallback(
        "oversized",
        b"x" * (MAX_MANIFEST_BYTES + 1),
    )

    failure_case = "all-failed"
    service = source_service(failure_case)
    first_failure = TimeoutReply(status=500)
    second_failure = TimeoutReply(status=500)
    failure_network = TimeoutNetwork([first_failure, second_failure])
    service.network = failure_network  # type: ignore[assignment]
    service._queue_next_manifest_source = service._start_next_manifest_source  # type: ignore[method-assign]
    started: list[bool] = []
    completed: list[bool] = []
    failures: list[tuple[str, bool]] = []
    service.checkStarted.connect(started.append)
    service.checkCompleted.connect(lambda: completed.append(True))
    service.checkFailed.connect(
        lambda message, manual: failures.append((message, manual))
    )
    output, capture = begin_manifest_output_capture()
    try:
        assert service.check_for_updates(manual=True)
        first_failure.finished.emit()
        assert len(failure_network.requests) == 2
        second_failure.finished.emit()
        assert started == [True]
        assert completed == [True]
        assert failures == [("检查更新失败，请检查网络连接后重试。", True)]
        assert service._last_successful_manifest_source is None
        assert "更新清单获取成功：" not in output.getvalue()
        assert first_failure.deleted
        assert second_failure.deleted
    finally:
        dispose_service(service)
        end_manifest_output_capture(capture)

    single_path = "/single-manifest-url"
    configure_manifest_route(
        server,
        valid_document("single-manifest-url"),
        path=single_path,
    )
    service = AppUpdateService(
        manifest_url=f"{server.base_url}{single_path}",
        updates_dir=root / "single-manifest-url",
        allow_insecure_localhost=True,
    )
    available = []
    service.updateAvailable.connect(
        lambda manifest, manual: available.append((manifest, manual))
    )
    output, capture = begin_manifest_output_capture()
    try:
        assert service.manifest_sources == (("自定义更新源", f"{server.base_url}{single_path}"),)
        assert service.check_for_updates(manual=True)
        assert wait_until(lambda: bool(available))
        assert service._last_successful_manifest_source == "自定义更新源"
        assert "更新清单获取成功：自定义更新源" in output.getvalue()
        assert server.request_count(single_path) == 1
    finally:
        dispose_service(service)
        end_manifest_output_capture(capture)

    shutdown_case = "shutdown"
    shutdown_gitcode_path, shutdown_github_path = source_paths(shutdown_case)
    configure_manifest_route(
        server,
        valid_document(shutdown_case),
        path=shutdown_gitcode_path,
        delay=0.35,
    )
    configure_manifest_route(
        server,
        valid_document(shutdown_case),
        path=shutdown_github_path,
    )
    service = source_service(shutdown_case)
    callbacks: list[str] = []
    service.updateAvailable.connect(lambda *_args: callbacks.append("available"))
    service.noUpdate.connect(lambda *_args: callbacks.append("no-update"))
    service.checkFailed.connect(lambda *_args: callbacks.append("failed"))
    assert service.check_for_updates(manual=False)
    dispose_service(service)
    assert wait_until(lambda: False, timeout=0.7) is False
    assert callbacks == []
    assert server.request_count(shutdown_github_path) == 0


def service_checks(root: Path, server: FixtureServer, setup: bytes) -> None:
    update_dir = root / "updates"
    user_sentinel = root / "user-data-do-not-touch.json"
    user_sentinel.write_text('{"preserved": true}', encoding="utf-8")
    launcher_ok = [False]
    launcher_calls: list[tuple[str, list[str]]] = []

    def launcher(path: str, arguments: list[str]):
        launcher_calls.append((path, list(arguments)))
        return launcher_ok[0], 12345 if launcher_ok[0] else 0

    service = AppUpdateService(
        manifest_url=f"{server.base_url}/manifest",
        updates_dir=update_dir,
        allow_insecure_localhost=True,
        installer_launcher=launcher,
    )
    available: list[tuple[UpdateManifest, bool]] = []
    no_updates: list[bool] = []
    check_failures: list[tuple[str, bool]] = []
    verified: list[tuple[UpdateManifest, str]] = []
    download_failures: list[str] = []
    cancelled: list[bool] = []
    launch_failures: list[str] = []
    launched: list[str] = []
    progress: list[tuple[int, int]] = []
    service.updateAvailable.connect(lambda item, manual: available.append((item, manual)))
    service.noUpdate.connect(no_updates.append)
    service.checkFailed.connect(
        lambda message, manual: check_failures.append((message, manual))
    )
    service.downloadVerified.connect(
        lambda item, path: verified.append((item, path))
    )
    service.downloadFailed.connect(download_failures.append)
    service.downloadCancelled.connect(lambda: cancelled.append(True))
    service.downloadProgress.connect(lambda received, total: progress.append((received, total)))
    service.installerLaunchFailed.connect(launch_failures.append)
    service.installerLaunched.connect(launched.append)

    class ExitProbe:
        def __init__(self) -> None:
            self.close_count = 0

        def close(self) -> None:
            self.close_count += 1

    exit_probe = ExitProbe()
    service.installerLaunched.connect(
        lambda path: MainWindow.on_update_installer_launched(exit_probe, path)
    )
    assert not service.launch_verified_installer()
    assert launch_failures and "尚未完成校验" in launch_failures[-1]
    assert exit_probe.close_count == 0

    server.routes["/setup.exe"] = {
        "body": setup,
        "content_type": "application/octet-stream",
    }
    document = manifest_document(
        f"{server.base_url}/setup.exe",
        setup,
        release_history=[release_history_entry(6, ["beta.6 更新日志"])],
    )
    configure_manifest_route(server, document)
    assert service.check_for_updates(manual=True)
    assert wait_until(lambda: bool(available))
    manifest, manual = available[-1]
    assert manual is True
    manual_sections = select_update_release_notes(manifest)
    assert [item.version for item in manual_sections] == ["0.5.0-beta.6"]

    assert service.check_for_updates(manual=False)
    assert wait_until(lambda: len(available) >= 2)
    automatic_manifest, automatic_manual = available[-1]
    assert automatic_manual is False
    assert select_update_release_notes(automatic_manifest) == manual_sections

    configure_manifest_route(
        server,
        manifest_document(
            f"{server.base_url}/setup.exe",
            setup,
            version="0.5.0-beta.5",
            numeric_version="0.5.0.5",
        ),
    )
    assert service.check_for_updates(manual=False)
    assert wait_until(lambda: no_updates == [False])

    configure_manifest_route(server, document, status=500)
    assert service.check_for_updates(manual=False)
    assert wait_until(lambda: any(not item[1] for item in check_failures))
    assert service.check_for_updates(manual=True)
    assert wait_until(lambda: any(item[1] for item in check_failures))
    configure_manifest_route(server, document)

    before_failure_count = len(download_failures)
    server.routes["/setup.exe"] = {
        "body": setup[:-16],
        "content_type": "application/octet-stream",
    }
    assert service.start_download(manifest)
    assert wait_until(lambda: len(download_failures) > before_failure_count)
    assert "大小" in download_failures[-1]
    assert not (update_dir / manifest.installer_filename).exists()

    wrong_hash_manifest = parse_update_manifest(
        encoded_manifest(dict(document, sha256="0" * 64)),
        allow_insecure_localhost=True,
    )
    before_failure_count = len(download_failures)
    server.routes["/setup.exe"] = {
        "body": setup,
        "content_type": "application/octet-stream",
    }
    assert service.start_download(wrong_hash_manifest)
    assert wait_until(lambda: len(download_failures) > before_failure_count)
    assert "SHA-256" in download_failures[-1]
    assert not (update_dir / manifest.installer_filename).exists()

    slow_setup = b"MZ" + b"s" * (256 * 1024 - 2)
    slow_document = manifest_document(f"{server.base_url}/slow.exe", slow_setup)
    slow_manifest = parse_update_manifest(
        encoded_manifest(slow_document),
        allow_insecure_localhost=True,
    )
    server.routes["/slow.exe"] = {
        "body": slow_setup,
        "content_type": "application/octet-stream",
        "chunk_size": 4096,
        "chunk_delay": 0.01,
    }
    assert service.start_download(slow_manifest)
    assert wait_until(lambda: bool(progress))
    assert service.cancel_download()
    assert wait_until(lambda: bool(cancelled))
    assert not (update_dir / slow_manifest.installer_filename).exists()

    server.routes["/setup.exe"] = {
        "body": setup,
        "content_type": "application/octet-stream",
    }
    assert service.start_download(manifest)
    assert wait_until(lambda: bool(verified))
    verified_path = Path(verified[-1][1])
    verify_installer_file(verified_path, manifest)
    assert progress and progress[-1][1] == len(setup)

    original_bytes = verified_path.read_bytes()
    verified_path.write_bytes(original_bytes[:-1] + b"z")
    assert not service.launch_verified_installer()
    assert launch_failures and "SHA-256" in launch_failures[-1]
    assert not launcher_calls
    assert not verified_path.exists()

    assert service.start_download(manifest)
    assert wait_until(lambda: len(verified) >= 2)
    fake_playback_state = {
        "queue": ["track-a", "track-b"],
        "volume": 65,
        "position": 43210,
    }
    expected_playback_state = dict(fake_playback_state)
    assert not service.launch_verified_installer()
    assert launcher_calls and launcher_calls[-1][1] == list(service.INSTALLER_ARGUMENTS)
    assert not launched
    assert exit_probe.close_count == 0
    assert fake_playback_state == expected_playback_state

    launcher_ok[0] = True
    assert service.launch_verified_installer()
    assert launched
    assert exit_probe.close_count == 1
    assert fake_playback_state == expected_playback_state

    dialog = UpdateDialog(service, manifest)
    assert dialog.install_button.isEnabled()
    assert not dialog.download_button.isEnabled()
    assert "SHA-256 已校验" in dialog.status_label.text()
    assert "0.5.0-beta.6 · 2026-07-06" in dialog.notes.toPlainText()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)

    stale = update_dir / "HushPlayer-0.1.0-beta.1-win-x64-setup.exe.old"
    unrelated = update_dir / "unrelated-user-file.txt"
    stale.write_bytes(b"old")
    unrelated.write_bytes(b"keep")
    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(stale, (old_time, old_time))
    assert service.cleanup_stale_updates(max_age_days=7) == 1
    assert not stale.exists()
    assert unrelated.read_bytes() == b"keep"
    assert user_sentinel.read_text(encoding="utf-8") == '{"preserved": true}'

    # A GitHub-style redirect can report a Content-Length that belongs
    # to the redirect response rather than to the final installer.
    server.routes["/setup.exe"] = {
        "body": setup,
        "content_type": "application/octet-stream",
    }
    server.routes["/redirect-setup.exe"] = {
        "status": 302,
        "location": f"{server.base_url}/setup.exe",
        "body": b"",
        "content_length": 0,
    }
    redirect_document = manifest_document(
        f"{server.base_url}/redirect-setup.exe",
        setup,
    )
    redirect_manifest = parse_update_manifest(
        encoded_manifest(redirect_document),
        allow_insecure_localhost=True,
    )
    before_failure_count = len(download_failures)
    before_verified_count = len(verified)
    assert service.start_download(redirect_manifest)
    assert wait_until(lambda: len(verified) > before_verified_count)
    assert len(download_failures) == before_failure_count
    redirected_path = Path(verified[-1][1])
    verify_installer_file(redirected_path, redirect_manifest)

    service.shutdown()


def shutdown_callback_check(root: Path, server: FixtureServer, setup: bytes) -> None:
    document = manifest_document(f"{server.base_url}/setup.exe", setup)
    configure_manifest_route(server, document, delay=0.4)
    service = AppUpdateService(
        manifest_url=f"{server.base_url}/manifest",
        updates_dir=root / "destroyed-service-updates",
        allow_insecure_localhost=True,
    )
    callbacks: list[str] = []
    service.updateAvailable.connect(lambda *_args: callbacks.append("available"))
    service.noUpdate.connect(lambda *_args: callbacks.append("no-update"))
    service.checkFailed.connect(lambda *_args: callbacks.append("failed"))
    assert service.check_for_updates(manual=False)
    service.shutdown()
    service.deleteLater()
    assert wait_until(lambda: False, timeout=0.7) is False
    assert callbacks == []


def update_dialog_history_layout_check(setup: bytes) -> None:
    long_history = []
    for sequence in (6, 7, 8):
        notes = [
            f"beta.{sequence} 长更新日志 {index}: " + "内容" * 80
            for index in range(50)
        ]
        if sequence == 6:
            notes[0] = "<b>普通文本</b>"
        long_history.append(release_history_entry(sequence, notes))
    manifest = parse_update_manifest(
        encoded_manifest(
            manifest_document(
                "https://example.com/HushPlayer-setup.exe",
                setup,
                version="0.5.0-beta.8",
                numeric_version="0.5.0.8",
                release_history=long_history,
            )
        )
    )
    service = AppUpdateService(manifest_url="https://example.com/manifest.json")
    dialog = UpdateDialog(service, manifest)
    try:
        assert "将从 0.5.0-beta.5 更新到 0.5.0-beta.8" in dialog.subtitle.text()
        notes_text = dialog.notes.toPlainText()
        assert "0.5.0-beta.6 · 2026-07-06" in notes_text
        assert "0.5.0-beta.7 · 2026-07-07" in notes_text
        assert "0.5.0-beta.8 · 2026-07-08" in notes_text
        assert "更新服务自动测试" not in notes_text
        assert "<b>普通文本</b>" in notes_text
        dialog.resize(560, 430)
        dialog.show()
        QCoreApplication.processEvents()
        assert dialog.notes.verticalScrollBar().maximum() > 0
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)
        service.shutdown()


def ui_notification_policy_check() -> None:
    warnings: list[tuple] = []

    class FakeMessageBox:
        @staticmethod
        def warning(*args):
            warnings.append(args)

    class MessageProbe:
        @staticmethod
        def update_message_parent():
            return None

    original_message_box = main_window_module.QMessageBox
    main_window_module.QMessageBox = FakeMessageBox
    try:
        probe = MessageProbe()
        MainWindow.on_update_check_failed(probe, "自动失败", False)
        assert warnings == []
        MainWindow.on_update_check_failed(probe, "手动失败", True)
        assert len(warnings) == 1
        assert warnings[0][1:] == ("检查更新失败", "手动失败")
    finally:
        main_window_module.QMessageBox = original_message_box


def main() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    setup = b"MZ" + bytes((index % 251 for index in range(8190)))
    parser_checks(setup)
    release_history_checks(setup)
    ui_notification_policy_check()
    server = FixtureServer()
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_app_update_") as temp_dir:
            root = Path(temp_dir)
            service_checks(root, server, setup)
            manifest_source_fallback_checks(root, server, setup)
            shutdown_callback_check(root, server, setup)
    finally:
        server.close()
    update_dialog_history_layout_check(setup)
    print("app update smoke: OK")


if __name__ == "__main__":
    main()
