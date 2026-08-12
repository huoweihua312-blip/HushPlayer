from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
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
    APP_NUMERIC_VERSION,
    APP_USER_AGENT,
    UPDATE_ARCHITECTURE,
    UPDATE_CHANNEL,
    UPDATE_MANIFEST_URL,
    UPDATE_MANIFEST_SOURCES,
    is_newer_numeric_version,
    parse_numeric_version,
)


SUPPORTED_MANIFEST_SCHEMA = 1
MAX_MANIFEST_BYTES = 128 * 1024
MIN_SETUP_BYTES = 1024
MAX_SETUP_BYTES = 512 * 1024 * 1024
MIN_PACKAGE_BYTES = 1024
MAX_PACKAGE_BYTES = 1024 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 20_000
MAX_PACKAGE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_RELEASE_HISTORY_ENTRIES = 50
MAX_RELEASE_NOTES = 50

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_RELEASE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-"
    r"([a-z][a-z0-9-]*)\.(0|[1-9]\d*)$"
)
_UPDATE_FILENAME_PATTERN = re.compile(
    r"^HushPlayer-[0-9A-Za-z.-]+-win-x64-setup\.exe(?:\..+)?$"
)
_PACKAGE_FILENAME_PATTERN = re.compile(
    r"^HushPlayer-[0-9A-Za-z.-]+-win-x64-update\.zip$"
)
_UPDATER_COPY_PATTERN = re.compile(r"^HushPlayerUpdater-\d+-\d+\.exe$")
_LOGGER = logging.getLogger(__name__)


class UpdateValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UpdateReleaseNotesSection:
    """One version's plain-text release notes for the update prompt."""

    version: str
    numeric_version: tuple[int, int, int, int]
    numeric_version_text: str
    release_date: str | None
    notes: tuple[str, ...]


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
    release_history: tuple[UpdateReleaseNotesSection, ...]
    package_url: str | None = None
    package_size: int | None = None
    package_sha256: str | None = None
    package_filename: str | None = None

    @property
    def is_newer(self) -> bool:
        return is_newer_numeric_version(self.numeric_version)

    @property
    def installer_filename(self) -> str:
        return f"HushPlayer-{self.version}-{self.architecture}-setup.exe"

    @property
    def has_in_app_package(self) -> bool:
        return all(
            value is not None
            for value in (
                self.package_url,
                self.package_size,
                self.package_sha256,
                self.package_filename,
            )
        )

    @property
    def download_url(self) -> str:
        return self.package_url if self.has_in_app_package else self.setup_url  # type: ignore[return-value]

    @property
    def download_size(self) -> int:
        return self.package_size if self.has_in_app_package else self.setup_size  # type: ignore[return-value]

    @property
    def download_sha256(self) -> str:
        return self.package_sha256 if self.has_in_app_package else self.sha256  # type: ignore[return-value]

    @property
    def download_filename(self) -> str:
        return self.package_filename if self.has_in_app_package else self.installer_filename  # type: ignore[return-value]


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


def _parse_release_notes(
    raw_release_notes: object,
    *,
    label: str = "更新说明",
) -> tuple[str, ...]:
    if not isinstance(raw_release_notes, list) or len(raw_release_notes) > MAX_RELEASE_NOTES:
        raise UpdateValidationError(f"{label}必须是最多 50 项的字符串数组。")
    release_notes: list[str] = []
    for note in raw_release_notes:
        if not isinstance(note, str):
            raise UpdateValidationError(f"{label}中的每一项都必须是字符串。")
        normalized = note.strip()
        if not normalized or len(normalized) > 1000:
            raise UpdateValidationError(f"{label}包含空白或过长内容。")
        release_notes.append(normalized)
    return tuple(release_notes)


