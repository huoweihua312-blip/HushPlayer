from __future__ import annotations

import hashlib
import json
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

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from app.services.app_update_service import (
    MAX_MANIFEST_BYTES,
    MAX_SETUP_BYTES,
    AppUpdateService,
    UpdateManifest,
    UpdateValidationError,
    parse_update_manifest,
    verify_installer_file,
)
from app.ui import main_window as main_window_module
from app.ui.main_window import MainWindow
from app.ui.update_dialog import UpdateDialog


class FixtureServer:
    def __init__(self) -> None:
        self.routes: dict[str, dict] = {}
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
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
    version: str = "0.5.0-beta.4",
    numeric_version: str = "0.5.0.4",
    sha256: str | None = None,
    setup_size: int | None = None,
) -> dict:
    return {
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
    assert manifest.numeric_version == (0, 5, 0, 4)
    assert manifest.installer_filename == "HushPlayer-0.5.0-beta.4-win-x64-setup.exe"

    same = dict(valid, version="0.5.0-beta.3", numeric_version="0.5.0.3")
    old = dict(valid, version="0.5.0-beta.2", numeric_version="0.5.0.2")
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


def configure_manifest_route(
    server: FixtureServer,
    document: dict,
    *,
    status: int = 200,
    delay: float = 0,
) -> None:
    server.routes["/manifest"] = {
        "status": status,
        "body": encoded_manifest(document),
        "content_type": "application/json",
        "delay": delay,
    }


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
    document = manifest_document(f"{server.base_url}/setup.exe", setup)
    configure_manifest_route(server, document)
    assert service.check_for_updates(manual=True)
    assert wait_until(lambda: bool(available))
    manifest, manual = available[-1]
    assert manual is True

    configure_manifest_route(
        server,
        manifest_document(
            f"{server.base_url}/setup.exe",
            setup,
            version="0.5.0-beta.3",
            numeric_version="0.5.0.3",
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
    ui_notification_policy_check()
    server = FixtureServer()
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_app_update_") as temp_dir:
            root = Path(temp_dir)
            service_checks(root, server, setup)
            shutdown_callback_check(root, server, setup)
    finally:
        server.close()
    print("app update smoke: OK")


if __name__ == "__main__":
    main()
