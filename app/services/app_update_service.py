from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QIODevice,
    QObject,
    QProcess,
    QSaveFile,
    QStandardPaths,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.core.version import (
    APP_USER_AGENT,
    UPDATE_ARCHITECTURE,
    UPDATE_CHANNEL,
    UPDATE_MANIFEST_URL,
    is_newer_numeric_version,
    parse_numeric_version,
)


SUPPORTED_MANIFEST_SCHEMA = 1
MAX_MANIFEST_BYTES = 128 * 1024
MIN_SETUP_BYTES = 1024
MAX_SETUP_BYTES = 512 * 1024 * 1024

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-"
    r"([a-z][a-z0-9-]*)\.(0|[1-9]\d*)$"
)
_UPDATE_FILENAME_PATTERN = re.compile(
    r"^HushPlayer-[0-9A-Za-z.-]+-win-x64-setup\.exe(?:\..+)?$"
)


class UpdateValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    schema_version: int
    channel: str
    version: str
    numeric_version: tuple[int, int, int, int]
    numeric_version_text: str
    architecture: str
    mandatory: bool
    setup_url: str
    setup_size: int
    sha256: str
    release_notes: tuple[str, ...]

    @property
    def is_newer(self) -> bool:
        return is_newer_numeric_version(self.numeric_version)

    @property
    def installer_filename(self) -> str:
        return f"HushPlayer-{self.version}-{self.architecture}-setup.exe"


def validate_update_url(
    value: str,
    *,
    allow_insecure_localhost: bool = False,
) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    local_http_allowed = (
        allow_insecure_localhost
        and scheme == "http"
        and hostname in {"127.0.0.1", "localhost", "::1"}
    )
    if scheme != "https" and not local_http_allowed:
        raise UpdateValidationError("更新地址必须使用 HTTPS。")
    if not parsed.netloc or not hostname:
        raise UpdateValidationError("更新地址格式无效。")
    if parsed.username or parsed.password:
        raise UpdateValidationError("更新地址不允许包含用户名或密码。")
    if parsed.fragment:
        raise UpdateValidationError("更新地址不允许包含片段标识。")
    return text


