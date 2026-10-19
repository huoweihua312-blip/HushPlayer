"""在线歌曲下载（仅限音源明确提供下载地址的歌曲）。

流程：resolveDownload → 流式写盘（临时文件 + 原子改名）→ 记录索引。
约束：
- 不破解 DRM、不绕过任何付费/权限限制；音源不提供下载地址时如实报错；
- 下载线程不做 UI 操作，进度通过信号回到主线程；
- 下载目录来自设置 ``downloads.dir``，默认用户数据目录下的 Downloads。
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..core import paths
from ..core.logging_setup import get_logger
from ..core.settings import settings
from ..model.track import Track

log = get_logger("services.downloads")

STATE_QUEUED = "queued"
STATE_RESOLVING = "resolving"
STATE_DOWNLOADING = "downloading"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

CHUNK = 96 * 1024
USER_AGENT = "HushPlayer/1.0 (Windows; music player)"
_TIMEOUT = (10, 60)
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(text: str, *, fallback: str = "track", limit: int = 120) -> str:
    cleaned = _BAD_CHARS.sub("_", str(text or "")).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    return cleaned[:limit].strip(" .") or fallback


def downloads_dir() -> Path:
    configured = str(settings().get("downloads.dir", "") or "").strip()
    target = Path(configured) if configured else paths.downloads_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = paths.downloads_dir()
        target.mkdir(parents=True, exist_ok=True)
    return target


def index_file() -> Path:
    return paths.data_dir() / "downloads.json"


def read_index() -> list[dict]:
    path = index_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _write_index(items: list[dict]) -> None:
    path = index_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-500:], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class DownloadJob:
    id: str
    track: Track
    state: str = STATE_QUEUED
    quality: str = "higher"
    downloaded: int = 0
    total: int = 0
    path: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False

    @property
    def title(self) -> str:
        return self.track.title or "未命名歌曲"

    @property
    def display_name(self) -> str:
        if self.track.artist:
            return f"{self.track.artist} - {self.track.title}"
        return self.title

    @property
    def progress(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.downloaded / self.total))


class _FetchJob(QRunnable):
    def __init__(self, service: "DownloadService", job: DownloadJob, url: str, headers: dict) -> None:
        super().__init__()
        self._service = service
        self._job = job
        self._url = url
        self._headers = headers
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - 线程内执行
        job = self._job
        service = self._service
        target_dir = downloads_dir()
        extension = _extension(self._url, self._headers.get("Content-Type", ""))
        filename = f"{safe_filename(job.display_name)}{extension}"
        target = target_dir / filename
        index = 2
        while target.exists() and target.stat().st_size > 0:
            target = target_dir / f"{safe_filename(job.display_name)} ({index}){extension}"
            index += 1
        temp = target.with_suffix(target.suffix + ".part")
        try:
            job.state = STATE_DOWNLOADING
            service._emit(job)
            headers = dict(self._headers)
            headers.setdefault("User-Agent", USER_AGENT)
            with requests.get(self._url, headers=headers, stream=True, timeout=_TIMEOUT) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"下载服务器返回 HTTP {response.status_code}")
                total = int(response.headers.get("Content-Length") or 0)
                job.total = total
                written = 0
                with temp.open("wb") as handle:
                    for chunk in response.iter_content(CHUNK):
                        if job.cancelled:
                            raise _Cancelled()
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        job.downloaded = written
                        service._emit(job, force=written % (CHUNK * 8) < CHUNK)
                handle = None
            if job.total and written < job.total:
                raise RuntimeError(f"下载不完整（{written}/{job.total} 字节）")
            if written == 0:
                raise RuntimeError("下载内容为空")
            os.replace(temp, target)
            job.path = str(target)
            # Persist the index *before* flipping to DONE: callers treat
            # ``state == done`` as "the download is fully committed", so the
            # entry must already be readable at that moment.
            service._record_success(job)
            job.state = STATE_DONE
        except _Cancelled:
            job.state = STATE_CANCELLED
            log.info("下载已取消：%s", job.display_name)
        except Exception as exc:  # noqa: BLE001
            job.state = STATE_FAILED
            job.error = str(exc) or exc.__class__.__name__
            log.warning("下载失败：%s（%s）", job.display_name, job.error)
        finally:
            try:
                if job.state in {STATE_FAILED, STATE_CANCELLED} and temp.exists():
                    temp.unlink()
            except OSError:
                pass
            service._emit(job, final=True)


class _Cancelled(Exception):
    pass


def _extension(url: str, content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "mpeg" in lowered or "mp3" in lowered:
        return ".mp3"
    if "flac" in lowered:
        return ".flac"
    if "m4a" in lowered or "mp4" in lowered:
        return ".m4a"
    if "ogg" in lowered:
        return ".ogg"
    if "wav" in lowered:
        return ".wav"
    suffix = Path(str(url).split("?")[0]).suffix.lower()
    if suffix in {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav"}:
        return suffix
    return ".mp3"


class DownloadService(QObject):
    """把在线歌曲保存到本地下载目录。"""

    job_updated = Signal(object)
    job_finished = Signal(object)
    jobs_changed = Signal()

    def __init__(self, client, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._jobs: dict[str, DownloadJob] = {}
        self._order: list[str] = []
        self._fetches: dict[str, _FetchJob] = {}

    # ---------------------------------------------------------------- 查询
    @property
    def jobs(self) -> list[DownloadJob]:
        return [self._jobs[job_id] for job_id in self._order if job_id in self._jobs]

    def active(self) -> list[DownloadJob]:
        return [job for job in self.jobs if job.state in {STATE_QUEUED, STATE_RESOLVING, STATE_DOWNLOADING}]

    def history(self) -> list[dict]:
        return read_index()

    def count_done(self) -> int:
        return len([item for item in read_index() if item.get("path")])

    # ---------------------------------------------------------------- 动作
    def download(self, tracks: list[Track], *, quality: str | None = None) -> list[DownloadJob]:
        created: list[DownloadJob] = []
        quality = quality or str(settings().get("downloads.quality", "higher") or "higher")
        for track in tracks:
            job = DownloadJob(id=uuid.uuid4().hex[:12], track=track, quality=quality)
            if track.kind != "online":
                if track.path and Path(track.path).is_file():
                    job.state = STATE_DONE
                    job.path = track.path
                    self._register(job)
                else:
                    job.state = STATE_FAILED
                    job.error = "本地文件不存在"
                    self._register(job)
                created.append(job)
                continue
            self._register(job)
            created.append(job)
            self._resolve(job)
        self.jobs_changed.emit()
        return created

    def cancel(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.state in {STATE_DONE, STATE_FAILED, STATE_CANCELLED}:
            return
        job.cancelled = True
        job.state = STATE_CANCELLED
        self._emit(job, final=True)

    def clear_finished(self) -> None:
        for job_id in list(self._order):
            job = self._jobs.get(job_id)
            if job and job.state in {STATE_DONE, STATE_FAILED, STATE_CANCELLED}:
                self._order.remove(job_id)
                self._jobs.pop(job_id, None)
        self.jobs_changed.emit()

    def open_folder(self) -> None:
        try:
            os.startfile(str(downloads_dir()))  # noqa: S606
        except OSError as exc:
            log.warning("打开下载目录失败：%s", exc)

    def shutdown(self) -> None:
        for job in self.active():
            job.cancelled = True
        self._pool.clear()
        self._pool.waitForDone(1500)

    # ---------------------------------------------------------------- 内部
    def _register(self, job: DownloadJob) -> None:
        self._jobs[job.id] = job
        self._order.append(job.id)
        self.job_updated.emit(job)

    def _resolve(self, job: DownloadJob) -> None:
        track = job.track
        source_id = track.source_id
        if not source_id:
            job.state = STATE_FAILED
            job.error = "缺少音源信息"
            self._emit(job, final=True)
            return
        if not self._client.ensure_started():
            job.state = STATE_FAILED
            job.error = self._client.last_error or "在线音源不可用"
            self._emit(job, final=True)
            return
        from ..online import models

        job.state = STATE_RESOLVING
        self._emit(job)
        payload: dict = {}

        def on_resolved(response: dict) -> None:
            payload.update(response)
            self._on_resolved(job, payload)

        self._client.resolve_download(
            source_id,
            models.runtime_track(track),
            on_resolved,
            quality=job.quality,
            timeout=45_000,
        )

    def _on_resolved(self, job: DownloadJob, response: dict) -> None:
        if job.state == STATE_CANCELLED:
            return
        if not response.get("ok"):
            job.state = STATE_FAILED
            job.error = str(response.get("error") or "音源没有返回可用的下载地址")
            self._emit(job, final=True)
            return
        data = response.get("data") or {}
        url = str(data.get("url") or "")
        if not url.startswith("http"):
            job.state = STATE_FAILED
            job.error = "音源返回的下载地址无效"
            self._emit(job, final=True)
            return
        headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
        fetch = _FetchJob(self, job, url, {str(k): str(v) for k, v in headers.items()})
        self._fetches[job.id] = fetch
        self._pool.start(fetch)

    def _record_success(self, job: DownloadJob) -> None:
        items = read_index()
        entry = {
            "track_id": job.track.id,
            "title": job.track.title,
            "artist": job.track.artist,
            "album": job.track.album,
            "source_id": job.track.source_id,
            "path": job.path,
            "size": job.downloaded,
            "quality": job.quality,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        items = [item for item in items if item.get("track_id") != entry["track_id"]]
        items.append(entry)
        _write_index(items)

    def _emit(self, job: DownloadJob, *, force: bool = False, final: bool = False) -> None:
        self.job_updated.emit(job)
        if final:
            if job.state == STATE_DONE:
                self.job_finished.emit(job)
            self.jobs_changed.emit()