def _parse_release_history_entry(
    raw_entry: object,
    *,
    channel: str,
) -> UpdateReleaseNotesSection:
    if not isinstance(raw_entry, dict):
        raise UpdateValidationError("历史版本条目必须是 JSON 对象。")

    version = str(raw_entry.get("version") or "").strip()
    version_match = _VERSION_PATTERN.fullmatch(version)
    if version_match is None or len(version) > 64:
        raise UpdateValidationError("历史版本条目的 version 格式无效。")
    version_major, version_minor, version_patch, version_channel, version_sequence = (
        version_match.groups()
    )
    if version_channel != channel:
        raise UpdateValidationError("历史版本条目的 channel 与更新清单不一致。")

    try:
        numeric_version = parse_numeric_version(
            str(raw_entry.get("numeric_version") or "")
        )
    except ValueError as error:
        raise UpdateValidationError("历史版本条目的 numeric_version 无效。") from error
    label_numeric = (
        int(version_major),
        int(version_minor),
        int(version_patch),
        int(version_sequence),
    )
    if numeric_version != label_numeric:
        raise UpdateValidationError(
            "历史版本条目的 version 与 numeric_version 不一致。"
        )

    release_date = str(raw_entry.get("release_date") or "").strip()
    if _RELEASE_DATE_PATTERN.fullmatch(release_date) is None:
        raise UpdateValidationError("历史版本条目的 release_date 格式无效。")
    try:
        if date.fromisoformat(release_date).isoformat() != release_date:
            raise ValueError(release_date)
    except ValueError as error:
        raise UpdateValidationError("历史版本条目的 release_date 无效。") from error

    return UpdateReleaseNotesSection(
        version=version,
        numeric_version=numeric_version,
        numeric_version_text=".".join(str(part) for part in numeric_version),
        release_date=release_date,
        notes=_parse_release_notes(
            raw_entry.get("notes"),
            label="历史版本更新说明",
        ),
    )


def _parse_release_history(
    raw_release_history: object,
    *,
    channel: str,
) -> tuple[UpdateReleaseNotesSection, ...]:
    """Best-effort optional history parsing; invalid entries never block updates."""

    if raw_release_history is None:
        return ()
    if not isinstance(raw_release_history, list):
        _LOGGER.warning("Ignoring invalid release_history: it must be a JSON array.")
        return ()
    if len(raw_release_history) > MAX_RELEASE_HISTORY_ENTRIES:
        _LOGGER.warning(
            "release_history has %s entries; only the first %s are considered.",
            len(raw_release_history),
            MAX_RELEASE_HISTORY_ENTRIES,
        )

    history: list[UpdateReleaseNotesSection] = []
    seen_versions: set[tuple[int, int, int, int]] = set()
    for index, raw_entry in enumerate(raw_release_history[:MAX_RELEASE_HISTORY_ENTRIES]):
        try:
            entry = _parse_release_history_entry(raw_entry, channel=channel)
        except UpdateValidationError as error:
            _LOGGER.warning(
                "Ignoring invalid release_history entry %s: %s",
                index,
                error,
            )
            continue
        if entry.numeric_version in seen_versions:
            _LOGGER.warning(
                "Ignoring duplicate release_history entry %s for %s.",
                index,
                entry.numeric_version_text,
            )
            continue
        seen_versions.add(entry.numeric_version)
        history.append(entry)
    return tuple(sorted(history, key=lambda item: item.numeric_version))


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

    release_notes = _parse_release_notes(document.get("release_notes", []))
    release_history = _parse_release_history(
        document.get("release_history"),
        channel=channel,
    )

    package_fields = (
        "package_url",
        "package_size",
        "package_sha256",
        "package_filename",
    )
    package_present = [field for field in package_fields if field in document]
    package_url: str | None = None
    package_size: int | None = None
    package_sha256: str | None = None
    package_filename: str | None = None
    if package_present:
        if len(package_present) != len(package_fields):
            raise UpdateValidationError(
                "应用内更新包字段必须同时提供 package_url、package_size、"
                "package_sha256 和 package_filename。"
            )
        package_url = validate_update_url(
            document["package_url"],
            allow_insecure_localhost=allow_insecure_localhost,
        )
        package_size_value = document["package_size"]
        if (
            isinstance(package_size_value, bool)
            or not isinstance(package_size_value, int)
            or not MIN_PACKAGE_BYTES <= package_size_value <= MAX_PACKAGE_BYTES
        ):
            raise UpdateValidationError(
                "应用内更新包大小必须在 1 KB 到 1 GB 之间。"
            )
        package_size = package_size_value
        package_sha256_value = str(document["package_sha256"] or "").strip().casefold()
        if _SHA256_PATTERN.fullmatch(package_sha256_value) is None:
            raise UpdateValidationError("应用内更新包 SHA-256 必须是 64 位十六进制。")
        package_sha256 = package_sha256_value
        package_filename_value = str(document["package_filename"] or "").strip()
        expected_package_filename = (
            f"HushPlayer-{version}-{architecture}-update.zip"
        )
        if package_filename_value != expected_package_filename or not _PACKAGE_FILENAME_PATTERN.fullmatch(
            package_filename_value
        ):
            raise UpdateValidationError(
                "应用内更新包文件名与当前版本或架构不一致。"
            )
        package_filename = package_filename_value

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
        release_notes=release_notes,
        release_history=release_history,
        package_url=package_url,
        package_size=package_size,
        package_sha256=package_sha256,
        package_filename=package_filename,
    )