def parse_update_manifest(
    payload: bytes,
    *,
    allow_insecure_localhost: bool = False,
) -> UpdateManifest:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise UpdateValidationError("更新清单响应超过 128 KB 安全上限。")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateValidationError("更新清单不是有效的 UTF-8 JSON。") from error
    if not isinstance(document, dict):
        raise UpdateValidationError("更新清单顶层必须是 JSON 对象。")

    required_fields = (
        "schema_version",
        "channel",
        "version",
        "numeric_version",
        "architecture",
        "setup_url",
        "setup_size",
        "sha256",
    )
    missing = [field for field in required_fields if field not in document]
    if missing:
        raise UpdateValidationError(f"更新清单缺少字段：{', '.join(missing)}。")

    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or schema_version != SUPPORTED_MANIFEST_SCHEMA:
        raise UpdateValidationError("更新清单 schema_version 不受支持。")

    channel = str(document["channel"] or "").strip()
    if channel != UPDATE_CHANNEL:
        raise UpdateValidationError("更新清单通道与当前 beta 通道不匹配。")

    architecture = str(document["architecture"] or "").strip()
    if architecture != UPDATE_ARCHITECTURE:
        raise UpdateValidationError("更新清单架构与当前 win-x64 架构不匹配。")

    version = str(document["version"] or "").strip()
    version_match = _VERSION_PATTERN.fullmatch(version)
    if version_match is None or len(version) > 64:
        raise UpdateValidationError("更新清单 version 格式无效。")
    version_major, version_minor, version_patch, version_channel, version_sequence = (
        version_match.groups()
    )
    if version_channel != channel:
        raise UpdateValidationError("更新清单 version 与 channel 不一致。")

    try:
        numeric_version = parse_numeric_version(str(document["numeric_version"] or ""))
    except ValueError as error:
        raise UpdateValidationError(str(error)) from error
    label_numeric = (
        int(version_major),
        int(version_minor),
        int(version_patch),
        int(version_sequence),
    )
    if numeric_version != label_numeric:
        raise UpdateValidationError("更新清单的 version 与 numeric_version 不一致。")

    setup_url = validate_update_url(
        document["setup_url"],
        allow_insecure_localhost=allow_insecure_localhost,
    )
    setup_size = document["setup_size"]
    if (
        isinstance(setup_size, bool)
        or not isinstance(setup_size, int)
        or not MIN_SETUP_BYTES <= setup_size <= MAX_SETUP_BYTES
    ):
        raise UpdateValidationError("安装包大小必须在 1 KB 到 512 MB 之间。")

    sha256 = str(document["sha256"] or "").strip().casefold()
    if _SHA256_PATTERN.fullmatch(sha256) is None:
        raise UpdateValidationError("安装包 SHA-256 必须是 64 位十六进制。")

    mandatory = document.get("mandatory", False)
    if not isinstance(mandatory, bool):
        raise UpdateValidationError("更新清单 mandatory 必须是布尔值。")

    raw_release_notes = document.get("release_notes", [])
    if not isinstance(raw_release_notes, list) or len(raw_release_notes) > 50:
        raise UpdateValidationError("更新说明必须是最多 50 项的字符串数组。")
    release_notes: list[str] = []
    for note in raw_release_notes:
        if not isinstance(note, str):
            raise UpdateValidationError("更新说明中的每一项都必须是字符串。")
        normalized = note.strip()
        if not normalized or len(normalized) > 1000:
            raise UpdateValidationError("更新说明包含空白或过长内容。")
        release_notes.append(normalized)

    return UpdateManifest(
        schema_version=SUPPORTED_MANIFEST_SCHEMA,
        channel=channel,
        version=version,
        numeric_version=numeric_version,
        numeric_version_text=".".join(str(part) for part in numeric_version),
        architecture=architecture,
        mandatory=mandatory,
        setup_url=setup_url,
        setup_size=setup_size,
        sha256=sha256,
        release_notes=tuple(release_notes),
    )


def verify_installer_file(path: str | Path, manifest: UpdateManifest) -> None:
    candidate = Path(path)
    try:
        if not candidate.is_file():
            raise UpdateValidationError("已下载的安装包不存在。")
        actual_size = candidate.stat().st_size
    except OSError as error:
        raise UpdateValidationError(f"无法读取已下载的安装包：{error}") from error
    if actual_size != manifest.setup_size:
        raise UpdateValidationError(
            f"安装包大小校验失败：应为 {manifest.setup_size} 字节，"
            f"实际为 {actual_size} 字节。"
        )
    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise UpdateValidationError(f"无法校验已下载的安装包：{error}") from error
    actual_sha256 = digest.hexdigest().casefold()
    if actual_sha256 != manifest.sha256:
        raise UpdateValidationError("安装包 SHA-256 校验失败，文件可能已损坏。")


def _start_detached_installer(path: str, arguments: list[str]):
    return QProcess.startDetached(path, arguments)


def _dispose_save_file(save_file: QSaveFile, *, cancel: bool = False) -> None:
    if cancel:
        save_file.cancelWriting()
    save_file.deleteLater()
    QCoreApplication.sendPostedEvents(save_file, QEvent.Type.DeferredDelete)


