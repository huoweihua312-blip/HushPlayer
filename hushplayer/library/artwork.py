"""专辑封面缓存与异步加载。

磁盘层：内容寻址（sha1）的封面文件，位于可重建的缓存目录。
内存层：按 (封面键, 尺寸) 缓存 QPixmap，限制条目数避免长时间运行膨胀。
网络层：在线封面的后台下载（线程池），完成后通过信号通知界面重绘。
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QThreadPool, QRunnable, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap

from ..core import paths
from ..core.logging_setup import get_logger
from ..model.track import Track

log = get_logger("artwork")

_MAX_MEMORY_ENTRIES = 400
_DEFAULT_SIZE = 320


def content_key(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:24]


class ArtworkStore:
    """封面文件的磁盘仓库（内容寻址、幂等写入）。"""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory or paths.artwork_cache_dir())
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def store(self, data: bytes, ext: str = ".jpg") -> str:
        if not data:
            return ""
        ext = (ext or ".jpg").lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            ext = ".jpg"
        key = content_key(data)
        target = self.directory / f"{key}{ext}"
        if target.exists() and target.stat().st_size == len(data):
            return str(target)
        with self._lock:
            tmp = target.with_suffix(target.suffix + ".tmp")
            try:
                tmp.write_bytes(data)
                os.replace(tmp, target)
            except OSError as exc:
                log.warning("写入封面缓存失败 %s: %s", target, exc)
                return ""
        return str(target)

    def store_file(self, path: str | Path) -> str:
        try:
            return self.store(Path(path).read_bytes(), Path(path).suffix)
        except OSError:
            return ""

    def size_bytes(self) -> int:
        total = 0
        try:
            for entry in os.scandir(self.directory):
                if entry.is_file():
                    total += entry.stat().st_size
        except OSError:
            pass
        return total

    def clear(self) -> int:
        removed = 0
        try:
            for entry in os.scandir(self.directory):
                if entry.is_file():
                    try:
                        os.unlink(entry.path)
                        removed += 1
                    except OSError:
                        pass
        except OSError:
            pass
        return removed

    def prune(self, max_bytes: int) -> int:
        """超出容量时按最久未修改顺序删除。"""
        if max_bytes <= 0:
            return 0
        try:
            entries = [
                (entry.stat().st_mtime, entry.stat().st_size, entry.path)
                for entry in os.scandir(self.directory)
                if entry.is_file()
            ]
        except OSError:
            return 0
        total = sum(size for _, size, _ in entries)
        if total <= max_bytes:
            return 0
        entries.sort()
        removed = 0
        for _, size, path in entries:
            if total <= max_bytes:
                break
            try:
                os.unlink(path)
                total -= size
                removed += 1
            except OSError:
                pass
        return removed


class _LoadJob(QRunnable):
    def __init__(self, provider: "CoverProvider", key: str, url: str, headers: dict | None) -> None:
        super().__init__()
        self._provider = provider
        self._key = key
        self._url = url
        self._headers = headers or {}

    def run(self) -> None:  # pragma: no cover - 线程内执行
        data = b""
        try:
            import requests

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HushPlayer/1.0",
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            }
            headers.update({str(k): str(v) for k, v in self._headers.items()})
            response = requests.get(self._url, headers=headers, timeout=12)
            if response.status_code == 200:
                data = response.content
        except Exception as exc:
            log.debug("封面下载失败 %s: %s", self._url, exc)
        path = ""
        if data:
            path = self._provider.store.store(data, self._provider.guess_ext(data))
        self._provider._on_job_done(self._key, path)


class CoverProvider(QObject):
    """线程安全的封面提供者：`pixmap(track, size)` 立即返回或返回 None 并在稍后发出 ready。"""

    ready = Signal(str)  # track id

    def __init__(self, store: ArtworkStore | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store or ArtworkStore()
        self._memory: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._pending: set[str] = set()
        self._resolved: dict[str, str] = {}
        self._lock = threading.Lock()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._placeholder_cache: dict[tuple[int, bool], QPixmap] = {}

    # -- 查询 ------------------------------------------------------------

    def key_for(self, track: Track | None) -> str:
        if track is None:
            return ""
        if track.artwork_path and os.path.exists(track.artwork_path):
            return track.artwork_path
        if track.artwork_url:
            return track.artwork_url
        return ""

    def pixmap(self, track: Track | None, size: int, *, dpr: float = 2.0) -> QPixmap | None:
        if track is None:
            return None
        key = self._resolved.get(track.id) or self.key_for(track)
        if not key:
            if track.kind == "local" and track.path and track.id not in self._pending:
                self._schedule_local(track)
            return None
        cache_key = (key, int(size * dpr))
        cached = self._memory.get(cache_key)
        if cached is not None:
            self._memory.move_to_end(cache_key)
            return cached
        if os.path.exists(key):
            pix = self._load_file(key, size, dpr)
            if pix is not None:
                self._put(cache_key, pix)
                return pix
            return None
        if not track.artwork_url:
            return None
        if track.id not in self._pending:
            self._schedule_remote(track, key)
        return None

    def prefetch(self, track: Track) -> None:
        if not track or track.id in self._pending:
            return
        key = self.key_for(track)
        if key and not os.path.exists(key) and track.artwork_url:
            self._schedule_remote(track, key)

    def invalidate(self, track_id: str) -> None:
        self._resolved.pop(track_id, None)

    def clear_memory(self) -> None:
        self._memory.clear()

    # -- 内部 ------------------------------------------------------------

    def _put(self, key: tuple[str, int], pixmap: QPixmap) -> None:
        self._memory[key] = pixmap
        while len(self._memory) > _MAX_MEMORY_ENTRIES:
            self._memory.popitem(last=False)

    def _load_file(self, path: str, size: int, dpr: float) -> QPixmap | None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        return self._scale(pixmap, size, dpr)

    @staticmethod
    def _scale(pixmap: QPixmap, size: int, dpr: float) -> QPixmap:
        target = max(1, int(round(size * dpr)))
        if pixmap.width() <= target and pixmap.height() <= target:
            scaled = pixmap
        else:
            scaled = pixmap.scaled(
                target,
                target,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
        scaled.setDevicePixelRatio(dpr)
        return scaled

    def _schedule_local(self, track: Track) -> None:
        self._pending.add(track.id)
        job = _LocalCoverJob(self, track)
        self._pool.start(job)

    def _schedule_remote(self, track: Track, key: str) -> None:
        self._pending.add(track.id)
        job = _LoadJob(self, track.id, track.artwork_url, None)
        self._pool.start(job)

    def _on_job_done(self, track_id: str, path: str) -> None:
        # 可能在不同线程：仅做字典写入，信号由 Qt 排队投递
        if path:
            self._resolved[track_id] = path
        self._pending.discard(track_id)
        self.ready.emit(track_id)

    @staticmethod
    def guess_ext(data: bytes) -> str:
        if data[:3] == b"\xff\xd8\xff":
            return ".jpg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        if data[:3] == b"GIF":
            return ".gif"
        return ".jpg"

    def placeholder(self, size: int, light: bool = False) -> QPixmap:
        return placeholder_pixmap(size, light=light, cache=self._placeholder_cache)


class _LocalCoverJob(QRunnable):
    """为扫描阶段没拿到封面的本地文件补一次提取。"""

    def __init__(self, provider: CoverProvider, track: Track) -> None:
        super().__init__()
        self._provider = provider
        self._track = track

    def run(self) -> None:  # pragma: no cover - 线程内执行
        path = ""
        try:
            from .metadata import read_track

            track, cover, ext = read_track(self._track.path, with_cover=True)
            if cover:
                path = self._provider.store.store(cover, ext)
            elif track.artwork_path:
                path = track.artwork_path
        except Exception:
            path = ""
        self._provider._on_job_done(self._track.id, path)


def placeholder_pixmap(size: int, light: bool = False, cache: dict | None = None) -> QPixmap:
    key = (size, light)
    if cache is not None and key in cache:
        return cache[key]
    target = max(24, int(size))
    pixmap = QPixmap(target, target)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    rect = QRectF(0, 0, target, target)
    path = QPainterPath()
    radius = target * 0.08
    path.addRoundedRect(rect, radius, radius)
    painter.setClipPath(path)
    gradient = QLinearGradient(0, 0, target, target)
    if light:
        gradient.setColorAt(0.0, QColor("#E6E6EC"))
        gradient.setColorAt(1.0, QColor("#D6D6DF"))
    else:
        gradient.setColorAt(0.0, QColor("#25252C"))
        gradient.setColorAt(1.0, QColor("#191920"))
    painter.fillPath(path, gradient)
    # 一个简单的唱片/音符轮廓
    pen_color = QColor(255, 255, 255, 46) if not light else QColor(0, 0, 0, 38)
    painter.setPen(Qt.NoPen)
    painter.setBrush(pen_color)
    circle = target * 0.30
    painter.drawEllipse(QRectF((target - circle) / 2, (target - circle) / 2, circle, circle))
    painter.setBrush(QColor(0, 0, 0, 0))
    painter.setPen(pen_color)
    inner = target * 0.10
    painter.drawEllipse(
        QRectF((target - inner) / 2, (target - inner) / 2, inner, inner)
    )
    painter.end()
    pixmap.setDevicePixelRatio(1.0)
    if cache is not None:
        cache[key] = pixmap
    return pixmap
