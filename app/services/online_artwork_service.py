from __future__ import annotations

import hashlib
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
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
        self._pending = deque()
        self._pump_timer = QTimer(self)
        self._pump_timer.setSingleShot(True)
        self._pump_timer.timeout.connect(self._pump)

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
        self._pending.extend(requests or ())
        self._pump()
        return generation

    def _pump(self) -> None:
        generation = self._generation
        processed = 0
        # Limit both active downloads and synchronous cache work per event turn.
        while self._pending and len(self._replies) < 4 and processed < 8:
            if generation != self._generation:
                return
            raw = self._pending.popleft()
            processed += 1
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
            cache_path = self.cache_dir / "online" / f"{digest}.img"
            cache_candidates = (
                cache_path,
                self.cache_dir / f"{digest}.img",
            )
            cache_hit = False
            for candidate in cache_candidates:
                try:
                    data = candidate.read_bytes() if candidate.is_file() else b""
                except OSError:
                    data = b""
                if data and not QImage.fromData(data).isNull():
                    self.imageReady.emit(generation, track_key, data)
                    cache_hit = True
                    break
            if cache_hit:
                continue
            request = QNetworkRequest(url)
            request.setTransferTimeout(15_000)
            request.setRawHeader(
                b"User-Agent",
                f"{APP_USER_AGENT} (artwork client)".encode("ascii"),
            )
            reply = self.network.get(request)
            reply.finished.connect(lambda current=reply: self._finish(current))
            self._replies[reply] = (generation, track_key, cache_path)
        if self._pending and len(self._replies) < 4:
            self._pump_timer.start(0)

    def cancel(self) -> None:
        self._pump_timer.stop()
        self._pending.clear()
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
        self._pump_timer.start(0)
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