class AppUpdateService(QObject):
    checkStarted = Signal(bool)
    checkCompleted = Signal()
    updateAvailable = Signal(object, bool)
    noUpdate = Signal(bool)
    checkFailed = Signal(str, bool)
    downloadStarted = Signal(str)
    downloadProgress = Signal(int, int)
    downloadFailed = Signal(str)
    downloadCancelled = Signal()
    downloadVerified = Signal(object, str)
    installerLaunchFailed = Signal(str)
    installerLaunched = Signal(str)

    CHECK_TRANSFER_TIMEOUT_MS = 15_000
    CHECK_TOTAL_TIMEOUT_MS = 30_000
    DOWNLOAD_TRANSFER_TIMEOUT_MS = 30_000
    DOWNLOAD_TOTAL_TIMEOUT_MS = 30 * 60 * 1000
    INSTALLER_ARGUMENTS = (
        "/SP-",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/NORESTARTAPPLICATIONS",
    )

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        manifest_url: str = UPDATE_MANIFEST_URL,
        updates_dir: str | Path | None = None,
        allow_insecure_localhost: bool = False,
        installer_launcher: Callable[[str, list[str]], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.manifest_url = str(manifest_url)
        self.allow_insecure_localhost = bool(allow_insecure_localhost)
        self.network = QNetworkAccessManager(self)
        self.updates_dir = (
            Path(updates_dir)
            if updates_dir is not None
            else Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.TempLocation
                )
            )
            / "HushPlayer"
            / "updates"
        )
        self._installer_launcher = installer_launcher or _start_detached_installer
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._on_check_timeout)
        self._download_timer = QTimer(self)
        self._download_timer.setSingleShot(True)
        self._download_timer.timeout.connect(self._on_download_timeout)

        self._check_reply: QNetworkReply | None = None
        self._check_manual = False
        self._manifest_buffer = bytearray()
        self._check_failure = ""
        self._download_reply: QNetworkReply | None = None
        self._download_file: QSaveFile | None = None
        self._download_manifest: UpdateManifest | None = None
        self._download_target: Path | None = None
        self._download_hash = hashlib.sha256()
        self._download_prefix = bytearray()
        self._download_written = 0
        self._download_failure = ""
        self._download_cancel_requested = False
        self._verified_manifest: UpdateManifest | None = None
        self._verified_path: Path | None = None
        self._shutting_down = False

    @property
    def is_checking(self) -> bool:
        return self._check_reply is not None

    @property
    def is_downloading(self) -> bool:
        return self._download_reply is not None

    @property
    def verified_manifest(self) -> UpdateManifest | None:
        return self._verified_manifest

    @property
    def verified_path(self) -> Path | None:
        return self._verified_path

    def check_for_updates(self, *, manual: bool) -> bool:
        if self._shutting_down or self.is_checking or self.is_downloading:
            return False
        try:
            url = validate_update_url(
                self.manifest_url,
                allow_insecure_localhost=self.allow_insecure_localhost,
            )
        except UpdateValidationError as error:
            self.checkFailed.emit(str(error), bool(manual))
            return False

        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setTransferTimeout(self.CHECK_TRANSFER_TIMEOUT_MS)
        request.setRawHeader(b"User-Agent", f"{APP_USER_AGENT} updater".encode("ascii"))
        request.setRawHeader(b"Accept", b"application/json")
        reply = self.network.get(request)
        self._check_reply = reply
        self._check_manual = bool(manual)
        self._manifest_buffer.clear()
        self._check_failure = ""
        reply.readyRead.connect(lambda current=reply: self._read_manifest_data(current))
        reply.downloadProgress.connect(
            lambda received, total, current=reply: self._guard_manifest_size(
                current,
                received,
                total,
            )
        )
        reply.finished.connect(lambda current=reply: self._finish_check(current))
        self._check_timer.start(self.CHECK_TOTAL_TIMEOUT_MS)
        self.checkStarted.emit(bool(manual))
        return True

    def _guard_manifest_size(
        self,
        reply: QNetworkReply,
        received: int,
        total: int,
    ) -> None:
        if reply is not self._check_reply or self._check_failure:
            return
        if received > MAX_MANIFEST_BYTES or total > MAX_MANIFEST_BYTES:
            self._check_failure = "更新清单响应超过 128 KB 安全上限。"
            reply.abort()

    def _read_manifest_data(self, reply: QNetworkReply) -> None:
        if reply is not self._check_reply or self._check_failure:
            return
        chunk = bytes(reply.readAll())
        if len(self._manifest_buffer) + len(chunk) > MAX_MANIFEST_BYTES:
            self._check_failure = "更新清单响应超过 128 KB 安全上限。"
            reply.abort()
            return
        self._manifest_buffer.extend(chunk)

    def _on_check_timeout(self) -> None:
        reply = self._check_reply
        if reply is None:
            return
        self._check_failure = "检查更新超时，请稍后重试。"
        reply.abort()

    def _finish_check(self, reply: QNetworkReply) -> None:
        if reply is not self._check_reply:
            reply.deleteLater()
            return
        self._read_manifest_data(reply)
        self._check_timer.stop()
        manual = self._check_manual
        failure = self._check_failure
        payload = bytes(self._manifest_buffer)
        self._check_reply = None
        self._manifest_buffer.clear()
        self._check_failure = ""

        if not failure:
            failure = self._response_failure(reply, expected_status=200)
        if not failure and reply.error() != QNetworkReply.NetworkError.NoError:
            failure = f"检查更新失败：{reply.errorString()}"
        reply.deleteLater()

        if self._shutting_down:
            return
        self.checkCompleted.emit()
        if failure:
            self.checkFailed.emit(failure, manual)
            return
        try:
            manifest = parse_update_manifest(
                payload,
                allow_insecure_localhost=self.allow_insecure_localhost,
            )
        except UpdateValidationError as error:
            self.checkFailed.emit(str(error), manual)
            return
        if manifest.is_newer:
            self.updateAvailable.emit(manifest, manual)
        else:
            self.noUpdate.emit(manual)

    def start_download(self, manifest: UpdateManifest) -> bool:
        if (
            self._shutting_down
            or self.is_checking
            or self.is_downloading
            or not isinstance(manifest, UpdateManifest)
            or not manifest.is_newer
        ):
            return False
        try:
            validate_update_url(
                manifest.setup_url,
                allow_insecure_localhost=self.allow_insecure_localhost,
            )
            target = self._prepare_download_target(manifest)
        except (OSError, UpdateValidationError) as error:
            self.downloadFailed.emit(f"无法准备更新下载：{error}")
            return False

        save_file = QSaveFile(str(target))
        save_file.setDirectWriteFallback(False)
        if not save_file.open(QIODevice.OpenModeFlag.WriteOnly):
            self.downloadFailed.emit(f"无法创建更新临时文件：{save_file.errorString()}")
            _dispose_save_file(save_file)
            return False

        request = QNetworkRequest(QUrl(manifest.setup_url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setTransferTimeout(self.DOWNLOAD_TRANSFER_TIMEOUT_MS)
        request.setRawHeader(b"User-Agent", f"{APP_USER_AGENT} updater".encode("ascii"))
        request.setRawHeader(b"Accept", b"application/octet-stream")
        reply = self.network.get(request)
        self._download_reply = reply
        self._download_file = save_file
        self._download_manifest = manifest
        self._download_target = target
        self._download_hash = hashlib.sha256()
        self._download_prefix.clear()
        self._download_written = 0
        self._download_failure = ""
        self._download_cancel_requested = False
        self._verified_manifest = None
        self._verified_path = None
        reply.metaDataChanged.connect(
            lambda current=reply: self._validate_download_response(current)
        )
        reply.readyRead.connect(lambda current=reply: self._read_download_data(current))
        reply.downloadProgress.connect(
            lambda received, total, current=reply: self._on_download_progress(
                current,
                received,
                total,
            )
        )
        reply.finished.connect(lambda current=reply: self._finish_download(current))
        self._download_timer.start(self.DOWNLOAD_TOTAL_TIMEOUT_MS)
        self.downloadStarted.emit(str(target))
        return True

    def _prepare_download_target(self, manifest: UpdateManifest) -> Path:
        root = self.updates_dir.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.cleanup_stale_updates()
        target = (root / manifest.installer_filename).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise UpdateValidationError("更新文件路径超出专用临时目录。") from error
        if not _UPDATE_FILENAME_PATTERN.fullmatch(target.name):
            raise UpdateValidationError("程序生成的安装包文件名不安全。")
        if target.exists():
            target.unlink()
        return target

    def cleanup_stale_updates(self, *, max_age_days: int = 7) -> int:
        root = self.updates_dir.expanduser().resolve()
        if not root.is_dir():
            return 0
        threshold = time.time() - max(1, int(max_age_days)) * 24 * 60 * 60
        removed = 0
        for candidate in root.iterdir():
            if (
                not candidate.is_file()
                or not _UPDATE_FILENAME_PATTERN.fullmatch(candidate.name)
                or candidate == self._verified_path
            ):
                continue
            try:
                if candidate.stat().st_mtime < threshold:
                    candidate.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def _validate_download_response(self, reply: QNetworkReply) -> None:
        if reply is not self._download_reply or self._download_failure:
            return
        failure = self._response_failure(reply, expected_status=200, allow_redirect=True)
        if failure:
            self._download_failure = failure
            reply.abort()
            return

        status = reply.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        try:
            status_code = int(status or 0)
        except (TypeError, ValueError):
            status_code = 0

        if 300 <= status_code < 400:
            return

        content_length = bytes(reply.rawHeader("Content-Length")).decode(
            "ascii",
            errors="ignore",
        )
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            manifest = self._download_manifest
            if manifest is not None and declared_size != manifest.setup_size:
                self._download_failure = "服务器返回的安装包大小与更新清单不一致。"
                reply.abort()
                return
        content_type = bytes(reply.rawHeader("Content-Type")).decode(
            "latin-1",
            errors="ignore",
        ).split(";", 1)[0].strip().casefold()
        if content_type.startswith("text/") or content_type in {
            "application/json",
            "application/xhtml+xml",
        }:
            self._download_failure = "服务器返回的不是安装程序内容。"
            reply.abort()

    def _read_download_data(self, reply: QNetworkReply) -> None:
        if reply is not self._download_reply or self._download_failure:
            return
        self._validate_download_response(reply)
        manifest = self._download_manifest
        save_file = self._download_file
        if self._download_failure or manifest is None or save_file is None:
            return
        data = bytes(reply.readAll())
        if not data:
            return
        if len(self._download_prefix) < 2:
            needed = 2 - len(self._download_prefix)
            self._download_prefix.extend(data[:needed])
            if len(self._download_prefix) == 2 and self._download_prefix != b"MZ":
                self._download_failure = "下载内容不是有效的 Windows 安装程序。"
                reply.abort()
                return
        if self._download_written + len(data) > manifest.setup_size:
            self._download_failure = "下载内容超过更新清单声明的安装包大小。"
            reply.abort()
            return
        written = save_file.write(data)
        if written != len(data):
            self._download_failure = f"写入更新文件失败：{save_file.errorString()}"
            reply.abort()
            return
        self._download_hash.update(data)
        self._download_written += written

    def _on_download_progress(
        self,
        reply: QNetworkReply,
        received: int,
        total: int,
    ) -> None:
        if reply is not self._download_reply or self._download_failure:
            return
        manifest = self._download_manifest
        if manifest is None:
            return
        if received > manifest.setup_size or total > MAX_SETUP_BYTES:
            self._download_failure = "安装包下载大小超过安全限制。"
            reply.abort()
            return
        self.downloadProgress.emit(max(0, int(received)), manifest.setup_size)

    def cancel_download(self) -> bool:
        reply = self._download_reply
        if reply is None:
            return False
        self._download_cancel_requested = True
        reply.abort()
        return True

    def _on_download_timeout(self) -> None:
        reply = self._download_reply
        if reply is None:
            return
        self._download_failure = "安装包下载超时，请稍后重试。"
        reply.abort()

    def _finish_download(self, reply: QNetworkReply) -> None:
        if reply is not self._download_reply:
            reply.deleteLater()
            return
        self._read_download_data(reply)
        self._download_timer.stop()
        manifest = self._download_manifest
        save_file = self._download_file
        target = self._download_target
        cancelled = self._download_cancel_requested
        failure = self._download_failure
        if not cancelled and not failure:
            failure = self._response_failure(reply, expected_status=200)
        if (
            not cancelled
            and not failure
            and reply.error() != QNetworkReply.NetworkError.NoError
        ):
            failure = f"安装包下载失败：{reply.errorString()}"
        if not cancelled and not failure and manifest is not None:
            if self._download_written != manifest.setup_size:
                failure = (
                    f"安装包大小校验失败：应为 {manifest.setup_size} 字节，"
                    f"实际为 {self._download_written} 字节。"
                )
            elif self._download_hash.hexdigest().casefold() != manifest.sha256:
                failure = "安装包 SHA-256 校验失败，已删除损坏文件。"

        self._download_reply = None
        self._download_file = None
        self._download_manifest = None
        self._download_target = None
        self._download_failure = ""
        self._download_cancel_requested = False
        reply.deleteLater()

        if cancelled or failure or manifest is None or save_file is None or target is None:
            if save_file is not None:
                _dispose_save_file(save_file, cancel=True)
            self._delete_update_file(target)
            if self._shutting_down:
                return
            if cancelled:
                self.downloadCancelled.emit()
            else:
                self.downloadFailed.emit(failure or "安装包下载未能完成。")
            return

        if not save_file.commit():
            message = f"提交更新文件失败：{save_file.errorString()}"
            _dispose_save_file(save_file)
            self._delete_update_file(target)
            if not self._shutting_down:
                self.downloadFailed.emit(message)
            return
        _dispose_save_file(save_file)
        try:
            verify_installer_file(target, manifest)
        except UpdateValidationError as error:
            self._delete_update_file(target)
            if not self._shutting_down:
                self.downloadFailed.emit(str(error))
            return
        self._verified_manifest = manifest
        self._verified_path = target
        if not self._shutting_down:
            self.downloadVerified.emit(manifest, str(target))

    def launch_verified_installer(self) -> bool:
        manifest = self._verified_manifest
        path = self._verified_path
        if manifest is None or path is None:
            self.installerLaunchFailed.emit("安装包尚未完成校验，不能启动安装。")
            return False
        try:
            verify_installer_file(path, manifest)
        except UpdateValidationError as error:
            self._verified_manifest = None
            self._verified_path = None
            self._delete_update_file(path)
            self.installerLaunchFailed.emit(str(error))
            return False
        try:
            result = self._installer_launcher(
                str(path),
                list(self.INSTALLER_ARGUMENTS),
            )
            started = bool(result[0]) if isinstance(result, tuple) else bool(result)
        except Exception as error:
            self.installerLaunchFailed.emit(f"无法启动安装程序：{error}")
            return False
        if not started:
            self.installerLaunchFailed.emit("Windows 未能启动安装程序，HushPlayer 将继续运行。")
            return False
        self.installerLaunched.emit(str(path))
        return True

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._check_timer.stop()
        self._download_timer.stop()
        check_reply = self._check_reply
        self._check_reply = None
        if check_reply is not None:
            check_reply.abort()
            check_reply.deleteLater()
        download_reply = self._download_reply
        self._download_reply = None
        if download_reply is not None:
            download_reply.abort()
            download_reply.deleteLater()
        save_file = self._download_file
        self._download_file = None
        if save_file is not None:
            _dispose_save_file(save_file, cancel=True)
        self._delete_update_file(self._download_target)
        self._download_manifest = None
        self._download_target = None

    def _response_failure(
        self,
        reply: QNetworkReply,
        *,
        expected_status: int,
        allow_redirect: bool = False,
    ) -> str:
        try:
            validate_update_url(
                reply.url().toString(),
                allow_insecure_localhost=self.allow_insecure_localhost,
            )
        except UpdateValidationError:
            return "更新请求被重定向到了不安全的地址。"
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        try:
            status_code = int(status or 0)
        except (TypeError, ValueError):
            status_code = 0
        if allow_redirect and 300 <= status_code < 400:
            return ""
        if status_code and status_code != expected_status:
            return f"更新服务器返回 HTTP {status_code}。"
        return ""

    def _delete_update_file(self, path: Path | None) -> None:
        if path is None:
            return
        try:
            root = self.updates_dir.expanduser().resolve()
            candidate = path.resolve()
            candidate.relative_to(root)
            if _UPDATE_FILENAME_PATTERN.fullmatch(candidate.name) and candidate.is_file():
                candidate.unlink()
        except (OSError, ValueError):
            return
