"""Cache housekeeping.

Everything here is disposable: the audio proxy cache, the artwork cache, the
lyrics cache and the on-disk database files.  The service reports sizes, clears
individual caches or everything, prunes to a budget and repairs indexes that
no longer match the files on disk.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from ..core import paths
from ..core.logging_setup import get_logger
from ..library.artwork import ArtworkStore
from ..online.proxy import AudioProxy

log = get_logger("services.cache")


@dataclass
class CacheStats:
    audio_bytes: int = 0
    audio_files: int = 0
    artwork_bytes: int = 0
    artwork_files: int = 0
    lyrics_bytes: int = 0
    lyrics_files: int = 0
    database_bytes: int = 0
    log_bytes: int = 0
    downloads_bytes: int = 0
    downloads_files: int = 0

    @property
    def total_bytes(self) -> int:
        return (
            self.audio_bytes
            + self.artwork_bytes
            + self.lyrics_bytes
            + self.database_bytes
            + self.log_bytes
            + self.downloads_bytes
        )

    def to_dict(self) -> dict:
        return {
            "audio_bytes": self.audio_bytes,
            "audio_files": self.audio_files,
            "artwork_bytes": self.artwork_bytes,
            "artwork_files": self.artwork_files,
            "lyrics_bytes": self.lyrics_bytes,
            "lyrics_files": self.lyrics_files,
            "database_bytes": self.database_bytes,
            "log_bytes": self.log_bytes,
            "downloads_bytes": self.downloads_bytes,
            "downloads_files": self.downloads_files,
            "total_bytes": self.total_bytes,
        }


@dataclass
class RepairReport:
    removed: int = 0
    kept: int = 0
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"removed": self.removed, "kept": self.kept, "problems": list(self.problems)}


def _dir_usage(folder: str, suffixes: tuple[str, ...] = ()) -> tuple[int, int]:
    total = 0
    count = 0
    if not os.path.isdir(folder):
        return (0, 0)
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if not os.path.isfile(path):
                continue
            if suffixes and not name.lower().endswith(suffixes):
                continue
            total += os.path.getsize(path)
            count += 1
        except OSError:
            continue
    return (total, count)


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class CacheService(QObject):
    changed = Signal()

    def __init__(
        self,
        proxy: AudioProxy,
        artwork: ArtworkStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._proxy = proxy
        self._artwork = artwork

    # ------------------------------------------------------------------ api
    def stats(self) -> CacheStats:
        result = CacheStats()
        audio_bytes, audio_files = _dir_usage(str(paths.audio_cache_dir()))
        result.audio_bytes = audio_bytes
        result.audio_files = audio_files
        result.artwork_bytes = self._artwork.size_bytes()
        result.artwork_files = _dir_usage(str(paths.artwork_cache_dir()))[1]
        lyrics_bytes, lyrics_files = _dir_usage(str(paths.lyrics_cache_dir()), (".json",))
        result.lyrics_bytes = lyrics_bytes
        result.lyrics_files = lyrics_files
        try:
            result.database_bytes = os.path.getsize(str(paths.database_file()))
        except OSError:
            result.database_bytes = 0
        result.log_bytes = _dir_usage(str(paths.logs_dir()))[0]
        downloads_bytes, downloads_files = _dir_usage(str(paths.downloads_dir()))
        result.downloads_bytes = downloads_bytes
        result.downloads_files = downloads_files
        return result

    def summary_text(self) -> str:
        stats = self.stats()
        return f"音乐缓存 {_human(stats.audio_bytes)} · 封面 {_human(stats.artwork_bytes)} · 共 {_human(stats.total_bytes)}"

    def clear_audio(self) -> None:
        self._proxy.clear_cache()
        self.changed.emit()

    def clear_artwork(self) -> None:
        self._artwork.clear()
        self.changed.emit()

    def clear_lyrics(self) -> None:
        folder = str(paths.lyrics_cache_dir())
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                if name.lower().endswith((".json", ".tmp")):
                    try:
                        os.remove(os.path.join(folder, name))
                    except OSError:
                        pass
        self.changed.emit()

    def clear_all(self) -> None:
        self.clear_audio()
        self.clear_artwork()
        self.clear_lyrics()

    def prune(self, max_mb: int) -> None:
        budget = max(64, int(max_mb)) * 1024 * 1024
        self._proxy.prune(budget)
        self._artwork.prune(budget // 4)
        self.changed.emit()

    # ------------------------------------------------------------ integrity
    def repair(self) -> RepairReport:
        """Delete cache files whose metadata is missing or inconsistent."""
        report = RepairReport()
        folder = str(paths.audio_cache_dir())
        if not os.path.isdir(folder):
            return report
        seen: set[str] = set()

        def media_for(token: str) -> list[str]:
            matches = []
            for name in os.listdir(folder):
                if not name.startswith(token):
                    continue
                if name.endswith(".meta.json") or name.endswith(".tmp"):
                    continue
                matches.append(os.path.join(folder, name))
            return matches

        for meta_path in glob.glob(os.path.join(folder, "*.meta.json")):
            token = os.path.basename(meta_path)[: -len(".meta.json")]
            seen.add(token)
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (OSError, json.JSONDecodeError):
                report.problems.append(f"缓存索引损坏：{token}")
                self._remove(meta_path)
                for path in media_for(token):
                    self._remove(path)
                report.removed += 1
                continue
            media = media_for(token)
            expected = int(meta.get("size") or 0)
            if not meta.get("complete") or not media:
                self._remove(meta_path)
                for path in media:
                    self._remove(path)
                report.removed += 1
                continue
            actual = sum(os.path.getsize(path) for path in media)
            if expected and actual != expected:
                report.problems.append(f"缓存大小不一致：{token}（{actual}/{expected}）")
                self._remove(meta_path)
                for path in media:
                    self._remove(path)
                report.removed += 1
                continue
            report.kept += 1
        # media files without an index are orphan leftovers
        for name in os.listdir(folder):
            if name.endswith(".meta.json") or name.endswith(".tmp"):
                continue
            token = name.split(".", 1)[0]
            if token in seen:
                continue
            report.problems.append(f"孤立缓存文件：{name}")
            self._remove(os.path.join(folder, name))
            report.removed += 1
        if report.removed:
            log.info("cache repair removed %d entries", report.removed)
        self.changed.emit()
        return report

    def _remove(self, path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass


__all__ = ["CacheService", "CacheStats", "RepairReport"]
