from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QIODevice, QObject, QSaveFile, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class OnlineDownloadManager(QObject):
    """Downloads one explicitly resolved, header-free public media URL at a time."""

    started = Signal(str)
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._file: QSaveFile | None = None
        self._target_path = ""
        self._written = 0
        self._failure = ""

    def is_active(self) -> bool:
        return self._reply is not None

    def start_download(self, resolution: dict, target_path: str) -> bool:
        if self.is_active():
            self.failed.emit("已有在线下载正在进行，请等待完成或先取消。")
            return False

        url = str(resolution.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.failed.emit("下载地址无效，仅支持 HTTP 或 HTTPS。")
            return False
        if resolution.get("headers"):
            self.failed.emit("该音源需要附加请求头，当前下载模式暂不支持。")
            return False

        target = Path(target_path)
        if not target.name or not target.parent.exists():
            self.failed.emit("保存位置不存在，请重新选择。")
            return False

        save_file = QSaveFile(str(target))
        if not save_file.open(QIODevice.OpenModeFlag.WriteOnly):
            self.failed.emit(f"无法创建下载文件：{save_file.errorString()}")
            return False

        request = QNetworkRequest(url)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        reply = self.network.get(request)
        self._reply = reply
        self._file = save_file
        self._target_path = str(target)
        self._written = 0
        self._failure = ""
        reply.readyRead.connect(self._read_available)
        reply.downloadProgress.connect(self._on_progress)
        reply.finished.connect(self._on_finished)
        self.started.emit(self._target_path)
        return True

    def cancel(self) -> None:
        if self._reply is None:
            return
        self._failure = "下载已取消。"
        self._reply.abort()

    def _read_available(self) -> None:
        if self._reply is None or self._file is None or self._failure:
            return
        chunk = self._reply.readAll()
        size = chunk.size()
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
        save_file = self._file
        if reply is None or save_file is None:
            return

        self._read_available()
        if not self._failure and reply.error() != QNetworkReply.NetworkError.NoError:
            self._failure = f"下载失败：{reply.errorString()}"
        if not self._failure and self._written <= 0:
            self._failure = "音源返回了空文件。"

        target_path = self._target_path
        if self._failure:
            save_file.cancelWriting()
            message = self._failure
        elif not save_file.commit():
            message = f"保存下载文件失败：{save_file.errorString()}"
        else:
            message = ""

        reply.deleteLater()
        save_file.deleteLater()
        self._reply = None
        self._file = None
        self._target_path = ""
        self._written = 0
        self._failure = ""

        if message:
            self.failed.emit(message)
        else:
            self.finished.emit(target_path)
