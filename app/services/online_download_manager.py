from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QIODevice, QObject, QSaveFile, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class OnlineDownloadManager(QObject):
    """Download one validated public media resource at a time."""

    started = Signal(str)
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
    AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus", ".aac"}
    ALLOWED_HEADERS = {
        "user-agent": "User-Agent",
        "referer": "Referer",
        "origin": "Origin",
        "accept": "Accept",
        "accept-language": "Accept-Language",
        "range": "Range",
    }
    MIME_EXTENSIONS = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mp4": ".m4a",
        "video/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "application/ogg": ".ogg",
        "audio/opus": ".opus",
        "audio/aac": ".aac",
    }
    REJECTED_CONTENT_TYPES = {
        "text/html",
        "application/xhtml+xml",
        "application/json",
        "text/json",
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._file: QSaveFile | None = None
        self._target_path = ""
        self._requested_target_path = ""
        self._resolution: dict = {}
        self._content_type = ""
        self._written = 0
        self._failure = ""

    def is_active(self) -> bool:
        return self._reply is not None

    def start_download(self, resolution: dict, target_path: str) -> bool:
        if self.is_active():
            self.failed.emit("已有在线下载正在进行，请等待完成或先取消。")
            return False

        try:
            url, headers = self.validate_resolution(resolution)
        except ValueError as error:
            self.failed.emit(str(error))
            return False

        target = Path(target_path)
        if not target.name or not target.parent.exists():
            self.failed.emit("保存位置不存在，请重新选择。")
            return False

        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        for name, value in headers.items():
            request.setRawHeader(name.encode("ascii"), value.encode("utf-8"))
        reply = self.network.get(request)
        self._reply = reply
        self._file = None
        self._requested_target_path = str(target)
        self._target_path = str(target)
        self._resolution = dict(resolution)
        self._content_type = ""
        self._written = 0
        self._failure = ""
        reply.metaDataChanged.connect(self._validate_response)
        reply.readyRead.connect(self._read_available)
        reply.downloadProgress.connect(self._on_progress)
        reply.finished.connect(self._on_finished)
        self.started.emit(self._target_path)
        return True

    @classmethod
    def validate_resolution(cls, resolution: dict) -> tuple[str, dict[str, str]]:
        if not isinstance(resolution, dict):
            raise ValueError("下载资源信息无效。")
        url = str(resolution.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("下载地址无效，仅支持 HTTP 或 HTTPS。")
        if parsed.username or parsed.password:
            raise ValueError("下载地址不允许包含用户名或密码。")
        raw_headers = resolution.get("headers") or {}
        if not isinstance(raw_headers, dict):
            raise ValueError("下载请求头必须是对象。")

        headers: dict[str, str] = {}
        token_pattern = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
        for raw_name, raw_value in raw_headers.items():
            name = str(raw_name or "").strip()
            value = str(raw_value or "")
            if not name or not token_pattern.fullmatch(name):
                raise ValueError("下载请求包含非法 header 名称。")
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise ValueError("下载请求头不允许包含换行字符。")
            normalized_name = name.casefold()
            canonical_name = cls.ALLOWED_HEADERS.get(normalized_name)
            if canonical_name is None:
                raise ValueError(f"下载请求头不受支持：{name}")
            if normalized_name == "range" and value.strip().casefold() != "bytes=0-":
                raise ValueError("下载 Range 仅允许完整资源请求 bytes=0-。")
            headers[canonical_name] = value
        return url, headers

    @classmethod
    def suggest_filename(cls, resolution: dict, fallback_stem: str) -> str:
        filename = cls._safe_filename(str(resolution.get("filename") or ""))
        if filename:
            return filename
        url_name = cls._safe_filename(Path(urlparse(str(resolution.get("url") or "")).path).name)
        if Path(url_name).suffix.lower() in cls.AUDIO_EXTENSIONS:
            return url_name
        mime_type = str(resolution.get("mimeType") or "").split(";", 1)[0].strip().casefold()
        suffix = cls.MIME_EXTENSIONS.get(mime_type, "")
        stem = cls._safe_filename(fallback_stem) or "online_track"
        return f"{Path(stem).stem}{suffix}" if suffix else Path(stem).stem

    def cancel(self) -> None:
        if self._reply is None:
            return
        self._failure = "下载已取消。"
        self._reply.abort()

    def _validate_response(self) -> None:
        if self._reply is None or self._failure:
            return
        reply = self._reply
        final_url = urlparse(reply.url().toString())
        if final_url.scheme not in {"http", "https"} or final_url.username or final_url.password:
            self._failure = "下载重定向返回了不安全的地址。"
            reply.abort()
            return

        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        try:
            status_code = int(status or 0)
        except (TypeError, ValueError):
            status_code = 0
        if status_code and status_code not in {200, 206}:
            if 300 <= status_code < 400:
                return
            self._failure = f"下载失败：HTTP {status_code}。"
            reply.abort()
            return

        content_length = bytes(reply.rawHeader("Content-Length")).decode("ascii", errors="ignore")
        try:
            declared_size = int(content_length or 0)
        except ValueError:
            declared_size = 0
        if declared_size > self.MAX_DOWNLOAD_BYTES:
            self._failure = "下载文件超过 1 GB 安全上限。"
            reply.abort()
            return

        self._content_type = bytes(reply.rawHeader("Content-Type")).decode(
            "latin-1", errors="ignore"
        ).split(";", 1)[0].strip().casefold()
        if self._content_type in self.REJECTED_CONTENT_TYPES or self._content_type.startswith("text/"):
            self._failure = f"服务器返回了 {self._content_type or '非音频'} 内容，已停止保存。"
            reply.abort()
            return

        if self._file is None:
            content_disposition = bytes(reply.rawHeader("Content-Disposition")).decode(
                "latin-1", errors="ignore"
            )
            target = Path(self._requested_target_path)
            if not target.suffix:
                suffix = self._infer_extension(
                    self._resolution,
                    content_disposition,
                    self._content_type,
                    reply.url().toString(),
                )
                if suffix:
                    target = target.with_suffix(suffix)
            save_file = QSaveFile(str(target))
            if not save_file.open(QIODevice.OpenModeFlag.WriteOnly):
                self._failure = f"无法创建下载文件：{save_file.errorString()}"
                reply.abort()
                return
            self._file = save_file
            self._target_path = str(target)

    def _read_available(self) -> None:
        if self._reply is None or self._failure:
            return
        self._validate_response()
        if self._file is None or self._failure:
            return
        chunk = self._reply.readAll()
        size = chunk.size()
        if self._written == 0 and size:
            beginning = bytes(chunk[: min(size, 1024)]).lstrip().lower()
            if beginning.startswith((b"<!doctype html", b"<html", b"<?xml")):
                self._failure = "下载内容实际是 HTML/XML 错误页，已停止保存。"
                self._reply.abort()
                return
        if self._written + size > self.MAX_DOWNLOAD_BYTES:
            self._failure = "下载文件超过 1 GB 安全上限。"
            self._reply.abort()
            return
        written = self._file.write(chunk)
        if written != size:
            self._failure = f"写入下载文件失败：{self._file.errorString()}"
            self._reply.abort()
            return
        self._written += written

    def _on_progress(self, received: int, total: int) -> None:
        if total > self.MAX_DOWNLOAD_BYTES:
            self._failure = "下载文件超过 1 GB 安全上限。"
            if self._reply is not None:
                self._reply.abort()
            return
        self.progress.emit(max(0, int(received)), int(total))

    def _on_finished(self) -> None:
        reply = self._reply
        if reply is None:
            return

        self._validate_response()
        self._read_available()
        if not self._failure and reply.error() != QNetworkReply.NetworkError.NoError:
            self._failure = f"下载失败：{reply.errorString()}"
        save_file = self._file
        if not self._failure and save_file is None:
            self._failure = "下载响应没有可保存的媒体内容。"
        if not self._failure and self._written <= 0:
            self._failure = "音源返回了空文件。"

        target_path = self._target_path
        if self._failure:
            if save_file is not None:
                save_file.cancelWriting()
            message = self._failure
        elif save_file is None:
            message = "下载响应没有可保存的媒体内容。"
        elif not save_file.commit():
            message = f"保存下载文件失败：{save_file.errorString()}"
        else:
            message = ""

        reply.deleteLater()
        if save_file is not None:
            save_file.deleteLater()
        self._reply = None
        self._file = None
        self._target_path = ""
        self._requested_target_path = ""
        self._resolution = {}
        self._content_type = ""
        self._written = 0
        self._failure = ""

        if message:
            self.failed.emit(message)
        else:
            self.finished.emit(target_path)

    @classmethod
    def _infer_extension(
        cls,
        resolution: dict,
        content_disposition: str,
        content_type: str,
        final_url: str,
    ) -> str:
        candidates = [
            str(resolution.get("filename") or ""),
            cls._content_disposition_filename(content_disposition),
        ]
        for candidate in candidates:
            suffix = Path(candidate).suffix.lower()
            if suffix in cls.AUDIO_EXTENSIONS:
                return suffix
        mime_suffix = cls.MIME_EXTENSIONS.get(content_type, "")
        if mime_suffix:
            return mime_suffix
        suffix = Path(urlparse(final_url).path).suffix.lower()
        return suffix if suffix in cls.AUDIO_EXTENSIONS else ""

    @staticmethod
    def _content_disposition_filename(value: str) -> str:
        extended = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", value, re.I)
        if extended:
            return unquote(extended.group(1).strip().strip('"'))
        regular = re.search(r"filename\s*=\s*(?:\"([^\"]+)\"|([^;]+))", value, re.I)
        if not regular:
            return ""
        return (regular.group(1) or regular.group(2) or "").strip()

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = Path(str(value or "")).name
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
