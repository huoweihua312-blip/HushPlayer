from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QFile, QIODevice, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.models.media_item import MediaItem
from app.services.online_download_manager import OnlineDownloadManager


@dataclass(slots=True)
class _CacheJob:
    cache_key: str
    stable_identity: str
    source_id: str
    track_id: str
    quality: str
    temporary_path: Path
    resolution: dict
    reply: QNetworkReply
    file: QFile
    created_at: int
    expected_size: int = 0
    mime_type: str = ""
    file_extension: str = ""
    written: int = 0
    first_bytes: bytearray = field(default_factory=bytearray)
    failure: str = ""
    last_progress_at: float = 0.0


class OnlineAudioCacheService(QObject):
    """Maintain validated full-file caches for authorized online tracks.

    HTTP is handled by Qt's asynchronous network stack. ``readyRead`` writes only
    the bytes currently buffered by Qt and never reads or hashes a complete file
    on the UI thread.
    """

    cacheStarted = Signal(str)
    cacheProgress = Signal(str, int, int)
    cacheCompleted = Signal(str, str)
    cacheFailed = Signal(str, str)
    cacheRemoved = Signal(str)
    statisticsChanged = Signal()

    MIN_CACHE_BYTES = 1024
    MAX_CACHE_BYTES = 1024 * 1024 * 1024
    PROGRESS_INTERVAL_SECONDS = 0.25
    _CACHE_FILE_PATTERN = re.compile(r"^[0-9a-f]{64}(?:\.[A-Za-z0-9]{1,8})?$")
    _REJECTED_CONTENT_TYPES = {
        "text/html",
        "application/xhtml+xml",
        "application/json",
        "text/json",
        "application/xml",
        "text/xml",
    }
    _MIME_EXTENSIONS = {
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
    _FORMAT_EXTENSIONS = {
        "mp3": ".mp3",
        "mpeg": ".mp3",
        "flac": ".flac",
        "wav": ".wav",
        "wave": ".wav",
        "m4a": ".m4a",
        "mp4": ".m4a",
        "ogg": ".ogg",
        "opus": ".opus",
        "aac": ".aac",
    }

    def __init__(self, cache_root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_root = Path(cache_root).resolve()
        self.files_dir = self.cache_root / "audio"
        self.temp_dir = self.cache_root / "temp"
        self.index_path = self.cache_root / "cache_index.sqlite3"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.network = QNetworkAccessManager(self)
        self._jobs: dict[str, _CacheJob] = {}
        self._closed = False
        self._initialize_database()
        self._cleanup_startup_artifacts()

    @contextmanager
    def _database_connection(self):
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        initialize_schema = not self.index_path.is_file()
        database = sqlite3.connect(str(self.index_path), timeout=5.0)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA busy_timeout=5000")
        database.execute("PRAGMA synchronous=NORMAL")
        try:
            if initialize_schema:
                self._create_schema(database)
            yield database
            database.commit()
        except Exception:
            database.rollback()
            raise
        finally:
            database.close()

    @staticmethod
    def _normalized_identity(value: MediaItem | dict) -> tuple[MediaItem, str, str, str]:
        media_item = MediaItem.from_mapping(value)
        if media_item.media_type != "online":
            raise ValueError("音频缓存只支持在线歌曲。")
        source_id = str(media_item.source_id or "").strip()
        track_id = str(media_item.track_id or "").strip()
        if not source_id or not track_id:
            raise ValueError("在线歌曲缺少稳定的来源或歌曲标识。")
        quality = str(media_item.quality or "default").strip().casefold() or "default"
        return media_item, source_id, track_id, quality

    @classmethod
    def cache_key_for(cls, value: MediaItem | dict) -> str:
        _media_item, source_id, track_id, quality = cls._normalized_identity(value)
        identity = "\0".join((source_id.casefold(), track_id, quality))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def active_count(self) -> int:
        return len(self._jobs)

    def is_downloading(self, value: MediaItem | dict) -> bool:
        try:
            cache_key = self.cache_key_for(value)
        except (TypeError, ValueError):
            return False
        return cache_key in self._jobs

    def cache_record(self, value: MediaItem | dict) -> dict | None:
        try:
            cache_key = self.cache_key_for(value)
        except (TypeError, ValueError):
            return None
        with self._database_connection() as database:
            row = database.execute(
                "SELECT * FROM cache_entries WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return dict(row) if row is not None else None

    def valid_cache(self, value: MediaItem | dict, *, touch: bool = True) -> dict | None:
        record = self.cache_record(value)
        if not record or record.get("status") != "complete":
            try:
                media_item, _source_id, _track_id, quality = self._normalized_identity(value)
            except (TypeError, ValueError):
                return None
            if quality == "default":
                with self._database_connection() as database:
                    row = database.execute(
                        "SELECT * FROM cache_entries "
                        "WHERE stable_identity = ? AND status = 'complete' "
                        "ORDER BY CASE WHEN quality = 'standard' THEN 0 ELSE 1 END, "
                        "last_accessed_at DESC, completed_at DESC LIMIT 1",
                        (media_item.stable_identity,),
                    ).fetchone()
                record = dict(row) if row is not None else None
        if not record or record.get("status") != "complete":
            return None
        cache_key = str(record.get("cache_key") or "")
        path = Path(str(record.get("local_path") or ""))
        expected_size = self._safe_size(record.get("expected_size"))
        if not self._is_valid_complete_file(path, expected_size, str(record.get("mime_type") or "")):
            self._remove_record_and_files(cache_key, record)
            self.statisticsChanged.emit()
            return None
        actual_size = path.stat().st_size
        if actual_size != self._safe_size(record.get("file_size")):
            with self._database_connection() as database:
                database.execute(
                    "UPDATE cache_entries SET file_size = ? WHERE cache_key = ?",
                    (actual_size, cache_key),
                )
            record["file_size"] = actual_size
        if touch:
            accessed_at = int(time.time())
            with self._database_connection() as database:
                database.execute(
                    "UPDATE cache_entries SET last_accessed_at = ? WHERE cache_key = ?",
                    (accessed_at, cache_key),
                )
            record["last_accessed_at"] = accessed_at
        return record

    def start_cache(self, value: MediaItem | dict, resolution: dict) -> bool:
        if self._closed:
            return False
        try:
            media_item, source_id, track_id, quality = self._normalized_identity(value)
            cache_key = self.cache_key_for(media_item)
            url, headers = OnlineDownloadManager.validate_resolution(resolution)
        except (TypeError, ValueError) as error:
            self.cacheFailed.emit("", str(error))
            return False
        if cache_key in self._jobs or self.valid_cache(media_item, touch=False) is not None:
            return False

        expected_size = self._resolution_expected_size(resolution)
        if expected_size > self.MAX_CACHE_BYTES:
            self._record_failed(
                cache_key,
                media_item,
                quality,
                "音频缓存超过 1 GB 安全上限。",
            )
            return False

        temporary_path = self.temp_dir / f"{cache_key}.part"
        self._unlink_if_safe(temporary_path, self.temp_dir)
        output = QFile(str(temporary_path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            self._record_failed(
                cache_key,
                media_item,
                quality,
                f"无法创建音频缓存临时文件：{output.errorString()}",
            )
            return False

        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        for name, header_value in headers.items():
            request.setRawHeader(name.encode("ascii"), header_value.encode("utf-8"))
        reply = self.network.get(request)
        now = int(time.time())
        job = _CacheJob(
            cache_key=cache_key,
            stable_identity=media_item.stable_identity,
            source_id=source_id,
            track_id=track_id,
            quality=quality,
            temporary_path=temporary_path,
            resolution=dict(resolution),
            reply=reply,
            file=output,
            created_at=now,
            expected_size=expected_size,
            file_extension=self._extension_from_hints(media_item, resolution),
        )
        self._jobs[cache_key] = job
        self._record_downloading(job)
        reply.metaDataChanged.connect(lambda key=cache_key: self._validate_response(key))
        reply.readyRead.connect(lambda key=cache_key: self._read_available(key))
        reply.downloadProgress.connect(
            lambda received, total, key=cache_key: self._on_progress(key, received, total)
        )
        reply.finished.connect(lambda key=cache_key: self._on_finished(key))
        self.cacheStarted.emit(cache_key)
        self.statisticsChanged.emit()
        return True

    def delete_cache(
        self,
        value: MediaItem | dict,
        *,
        protected_cache_key: str = "",
    ) -> dict:
        record = self.valid_cache(value, touch=False)
        if record is not None:
            cache_key = str(record.get("cache_key") or "")
        else:
            try:
                cache_key = self.cache_key_for(value)
            except (TypeError, ValueError):
                return {"removed": 0, "skipped": 0, "bytes": 0}
        if cache_key and cache_key == str(protected_cache_key or ""):
            return {"removed": 0, "skipped": 1, "bytes": 0}
        self._cancel_job(cache_key, remove_record=True)
        with self._database_connection() as database:
            row = database.execute(
                "SELECT * FROM cache_entries WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return {"removed": 0, "skipped": 0, "bytes": 0}
        record = dict(row)
        removed_bytes = self._record_file_bytes(record)
        self._remove_record_and_files(cache_key, record)
        self.cacheRemoved.emit(cache_key)
        self.statisticsChanged.emit()
        return {"removed": 1, "skipped": 0, "bytes": removed_bytes}

    def clear_incomplete(self, *, protected_cache_key: str = "") -> dict:
        protected = str(protected_cache_key or "")
        cancelled = 0
        for cache_key in list(self._jobs):
            if cache_key == protected:
                continue
            self._cancel_job(cache_key, remove_record=True)
            cancelled += 1
        with self._database_connection() as database:
            rows = database.execute(
                "SELECT * FROM cache_entries WHERE status != 'complete'"
            ).fetchall()
        removed = 0
        removed_bytes = 0
        for row in rows:
            record = dict(row)
            cache_key = str(record.get("cache_key") or "")
            if cache_key == protected:
                continue
            removed_bytes += self._record_file_bytes(record)
            self._remove_record_and_files(cache_key, record)
            removed += 1
        for path in self.temp_dir.glob("*.part"):
            removed_bytes += self._safe_file_size(path)
            self._unlink_if_safe(path, self.temp_dir)
        if cancelled or removed or removed_bytes:
            self.statisticsChanged.emit()
        return {
            "removed": removed + cancelled,
            "cancelled": cancelled,
            "skipped": int(bool(protected and protected in self._jobs)),
            "bytes": removed_bytes,
        }

    def clear_all(self, *, protected_cache_key: str = "") -> dict:
        protected = str(protected_cache_key or "")
        cancelled = 0
        for cache_key in list(self._jobs):
            if cache_key == protected:
                continue
            self._cancel_job(cache_key, remove_record=True)
            cancelled += 1
        with self._database_connection() as database:
            rows = database.execute("SELECT * FROM cache_entries").fetchall()
        removed = 0
        skipped = 0
        removed_bytes = 0
        for row in rows:
            record = dict(row)
            cache_key = str(record.get("cache_key") or "")
            if cache_key == protected:
                skipped += 1
                continue
            removed_bytes += self._record_file_bytes(record)
            self._remove_record_and_files(cache_key, record)
            removed += 1
        for path in self.temp_dir.glob("*.part"):
            removed_bytes += self._safe_file_size(path)
            self._unlink_if_safe(path, self.temp_dir)
        for path in self.files_dir.iterdir():
            if not path.is_file() or not self._CACHE_FILE_PATTERN.fullmatch(path.name):
                continue
            if protected and path.name.startswith(protected):
                continue
            removed_bytes += self._safe_file_size(path)
            self._unlink_if_safe(path, self.files_dir)
        if cancelled or removed or removed_bytes:
            self.statisticsChanged.emit()
        return {
            "removed": removed + cancelled,
            "cancelled": cancelled,
            "skipped": skipped,
            "bytes": removed_bytes,
        }

    def statistics(self) -> dict:
        complete_count = 0
        complete_bytes = 0
        with self._database_connection() as database:
            rows = database.execute(
                "SELECT * FROM cache_entries WHERE status = 'complete'"
            ).fetchall()
        for row in rows:
            record = dict(row)
            path = Path(str(record.get("local_path") or ""))
            if self._is_valid_complete_file(
                path,
                self._safe_size(record.get("expected_size")),
                str(record.get("mime_type") or ""),
            ):
                complete_count += 1
                complete_bytes += self._safe_file_size(path)
            else:
                self._remove_record_and_files(str(record.get("cache_key") or ""), record)
        incomplete_bytes = sum(
            self._safe_file_size(path) for path in self.temp_dir.glob("*.part")
        )
        return {
            "complete_count": complete_count,
            "complete_bytes": complete_bytes,
            "incomplete_bytes": incomplete_bytes,
            "active_count": len(self._jobs),
            "cache_root": str(self.cache_root),
        }

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        for cache_key in list(self._jobs):
            self._cancel_job(cache_key, remove_record=False, failure="应用退出，缓存任务已取消。")

    def _initialize_database(self) -> None:
        with self._database_connection() as database:
            database.execute("PRAGMA journal_mode=WAL")
            self._create_schema(database)

    @staticmethod
    def _create_schema(database: sqlite3.Connection) -> None:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                stable_identity TEXT NOT NULL,
                source_id TEXT NOT NULL,
                track_id TEXT NOT NULL,
                quality TEXT NOT NULL,
                local_path TEXT NOT NULL DEFAULT '',
                temporary_path TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '',
                file_extension TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                expected_size INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                completed_at INTEGER NOT NULL DEFAULT 0,
                last_accessed_at INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        database.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_entries_identity "
            "ON cache_entries(stable_identity, quality)"
        )
        database.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_entries_status "
            "ON cache_entries(status)"
        )

    def _cleanup_startup_artifacts(self) -> None:
        for path in self.temp_dir.glob("*.part"):
            self._unlink_if_safe(path, self.temp_dir)
        with self._database_connection() as database:
            database.execute(
                "UPDATE cache_entries SET status = 'failed', temporary_path = '', "
                "file_size = 0, last_error = ? WHERE status = 'downloading'",
                ("上次运行结束前缓存未完成。",),
            )
            referenced = {
                Path(str(row[0])).name
                for row in database.execute(
                    "SELECT local_path FROM cache_entries WHERE status = 'complete'"
                ).fetchall()
                if str(row[0] or "")
            }
        for path in self.files_dir.iterdir():
            if (
                path.is_file()
                and self._CACHE_FILE_PATTERN.fullmatch(path.name)
                and path.name not in referenced
            ):
                self._unlink_if_safe(path, self.files_dir)

    def _record_downloading(self, job: _CacheJob) -> None:
        with self._database_connection() as database:
            database.execute(
                """
                INSERT INTO cache_entries (
                    cache_key, stable_identity, source_id, track_id, quality,
                    local_path, temporary_path, status, mime_type, file_extension,
                    file_size, expected_size, created_at, completed_at,
                    last_accessed_at, last_error
                ) VALUES (?, ?, ?, ?, ?, '', ?, 'downloading', '', ?, 0, ?, ?, 0, 0, '')
                ON CONFLICT(cache_key) DO UPDATE SET
                    stable_identity = excluded.stable_identity,
                    source_id = excluded.source_id,
                    track_id = excluded.track_id,
                    quality = excluded.quality,
                    local_path = '',
                    temporary_path = excluded.temporary_path,
                    status = 'downloading',
                    mime_type = '',
                    file_extension = excluded.file_extension,
                    file_size = 0,
                    expected_size = excluded.expected_size,
                    created_at = excluded.created_at,
                    completed_at = 0,
                    last_accessed_at = 0,
                    last_error = ''
                """,
                (
                    job.cache_key,
                    job.stable_identity,
                    job.source_id,
                    job.track_id,
                    job.quality,
                    str(job.temporary_path),
                    job.file_extension,
                    job.expected_size,
                    job.created_at,
                ),
            )

    def _record_failed(
        self,
        cache_key: str,
        media_item: MediaItem,
        quality: str,
        message: str,
    ) -> None:
        now = int(time.time())
        with self._database_connection() as database:
            database.execute(
                """
                INSERT INTO cache_entries (
                    cache_key, stable_identity, source_id, track_id, quality,
                    status, created_at, last_error
                ) VALUES (?, ?, ?, ?, ?, 'failed', ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    status = 'failed', temporary_path = '', file_size = 0,
                    completed_at = 0, last_error = excluded.last_error
                """,
                (
                    cache_key,
                    media_item.stable_identity,
                    media_item.source_id,
                    media_item.track_id,
                    quality,
                    now,
                    message,
                ),
            )
        self.cacheFailed.emit(cache_key, message)
        self.statisticsChanged.emit()

    def _validate_response(self, cache_key: str) -> None:
        job = self._jobs.get(cache_key)
        if job is None or job.failure:
            return
        reply = job.reply
        final_url = urlparse(reply.url().toString())
        if final_url.scheme not in {"http", "https"} or final_url.username or final_url.password:
            self._fail_job(job, "音频缓存重定向返回了不安全的地址。")
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        try:
            status_code = int(status or 0)
        except (TypeError, ValueError):
            status_code = 0
        if status_code and status_code not in {200, 206}:
            if 300 <= status_code < 400:
                return
            self._fail_job(job, f"音频缓存失败：HTTP {status_code}。")
            return
        content_type = bytes(reply.rawHeader("Content-Type")).decode(
            "latin-1", errors="ignore"
        ).split(";", 1)[0].strip().casefold()
        if content_type:
            job.mime_type = content_type
        if content_type in self._REJECTED_CONTENT_TYPES or content_type.startswith("text/"):
            self._fail_job(job, f"服务器返回了 {content_type or '非音频'} 内容。")
            return
        declared_size = self._safe_size(
            bytes(reply.rawHeader("Content-Length")).decode("ascii", errors="ignore")
        )
        if declared_size > self.MAX_CACHE_BYTES:
            self._fail_job(job, "音频缓存超过 1 GB 安全上限。")
            return
        if declared_size:
            job.expected_size = declared_size
        if not job.file_extension:
            disposition = bytes(reply.rawHeader("Content-Disposition")).decode(
                "latin-1", errors="ignore"
            )
            job.file_extension = self._extension_from_response(
                job.resolution,
                disposition,
                job.mime_type,
                reply.url().toString(),
            )

    def _read_available(self, cache_key: str) -> None:
        job = self._jobs.get(cache_key)
        if job is None or job.failure:
            return
        self._validate_response(cache_key)
        if job.failure:
            return
        chunk = job.reply.readAll()
        size = chunk.size()
        if size <= 0:
            return
        raw = bytes(chunk)
        if len(job.first_bytes) < 1024:
            remaining = 1024 - len(job.first_bytes)
            job.first_bytes.extend(raw[:remaining])
        if self._looks_like_error_document(bytes(job.first_bytes)):
            self._fail_job(job, "音频缓存内容实际是 HTML、XML 或 JSON 错误响应。")
            return
        if job.written + size > self.MAX_CACHE_BYTES:
            self._fail_job(job, "音频缓存超过 1 GB 安全上限。")
            return
        written = job.file.write(chunk)
        if written != size:
            self._fail_job(job, f"写入音频缓存失败：{job.file.errorString()}")
            return
        job.written += int(written)

    def _on_progress(self, cache_key: str, received: int, total: int) -> None:
        job = self._jobs.get(cache_key)
        if job is None:
            return
        if total > self.MAX_CACHE_BYTES:
            self._fail_job(job, "音频缓存超过 1 GB 安全上限。")
            return
        now = time.monotonic()
        if now - job.last_progress_at < self.PROGRESS_INTERVAL_SECONDS and received != total:
            return
        job.last_progress_at = now
        self.cacheProgress.emit(cache_key, max(0, int(received)), int(total))

    def _on_finished(self, cache_key: str) -> None:
        job = self._jobs.get(cache_key)
        if job is None:
            return
        self._validate_response(cache_key)
        self._read_available(cache_key)
        if not job.failure and job.reply.error() != QNetworkReply.NetworkError.NoError:
            job.failure = f"音频缓存失败：{job.reply.errorString()}"
        job.file.flush()
        job.file.close()
        if not job.failure and job.written < self.MIN_CACHE_BYTES:
            job.failure = "音频缓存文件过小，可能不是完整媒体。"
        if not job.failure and job.expected_size and job.written != job.expected_size:
            job.failure = (
                f"音频缓存大小不完整：收到 {job.written} 字节，"
                f"预期 {job.expected_size} 字节。"
            )
        if not job.failure and not self._valid_media_header(bytes(job.first_bytes), job.mime_type):
            job.failure = "音频缓存文件头无效或内容不是可识别的媒体。"

        final_path = Path()
        if not job.failure:
            extension = job.file_extension or ".bin"
            final_path = self.files_dir / f"{job.cache_key}{extension}"
            try:
                os.replace(job.temporary_path, final_path)
            except OSError as error:
                job.failure = f"提交音频缓存文件失败：{error}"

        reply = job.reply
        self._jobs.pop(cache_key, None)
        reply.blockSignals(True)
        reply.deleteLater()
        job.file.deleteLater()
        if job.failure:
            self._unlink_if_safe(job.temporary_path, self.temp_dir)
            with self._database_connection() as database:
                database.execute(
                    "UPDATE cache_entries SET status = 'failed', temporary_path = '', "
                    "file_size = 0, expected_size = ?, mime_type = ?, "
                    "file_extension = ?, completed_at = 0, last_error = ? "
                    "WHERE cache_key = ?",
                    (
                        job.expected_size,
                        job.mime_type,
                        job.file_extension,
                        job.failure,
                        cache_key,
                    ),
                )
            self.cacheFailed.emit(cache_key, job.failure)
        else:
            completed_at = int(time.time())
            with self._database_connection() as database:
                database.execute(
                    "UPDATE cache_entries SET local_path = ?, temporary_path = '', "
                    "status = 'complete', mime_type = ?, file_extension = ?, "
                    "file_size = ?, expected_size = ?, completed_at = ?, "
                    "last_accessed_at = ?, last_error = '' WHERE cache_key = ?",
                    (
                        str(final_path),
                        job.mime_type,
                        job.file_extension,
                        job.written,
                        job.expected_size,
                        completed_at,
                        completed_at,
                        cache_key,
                    ),
                )
            self.cacheCompleted.emit(cache_key, str(final_path))
        self.statisticsChanged.emit()

    def _fail_job(self, job: _CacheJob, message: str) -> None:
        if job.failure:
            return
        job.failure = str(message or "音频缓存失败。")
        job.reply.abort()

    def _cancel_job(
        self,
        cache_key: str,
        *,
        remove_record: bool,
        failure: str = "音频缓存任务已取消。",
    ) -> bool:
        job = self._jobs.pop(cache_key, None)
        if job is None:
            return False
        job.reply.blockSignals(True)
        job.reply.abort()
        job.reply.deleteLater()
        if job.file.isOpen():
            job.file.close()
        job.file.deleteLater()
        self._unlink_if_safe(job.temporary_path, self.temp_dir)
        if remove_record:
            with self._database_connection() as database:
                database.execute(
                    "DELETE FROM cache_entries WHERE cache_key = ?",
                    (cache_key,),
                )
        else:
            with self._database_connection() as database:
                database.execute(
                    "UPDATE cache_entries SET status = 'failed', temporary_path = '', "
                    "file_size = 0, completed_at = 0, last_error = ? "
                    "WHERE cache_key = ?",
                    (failure, cache_key),
                )
        return True

    def _remove_record_and_files(self, cache_key: str, record: dict) -> None:
        local_path = Path(str(record.get("local_path") or ""))
        temporary_path = Path(str(record.get("temporary_path") or ""))
        self._unlink_if_safe(local_path, self.files_dir)
        self._unlink_if_safe(temporary_path, self.temp_dir)
        with self._database_connection() as database:
            database.execute(
                "DELETE FROM cache_entries WHERE cache_key = ?",
                (cache_key,),
            )

    def _is_valid_complete_file(
        self,
        path: Path,
        expected_size: int,
        mime_type: str,
    ) -> bool:
        if not self._path_within(path, self.files_dir) or path.suffix.casefold() == ".part":
            return False
        try:
            actual_size = path.stat().st_size
            if actual_size < self.MIN_CACHE_BYTES:
                return False
            if expected_size and actual_size != expected_size:
                return False
            with path.open("rb") as file:
                first_bytes = file.read(1024)
        except OSError:
            return False
        return self._valid_media_header(first_bytes, mime_type)

    @classmethod
    def _valid_media_header(cls, first_bytes: bytes, mime_type: str) -> bool:
        if not first_bytes or cls._looks_like_error_document(first_bytes):
            return False
        if len(set(first_bytes[: min(256, len(first_bytes))])) <= 1:
            return False
        header = first_bytes[:64]
        recognized = (
            header.startswith((b"ID3", b"fLaC", b"RIFF", b"OggS", b"FORM"))
            or (len(header) >= 12 and header[4:8] == b"ftyp")
            or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)
        )
        normalized_mime = str(mime_type or "").split(";", 1)[0].strip().casefold()
        mime_allows_media = (
            normalized_mime.startswith("audio/")
            or normalized_mime in {"application/ogg", "video/mp4", "application/octet-stream"}
        )
        binary_bytes = sum(
            1 for value in header if value == 0 or value < 9 or 13 < value < 32 or value > 126
        )
        looks_binary = bool(header) and binary_bytes / len(header) >= 0.18
        return bool(recognized or (mime_allows_media and looks_binary) or looks_binary)

    @staticmethod
    def _looks_like_error_document(first_bytes: bytes) -> bool:
        beginning = bytes(first_bytes[:1024]).lstrip().lower()
        return beginning.startswith(
            (b"<!doctype html", b"<html", b"<?xml", b"{", b"[")
        )

    @classmethod
    def _extension_from_hints(cls, media_item: MediaItem, resolution: dict) -> str:
        for value in (
            media_item.format,
            resolution.get("format"),
            resolution.get("type"),
            resolution.get("ext"),
        ):
            extension = cls._normalized_extension(value)
            if extension:
                return extension
        filename = Path(str(resolution.get("filename") or "")).suffix
        return cls._normalized_extension(filename)

    @classmethod
    def _extension_from_response(
        cls,
        resolution: dict,
        content_disposition: str,
        mime_type: str,
        final_url: str,
    ) -> str:
        for candidate in (
            str(resolution.get("filename") or ""),
            cls._content_disposition_filename(content_disposition),
        ):
            extension = cls._normalized_extension(Path(candidate).suffix)
            if extension:
                return extension
        mime_extension = cls._MIME_EXTENSIONS.get(mime_type, "")
        if mime_extension:
            return mime_extension
        return cls._normalized_extension(Path(urlparse(final_url).path).suffix)

    @classmethod
    def _normalized_extension(cls, value) -> str:
        text = str(value or "").strip().casefold().lstrip(".")
        if not text:
            return ""
        if "/" in text:
            return cls._MIME_EXTENSIONS.get(text, "")
        return cls._FORMAT_EXTENSIONS.get(text, "")

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
    def _resolution_expected_size(resolution: dict) -> int:
        for key in ("expected_size", "contentLength", "content_length", "size"):
            size = OnlineAudioCacheService._safe_size(resolution.get(key))
            if size:
                return size
        return 0

    @staticmethod
    def _safe_size(value) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_file_size(path: Path) -> int:
        try:
            return max(0, path.stat().st_size) if path.is_file() else 0
        except OSError:
            return 0

    def _record_file_bytes(self, record: dict) -> int:
        return self._safe_file_size(Path(str(record.get("local_path") or ""))) + self._safe_file_size(
            Path(str(record.get("temporary_path") or ""))
        )

    @staticmethod
    def _path_within(path: Path, directory: Path) -> bool:
        if not str(path):
            return False
        try:
            path.resolve().relative_to(directory.resolve())
            return True
        except (OSError, ValueError):
            return False

    def _unlink_if_safe(self, path: Path, directory: Path) -> bool:
        if not str(path) or not self._path_within(path, directory):
            return False
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False
