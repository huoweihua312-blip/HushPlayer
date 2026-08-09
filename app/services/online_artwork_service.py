from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.core.version import APP_USER_AGENT


class OnlineArtworkService(QObject):
    """Asynchronously fetch and cache keyed online covers."""

    imageReady = Signal(int, str, bytes)
    failed = Signal(int, str, str)

    def __init__(self, cache_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_dir = Path(cache_dir)
        self.network = QNetworkAccessManager(self)
        self._generation = 0
        self._replies: dict[QNetworkReply, tuple[int, str, Path]] = {}

    @property
    def generation(self) -> int:
        return self._generation

    def request(self, track_key: str, url_text: str) -> int:
        return self.request_many(((track_key, url_text),))

    def request_many(self, requests) -> int:
        """Start one bounded batch whose results retain their row keys."""

        self.cancel()
        self._generation += 1
        generation = self._generation
        for raw in requests or ():
            try:
                track_key, url_text = raw
            except (TypeError, ValueError):
                continue
            track_key = str(track_key or "")
            url = QUrl(str(url_text or ""))
            if not url.isValid() or url.scheme().lower() not in {"http", "https"}:
                self.failed.emit(generation, track_key, "没有可用的在线封面")
                continue
            digest = hashlib.sha256(url.toString().encode("utf-8")).hexdigest()
            cache_path = self.cache_dir / f"{digest}.img"
            if cache_path.is_file():
                try:
                    data = cache_path.read_bytes()
                except OSError:
                    data = b""
                if data and not QImage.fromData(data).isNull():
                    self.imageReady.emit(generation, track_key, data)
                    continue
            request = QNetworkRequest(url)
            request.setRawHeader(
                b"User-Agent",
                f"{APP_USER_AGENT} (artwork client)".encode("ascii"),
            )
            reply = self.network.get(request)
            reply.finished.connect(lambda current=reply: self._finish(current))
            self._replies[reply] = (generation, track_key, cache_path)
        return generation

    def cancel(self) -> None:
        replies = list(self._replies)
        self._replies.clear()
        for reply in replies:
            reply.abort()
            reply.deleteLater()

    def _finish(self, reply: QNetworkReply) -> None:
        context = self._replies.pop(reply, None)
        if context is None:
            reply.deleteLater()
            return
        generation, track_key, cache_path = context
        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = reply.errorString() or "在线封面加载失败"
            reply.deleteLater()
            self.failed.emit(generation, track_key, message)
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if (
            not data
            or len(data) > 12 * 1024 * 1024
            or QImage.fromData(data).isNull()
        ):
            self.failed.emit(generation, track_key, "在线封面内容无效")
            return
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(cache_path)
        except OSError:
            pass
        self.imageReady.emit(generation, track_key, data)