def select_update_release_notes(
    manifest: UpdateManifest,
    *,
    current_numeric_version: str | Sequence[int] = APP_NUMERIC_VERSION,
) -> tuple[UpdateReleaseNotesSection, ...]:
    """Select ordered history, adding legacy target notes when history is incomplete."""

    current = parse_numeric_version(current_numeric_version)
    if not is_newer_numeric_version(manifest.numeric_version, current):
        return ()

    fallback = UpdateReleaseNotesSection(
        version=manifest.version,
        numeric_version=manifest.numeric_version,
        numeric_version_text=manifest.numeric_version_text,
        release_date=None,
        notes=manifest.release_notes,
    )
    matching_history = tuple(
        entry
        for entry in manifest.release_history
        if current < entry.numeric_version <= manifest.numeric_version
    )
    if matching_history:
        if matching_history[-1].numeric_version == manifest.numeric_version:
            return matching_history
        return matching_history + (fallback,)
    return (fallback,)


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


def verify_update_package(path: str | Path, manifest: UpdateManifest) -> None:
    if not manifest.has_in_app_package:
        raise UpdateValidationError("当前更新清单没有可用的应用内更新包。")
    candidate = Path(path)
    try:
        if not candidate.is_file():
            raise UpdateValidationError("已下载的应用内更新包不存在。")
        actual_size = candidate.stat().st_size
    except OSError as error:
        raise UpdateValidationError(f"无法读取已下载的应用内更新包：{error}") from error
    if actual_size != manifest.package_size:
        raise UpdateValidationError(
            f"应用内更新包大小校验失败：应为 {manifest.package_size} 字节，"
            f"实际为 {actual_size} 字节。"
        )

    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise UpdateValidationError(
            f"无法校验已下载的应用内更新包：{error}"
        ) from error
    if digest.hexdigest().casefold() != manifest.package_sha256:
        raise UpdateValidationError("应用内更新包 SHA-256 校验失败，文件可能已损坏。")

    try:
        with zipfile.ZipFile(candidate) as archive:
            members = archive.infolist()
            if len(members) > MAX_PACKAGE_MEMBERS:
                raise UpdateValidationError("应用内更新包包含过多文件。")
            total_uncompressed = 0
            names: set[str] = set()
            for member in members:
                name = str(member.filename or "")
                normalized = name.replace("\\", "/").rstrip("/")
                path_parts = normalized.split("/")
                if (
                    not normalized
                    or "\x00" in normalized
                    or normalized.startswith("/")
                    or Path(normalized).drive
                    or any(part in {"", ".", ".."} for part in path_parts)
                    or normalized in names
                ):
                    raise UpdateValidationError(
                        "应用内更新包包含不安全或重复的文件路径。"
                    )
                names.add(normalized)
                mode = (member.external_attr >> 16) & 0o170000
                if member.create_system == 3 and mode == stat.S_IFLNK:
                    raise UpdateValidationError("应用内更新包不允许包含符号链接。")
                total_uncompressed += max(0, int(member.file_size))
                if total_uncompressed > MAX_PACKAGE_UNCOMPRESSED_BYTES:
                    raise UpdateValidationError("应用内更新包解压后超过安全大小限制。")
            required = {"HushPlayer.exe", "HushPlayerUpdater.exe"}
            if not required.issubset(names):
                missing = ", ".join(sorted(required - names))
                raise UpdateValidationError(
                    f"应用内更新包缺少必要文件：{missing}。"
                )
    except zipfile.BadZipFile as error:
        raise UpdateValidationError("应用内更新包不是有效的 ZIP 文件。") from error
    except OSError as error:
        raise UpdateValidationError(f"无法读取应用内更新包：{error}") from error


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
    updaterLaunched = Signal(str)

    CHECK_TRANSFER_TIMEOUT_MS = 8_000
    # Leave a small guard interval after Qt's transfer timeout so the two
    # independent abort paths cannot race for the same reply.
    CHECK_TOTAL_TIMEOUT_MS = 9_000
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
        manifest_url: str | None = None,
        manifest_sources: Sequence[tuple[str, str]] | None = None,
        updates_dir: str | Path | None = None,
        allow_insecure_localhost: bool = False,
        installer_launcher: Callable[[str, list[str]], object] | None = None,
        updater_launcher: Callable[[str, list[str]], object] | None = None,
        application_dir: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        configured_sources: Sequence[object]
        if manifest_url is not None:
            configured_sources = (("自定义更新源", str(manifest_url)),)
        elif manifest_sources is not None:
            configured_sources = manifest_sources
        else:
            configured_sources = UPDATE_MANIFEST_SOURCES
        self.manifest_sources = self._normalize_manifest_sources(configured_sources)
        self.manifest_url = (
            self.manifest_sources[0][1]
            if self.manifest_sources
            else UPDATE_MANIFEST_URL
        )
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
        self._updater_launcher = updater_launcher or _start_detached_installer
        self._application_dir_override = (
            Path(application_dir).expanduser().resolve()
            if application_dir is not None
            else None
        )
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._on_check_timeout)
        self._check_retry_timer = QTimer(self)
        self._check_retry_timer.setSingleShot(True)
        self._check_retry_timer.timeout.connect(self._start_next_manifest_source)
        self._download_timer = QTimer(self)
        self._download_timer.setSingleShot(True)
        self._download_timer.timeout.connect(self._on_download_timeout)

        self._check_reply: QNetworkReply | None = None
        self._check_active = False
        self._check_manual = False
        self._check_source_index = -1
        self._check_source_name = ""
        self._last_successful_manifest_source: str | None = None
        self._manifest_buffer = bytearray()
        self._check_failure = ""
        self._download_reply: QNetworkReply | None = None
        self._download_file: QSaveFile | None = None
        self._download_manifest: UpdateManifest | None = None
        self._download_target: Path | None = None
        self._download_hash = hashlib.sha256()
        self._download_prefix = bytearray()
        self._download_written = 0
        self._download_kind = ""
        self._download_expected_size = 0
        self._download_expected_sha256 = ""
        self._download_expected_prefix = b""
        self._download_failure = ""
        self._download_cancel_requested = False
        self._verified_manifest: UpdateManifest | None = None
        self._verified_path: Path | None = None
        self._shutting_down = False

    @property
    def is_checking(self) -> bool:
        return self._check_active

    @property
    def is_downloading(self) -> bool:
        return self._download_reply is not None

    @property
    def verified_manifest(self) -> UpdateManifest | None:
        return self._verified_manifest

    @property
    def verified_path(self) -> Path | None:
        return self._verified_path

    @staticmethod
    def _normalize_manifest_sources(
        sources: Sequence[object],
    ) -> tuple[tuple[str, str], ...]:
        normalized: list[tuple[str, str]] = []
        for index, source in enumerate(sources):
            if isinstance(source, (tuple, list)) and len(source) == 2:
                name = str(source[0] or "").strip() or f"更新源 {index + 1}"
                url = str(source[1] or "").strip()
            else:
                name = f"更新源 {index + 1}"
                url = ""
            normalized.append((name, url))
        return tuple(normalized)

    def _build_manifest_request(self, url: str) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setAttribute(
            QNetworkRequest.Attribute.Http2AllowedAttribute,
            False,
        )
        request.setTransferTimeout(self.CHECK_TRANSFER_TIMEOUT_MS)
        request.setRawHeader(b"User-Agent", f"{APP_USER_AGENT} updater".encode("ascii"))
        request.setRawHeader(b"Accept", b"application/json")
        return request

    def check_for_updates(self, *, manual: bool) -> bool:
        if self._shutting_down or self.is_checking or self.is_downloading:
            return False
        self._check_active = True
        self._check_manual = bool(manual)
        self._check_source_index = -1
        self._check_source_name = ""
        self._last_successful_manifest_source = None
        self._manifest_buffer.clear()
        self._check_failure = ""
        self.checkStarted.emit(bool(manual))
        self._start_next_manifest_source()
        return True

    def _start_next_manifest_source(self) -> None:
        if self._shutting_down or not self._check_active:
            return
        self._check_retry_timer.stop()
        while self._check_source_index + 1 < len(self.manifest_sources):
            self._check_source_index += 1
            source_name, source_url = self.manifest_sources[self._check_source_index]
            try:
                url = validate_update_url(
                    source_url,
                    allow_insecure_localhost=self.allow_insecure_localhost,
                )
            except UpdateValidationError as error:
                self._record_manifest_source_failure(source_name, str(error))
                continue

            self._check_source_name = source_name
            if self._check_source_index > 0:
                print(f"正在尝试备用更新源：{source_name}")
            self._manifest_buffer.clear()
            self._check_failure = ""
            reply = self.network.get(self._build_manifest_request(url))
            self._check_reply = reply
            reply.readyRead.connect(
                lambda current=reply: self._read_manifest_data(current)
            )
            reply.downloadProgress.connect(
                lambda received, total, current=reply: self._guard_manifest_size(
                    current,
                    received,
                    total,
                )
            )
            reply.finished.connect(lambda current=reply: self._finish_check(current))
            self._check_timer.start(self.CHECK_TOTAL_TIMEOUT_MS)
            return
        self._complete_check_failure()

    def _record_manifest_source_failure(self, source_name: str, reason: str) -> None:
        _LOGGER.warning("%s 更新清单请求失败：%s", source_name, reason)

    def _queue_next_manifest_source(self) -> None:
        """Yield after a reply finishes before creating the fallback request."""

        if self._shutting_down or not self._check_active:
            return
        self._check_retry_timer.start(0)

    def _clear_check_attempt(self) -> bool:
        if not self._check_active:
            return False
        self._check_active = False
        self._check_timer.stop()
        self._check_retry_timer.stop()
        self._check_reply = None
        self._check_source_name = ""
        self._manifest_buffer.clear()
        self._check_failure = ""
        return True

    def _complete_check_failure(self) -> None:
        if self._shutting_down or not self._clear_check_attempt():
            return
        manual = self._check_manual
        self.checkCompleted.emit()
        self.checkFailed.emit("检查更新失败，请检查网络连接后重试。", manual)

    def _complete_check_success(self, manifest: UpdateManifest) -> None:
        if self._shutting_down or not self._clear_check_attempt():
            return
        manual = self._check_manual
        self.checkCompleted.emit()
        if manifest.is_newer:
            self.updateAvailable.emit(manifest, manual)
        else:
            self.noUpdate.emit(manual)

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
        if reply is None or not self._check_active:
            return
        self._check_failure = "检查更新超时，请稍后重试。"
        reply.abort()

    def _finish_check(self, reply: QNetworkReply) -> None:
        if reply is not self._check_reply:
            reply.deleteLater()
            return
        self._read_manifest_data(reply)
        self._check_timer.stop()
        source_name = self._check_source_name
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
        if failure:
            self._record_manifest_source_failure(source_name, failure)
            self._queue_next_manifest_source()
            return
        try:
            manifest = parse_update_manifest(
                payload,
                allow_insecure_localhost=self.allow_insecure_localhost,
            )
        except UpdateValidationError as error:
            self._record_manifest_source_failure(source_name, str(error))
            self._queue_next_manifest_source()
            return
        self._last_successful_manifest_source = source_name
        print(f"更新清单获取成功：{source_name}")
        self._complete_check_success(manifest)

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
                manifest.download_url,
                allow_insecure_localhost=self.allow_insecure_localhost,
            )
            target = self._prepare_download_target(manifest.download_filename)
        except (OSError, UpdateValidationError) as error:
            self.downloadFailed.emit(f"无法准备更新下载：{error}")
            return False

        save_file = QSaveFile(str(target))
        save_file.setDirectWriteFallback(False)
        if not save_file.open(QIODevice.OpenModeFlag.WriteOnly):
            self.downloadFailed.emit(f"无法创建更新临时文件：{save_file.errorString()}")
            _dispose_save_file(save_file)
            return False

        request = QNetworkRequest(QUrl(manifest.download_url))
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
        self._download_kind = "package" if manifest.has_in_app_package else "installer"
        self._download_expected_size = manifest.download_size
        self._download_expected_sha256 = manifest.download_sha256
        self._download_expected_prefix = b"PK" if manifest.has_in_app_package else b"MZ"
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

    def _prepare_download_target(self, filename: str) -> Path:
        root = self.updates_dir.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.cleanup_stale_updates()
        target = (root / filename).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise UpdateValidationError("更新文件路径超出专用临时目录。") from error
        if not (
            _UPDATE_FILENAME_PATTERN.fullmatch(target.name)
            or _PACKAGE_FILENAME_PATTERN.fullmatch(target.name)
        ):
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
                or not (
                    _UPDATE_FILENAME_PATTERN.fullmatch(candidate.name)
                    or _PACKAGE_FILENAME_PATTERN.fullmatch(candidate.name)
                    or _UPDATER_COPY_PATTERN.fullmatch(candidate.name)
                )
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
            if declared_size != self._download_expected_size:
                self._download_failure = "服务器返回的更新文件大小与更新清单不一致。"
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
            self._download_failure = "服务器返回的不是有效更新文件。"
            reply.abort()

    def _read_download_data(self, reply: QNetworkReply) -> None:
        if reply is not self._download_reply or self._download_failure:
            return
        self._validate_download_response(reply)
        save_file = self._download_file
        if self._download_failure or save_file is None:
            return
        data = bytes(reply.readAll())
        if not data:
            return
        if len(self._download_prefix) < 2:
            needed = 2 - len(self._download_prefix)
            self._download_prefix.extend(data[:needed])
            if (
                len(self._download_prefix) == 2
                and self._download_prefix != self._download_expected_prefix
            ):
                self._download_failure = "下载内容不是有效的 HushPlayer 更新文件。"
                reply.abort()
                return
        if self._download_written + len(data) > self._download_expected_size:
            self._download_failure = "下载内容超过更新清单声明的大小。"
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
        if not self._download_expected_size:
            return
        max_allowed = (
            MAX_PACKAGE_BYTES
            if self._download_kind == "package"
            else MAX_SETUP_BYTES
        )
        if received > self._download_expected_size or total > max_allowed:
            self._download_failure = "更新文件下载大小超过安全限制。"
            reply.abort()
            return
        self.downloadProgress.emit(max(0, int(received)), self._download_expected_size)

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
        self._download_failure = "更新文件下载超时，请稍后重试。"
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
            failure = f"更新文件下载失败：{reply.errorString()}"
        if not cancelled and not failure and manifest is not None:
            if self._download_written != self._download_expected_size:
                failure = (
                    f"更新文件大小校验失败：应为 {self._download_expected_size} 字节，"
                    f"实际为 {self._download_written} 字节。"
                )
            elif self._download_hash.hexdigest().casefold() != self._download_expected_sha256:
                failure = "更新文件 SHA-256 校验失败，已删除损坏文件。"

        self._download_reply = None
        self._download_file = None
        self._download_manifest = None
        self._download_target = None
        self._download_failure = ""
        self._download_cancel_requested = False
        download_kind = self._download_kind
        self._download_kind = ""
        self._download_expected_size = 0
        self._download_expected_sha256 = ""
        self._download_expected_prefix = b""
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
                self.downloadFailed.emit(failure or "更新文件下载未能完成。")
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
            if download_kind == "package":
                verify_update_package(target, manifest)
            else:
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

    def _application_install_dir(self) -> Path:
        if self._application_dir_override is not None:
            return self._application_dir_override
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[2]

    def launch_verified_update(self) -> bool:
        manifest = self._verified_manifest
        path = self._verified_path
        if manifest is None or path is None:
            self.installerLaunchFailed.emit("更新文件尚未完成校验，不能启动更新。")
            return False
        if not manifest.has_in_app_package:
            return self.launch_verified_installer()
        helper_copy: Path | None = None
        try:
            verify_update_package(path, manifest)
            install_dir = self._application_install_dir()
            helper_source = install_dir / "HushPlayerUpdater.exe"
            if not helper_source.is_file():
                raise UpdateValidationError(
                    "当前程序缺少应用内更新助手，请改用安装包方式更新。"
                )
            self.updates_dir.mkdir(parents=True, exist_ok=True)
            helper_copy = self.updates_dir / (
                f"HushPlayerUpdater-{os.getpid()}-{time.time_ns()}.exe"
            )
            shutil.copy2(helper_source, helper_copy)
            arguments = [
                "--parent-pid",
                str(os.getpid()),
                "--install-dir",
                str(install_dir),
                "--package",
                str(path),
                "--restart-exe",
                str(install_dir / "HushPlayer.exe"),
                "--cleanup-helper",
                str(helper_copy),
            ]
            result = self._updater_launcher(str(helper_copy), arguments)
            started = bool(result[0]) if isinstance(result, tuple) else bool(result)
        except (OSError, UpdateValidationError) as error:
            if helper_copy is not None:
                self._delete_update_file(helper_copy)
            self.installerLaunchFailed.emit(str(error))
            return False
        except Exception as error:
            if helper_copy is not None:
                self._delete_update_file(helper_copy)
            self.installerLaunchFailed.emit(f"无法启动应用内更新助手：{error}")
            return False
        if not started:
            try:
                helper_copy.unlink(missing_ok=True)
            except OSError:
                pass
            self.installerLaunchFailed.emit(
                "Windows 未能启动应用内更新助手，HushPlayer 将继续运行。"
            )
            return False
        self.updaterLaunched.emit(str(helper_copy))
        return True

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
        self._check_active = False
        self._check_timer.stop()
        self._check_retry_timer.stop()
        self._download_timer.stop()
        check_reply = self._check_reply
        self._check_reply = None
        self._check_source_name = ""
        self._manifest_buffer.clear()
        self._check_failure = ""
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
        self._download_kind = ""
        self._download_expected_size = 0
        self._download_expected_sha256 = ""
        self._download_expected_prefix = b""

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
            if (
                _UPDATE_FILENAME_PATTERN.fullmatch(candidate.name)
                or _PACKAGE_FILENAME_PATTERN.fullmatch(candidate.name)
                or _UPDATER_COPY_PATTERN.fullmatch(candidate.name)
            ) and candidate.is_file():
                candidate.unlink()
        except (OSError, ValueError):
            return
