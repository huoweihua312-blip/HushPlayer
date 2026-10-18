"""音乐库扫描：后台线程遍历目录、读取元数据、写库、清理失效条目。

设计要点：
- 扫描在独立线程执行，UI 线程只接收节流的进度信号。
- 依据 (路径, 大小, 修改时间) 判断是否需要重新解析，重复扫描很快。
- 解析失败的文件记入 scan_errors，不会中断整体扫描。
- 支持取消：取消时不做失效删除，避免误删。
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..core.logging_setup import get_logger
from ..model.track import Track, local_track_id, normalize_path
from ..store.repository import MetaStore, TrackRepository
from .artwork import ArtworkStore
from .metadata import UnsupportedAudio, is_audio_file, read_track

log = get_logger("scanner")

SKIP_DIRS = {
    "$recycle.bin",
    "system volume information",
    "recycler",
    "windows",
    "node_modules",
    "appdata",
    ".git",
    ".svn",
    "__pycache__",
}


@dataclass
class ScanResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    errors: int = 0
    cancelled: bool = False
    duration_s: float = 0.0
    folders: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "added": self.added,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "removed": self.removed,
            "errors": self.errors,
            "cancelled": self.cancelled,
            "duration_s": round(self.duration_s, 2),
            "folders": list(self.folders),
            "total": self.added + self.updated + self.unchanged,
        }

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.errors)


class Scanner(QObject):
    stage = Signal(str)
    progress = Signal(int, int, str)  # 已处理, 总数, 当前文件
    finished = Signal(object)  # ScanResult
    failed = Signal(str)

    def __init__(
        self,
        tracks: TrackRepository,
        meta: MetaStore,
        artwork: ArtworkStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._meta = meta
        self._artwork = artwork or ArtworkStore()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    # -- 状态 ------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        self._cancel.set()

    # -- 对外 API --------------------------------------------------------

    def start(self, folders: list[str]) -> bool:
        folders = [str(Path(f)) for f in folders if f]
        if not folders:
            self.finished.emit(ScanResult(folders=[]))
            return False
        with self._lock:
            if self._running:
                log.debug("扫描已在进行中，忽略重复请求")
                return False
            self._running = True
            self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, args=(folders,), name="library-scan", daemon=True
        )
        self._thread.start()
        return True

    def import_files(self, file_paths: list[str]) -> ScanResult:
        """同步导入单个文件（用于“添加歌曲”对话框，数量少、需即时反馈）。"""
        result = ScanResult(folders=[])
        started = time.monotonic()
        batch: list[Track] = []
        for raw in file_paths:
            path = str(Path(raw))
            if not is_audio_file(path):
                continue
            try:
                track, cover, ext = read_track(path, with_cover=True)
            except UnsupportedAudio as exc:
                self._meta.record_scan_error(path, str(exc))
                result.errors += 1
                continue
            except Exception as exc:  # pragma: no cover - 防御
                self._meta.record_scan_error(path, repr(exc))
                result.errors += 1
                continue
            if cover:
                stored = self._artwork.store(cover, ext)
                if stored:
                    track.artwork_path = stored
            batch.append(track)
        if batch:
            self._tracks.upsert_many(batch)
            result.added = len(batch)
        result.duration_s = time.monotonic() - started
        self.finished.emit(result)
        return result

    # -- 线程体 ----------------------------------------------------------

    def _run(self, folders: list[str]) -> None:
        started = time.monotonic()
        result = ScanResult(folders=folders)
        try:
            self.stage.emit("正在收集音频文件…")
            files = self._collect(folders)
            result.errors += 0
            total = len(files)
            self.progress.emit(0, total, "")

            known = self._known_state()
            pending: list[Track] = []
            errors = 0
            last_emit = 0.0
            for index, path in enumerate(files, start=1):
                if self._cancel.is_set():
                    result.cancelled = True
                    break
                path_key = normalize_path(path)
                key = local_track_id(path)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                previous = known.get(path_key)
                if previous and previous[0] == int(stat.st_size) and abs(previous[1] - stat.st_mtime) < 1.0:
                    result.unchanged += 1
                    if index - last_emit >= 40:
                        self.progress.emit(index, total, path)
                        last_emit = index
                    continue
                try:
                    track, cover, ext = read_track(path, with_cover=True)
                except UnsupportedAudio as exc:
                    errors += 1
                    self._meta.record_scan_error(path, str(exc))
                    log.debug("无法解析音频 %s: %s", path, exc)
                    continue
                except Exception as exc:  # pragma: no cover - 防御
                    errors += 1
                    self._meta.record_scan_error(path, repr(exc))
                    log.warning("读取元数据异常 %s: %r", path, exc)
                    continue
                if cover:
                    stored = self._artwork.store(cover, ext)
                    if stored:
                        track.artwork_path = stored
                track.id = key
                pending.append(track)
                if len(pending) >= 200:
                    added, updated = self._flush(pending)
                    result.added += added
                    result.updated += updated
                if index - last_emit >= 40:
                    self.progress.emit(index, total, path)
                    last_emit = index

            if pending:
                added, updated = self._flush(pending)
                result.added += added
                result.updated += updated
            self.progress.emit(min(total, self._processed_hint(total)), total, "")

            result.errors = errors
            if not result.cancelled:
                self.stage.emit("正在清理失效条目…")
                present = {normalize_path(path) for path in files}
                result.removed = self._tracks.delete_local_missing(present, folders)
                self._meta.clear_scan_errors()
        except Exception as exc:  # pragma: no cover - 防御
            log.exception("扫描失败: %r", exc)
            self.failed.emit(str(exc))
            result.errors += 1
        finally:
            result.duration_s = time.monotonic() - started
            with self._lock:
                self._running = False
            log.info(
                "扫描结束 added=%s updated=%s unchanged=%s removed=%s errors=%s cancelled=%s %.2fs",
                result.added,
                result.updated,
                result.unchanged,
                result.removed,
                result.errors,
                result.cancelled,
                result.duration_s,
            )
            self.finished.emit(result)

    @staticmethod
    def _processed_hint(total: int) -> int:
        return total

    def _flush(self, batch: list[Track]) -> tuple[int, int]:
        added, updated = self._tracks.upsert_many(batch, return_counts=True)
        batch.clear()
        return added, updated

    def _known_state(self) -> dict[str, tuple[int, float, str]]:
        state: dict[str, tuple[int, float, str]] = {}
        try:
            rows = self._tracks.db.connection().execute(
                "SELECT path_key, size, modified_at, id FROM tracks WHERE kind = 'local'"
            ).fetchall()
            for row in rows:
                state[row["path_key"]] = (int(row["size"] or 0), float(row["modified_at"] or 0.0), row["id"])
        except Exception as exc:  # pragma: no cover
            log.warning("读取既有曲目状态失败: %r", exc)
        return state

    def _collect(self, folders: list[str]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for folder in folders:
            root = Path(folder)
            if not root.exists():
                self._meta.record_scan_error(str(root), "目录不存在")
                continue
            try:
                for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                    if self._cancel.is_set():
                        return found
                    dirnames[:] = [
                        name
                        for name in dirnames
                        if not name.startswith(".")
                        and name.casefold() not in SKIP_DIRS
                        and not name.startswith("$")
                    ]
                    for name in filenames:
                        if not is_audio_file(name):
                            continue
                        full = os.path.join(dirpath, name)
                        key = normalize_path(full)
                        if key in seen:
                            continue
                        seen.add(key)
                        found.append(full)
                        if len(found) % 500 == 0:
                            self.stage.emit(f"正在收集音频文件… {len(found)}")
                    if len(found) % 200 == 0 and found:
                        self.progress.emit(0, len(found), dirpath)
            except OSError as exc:
                self._meta.record_scan_error(str(root), str(exc))
                log.warning("遍历目录失败 %s: %s", root, exc)
        return found


def walk_audio(folder: str, limit: int = 0) -> list[str]:
    """给工具与测试使用的一次性目录枚举。"""
    items: list[str] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if is_audio_file(name):
                items.append(os.path.join(dirpath, name))
                if limit and len(items) >= limit:
                    return items
    return items
