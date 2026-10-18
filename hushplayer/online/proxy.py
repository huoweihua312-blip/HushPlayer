"""在线音频本地代理 + 磁盘缓存。

为什么需要它：
* 在线音源解析出的 URL 往往要求特定 Referer / User-Agent，Qt 的播放后端不一定能加；
* 需要 Range 支持以拖动进度；
* 需要把流写进磁盘缓存，长时间暂停/二次播放不重复下载。

实现：127.0.0.1 上的随机端口 HTTP 服务，``/audio/<token>`` 暴露某个已注册资源。
下载线程直接把字节追加写入目标缓存文件（Windows 上「写一个文件、同时读同一个文件」是允许的，
而写完再改名会被正在读取的句柄挡住，所以不采用临时文件改名方案）。
请求线程在所需字节尚未就绪时短暂等待，因此首次播放即可边下边播。

完整性由同名 ``.meta.json`` 记录：标记 ``complete`` 且大小一致才复用，
避免把上次崩溃留下的半截文件当成完整缓存。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("proxy")

_CHUNK = 64 * 1024
_READY_TIMEOUT = 45.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HushPlayer/1.0"

_MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
}
_AUDIO_EXTS = set(_MIME_BY_EXT)


def _ext_from_mime(mime: str) -> str:
    mime = (mime or "").lower()
    if "flac" in mime:
        return ".flac"
    if "mp4" in mime or "m4a" in mime or "aac" in mime:
        return ".m4a"
    if "ogg" in mime or "opus" in mime:
        return ".ogg"
    if "wav" in mime:
        return ".wav"
    return ".mp3"


def _ext_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in _AUDIO_EXTS else ".mp3"


def token_for(cache_key: str) -> str:
    return hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:24]


def _read_meta(path: Path) -> dict:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def _write_meta(path: Path, data: dict) -> None:
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


class Download:
    """一个远程音频的下载/缓存任务。"""

    def __init__(
        self,
        token: str,
        url: str,
        headers: dict | None,
        dest: Path,
        *,
        meta_path: Path | None = None,
        expires_at: float = 0.0,
    ) -> None:
        self.token = token
        self.url = url
        self.headers = headers or {}
        self.dest = dest
        self.meta_path = meta_path or dest.with_suffix(".meta.json")
        self.expires_at = expires_at
        self.total = 0
        self.available = 0
        self.complete = False
        self.error = ""
        self.cancelled = False
        self.started_at = time.time()
        self.last_access = time.time()
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None

    # -- 生命周期 --------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None or self.complete:
            return
        self._thread = threading.Thread(
            target=self._run, name=f"audio-dl-{self.token[:6]}", daemon=True
        )
        self._thread.start()

    def cancel(self) -> None:
        self.cancelled = True
        with self._cond:
            self._cond.notify_all()

    def wait_for(self, offset: int, timeout: float = _READY_TIMEOUT) -> bool:
        """等待「已写入字节数 > offset」或任务结束。"""
        if offset < self.available or self.complete or self.error:
            return True
        deadline = time.monotonic() + timeout
        with self._cond:
            while offset >= self.available and not self.complete and not self.error:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(min(0.4, remaining))
        return True

    def _notify(self) -> None:
        with self._cond:
            self._cond.notify_all()

    # -- 下载 ------------------------------------------------------------
    def _run(self) -> None:
        try:
            import requests

            headers = {
                "User-Agent": _USER_AGENT,
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            }
            headers.update({str(k): str(v) for k, v in self.headers.items()})
            self.dest.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(self.url, headers=headers, stream=True, timeout=(12, 45)) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}")
                length = response.headers.get("Content-Length")
                self.total = int(length) if length and length.isdigit() else 0
                written = 0
                with open(self.dest, "wb") as handle:
                    for chunk in response.iter_content(_CHUNK):
                        if self.cancelled:
                            return
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        with self._cond:
                            self.available = written
                            self._cond.notify_all()
                    handle.flush()
                    os.fsync(handle.fileno())
            if self.total and written < self.total:
                raise RuntimeError(f"下载不完整 {written}/{self.total}")
            self.total = written
            self.available = written
            self.complete = True
            _write_meta(
                self.meta_path,
                {
                    "complete": True,
                    "size": written,
                    "url": self.url,
                    "created": self.started_at,
                    "expires_at": self.expires_at,
                },
            )
            log.info("已缓存音频 %s (%.1f MB)", self.dest.name, written / 1048576)
        except Exception as exc:
            if not self.cancelled:
                log.warning("在线音频下载失败 %s: %s", self.url[:120], exc)
                self.error = str(exc)
                try:
                    _write_meta(self.meta_path, {"complete": False, "error": str(exc)[:200]})
                except Exception:
                    pass
        finally:
            self._notify()


class AudioProxy:
    """管理缓存任务并对外提供本地播放 URL。"""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = Path(cache_dir or paths.audio_cache_dir())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._downloads: dict[str, Download] = {}
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    # -- HTTP 服务 -------------------------------------------------------
    def ensure_server(self) -> int:
        if self._server is not None:
            return self.port
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                log.debug("proxy %s - %s", self.address_string(), fmt % args)

            def do_HEAD(self) -> None:
                proxy._serve(self, head_only=True)

            def do_GET(self) -> None:
                proxy._serve(self, head_only=False)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        self._server = server
        self.port = server.server_address[1]
        self._thread = threading.Thread(
            target=server.serve_forever, name="audio-proxy", daemon=True
        )
        self._thread.start()
        log.info("本地音频代理已启动 127.0.0.1:%s", self.port)
        return self.port

    def shutdown(self) -> None:
        self.cancel_all()
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    # -- 注册 ------------------------------------------------------------
    def register(
        self,
        cache_key: str,
        url: str,
        headers: dict | None = None,
        *,
        mime: str = "",
        ext: str = "",
        expires_at: float = 0.0,
    ) -> str:
        """注册远程资源，返回给播放器使用的本地 URL。"""
        self.ensure_server()
        token = token_for(cache_key)
        suffix = ext if ext.startswith(".") else (_ext_from_mime(mime) if mime else _ext_from_url(url))
        dest = self.cache_dir / f"{token}{suffix}"
        meta_path = self.cache_dir / f"{token}.meta.json"

        with self._lock:
            download = self._downloads.get(token)

        if download is None:
            meta = _read_meta(meta_path)
            size = dest.stat().st_size if dest.exists() else 0
            if meta.get("complete") and size and int(meta.get("size", 0)) == size:
                download = Download(token, url, headers, dest, meta_path=meta_path)
                download.total = size
                download.available = size
                download.complete = True
            else:
                if dest.exists():
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                download = Download(
                    token, url, headers, dest, meta_path=meta_path, expires_at=expires_at
                )
                with self._lock:
                    self._downloads[token] = download
                download.start()
            with self._lock:
                self._downloads[token] = download
        else:
            download.last_access = time.time()
            if download.error:
                download.error = ""
                download.cancelled = False
                download._thread = None
                download.start()

        return f"http://127.0.0.1:{self.port}/audio/{token}"

    def local_path(self, cache_key: str) -> str:
        """若缓存已完整，返回本地文件路径（下载功能复用同一份缓存）。"""
        token = token_for(cache_key)
        with self._lock:
            download = self._downloads.get(token)
        if download is not None and download.complete and download.dest.exists():
            return str(download.dest)
        meta = _read_meta(self.cache_dir / f"{token}.meta.json")
        if meta.get("complete"):
            for candidate in self.cache_dir.glob(f"{token}.*"):
                if candidate.suffix != ".json" and candidate.stat().st_size > 0:
                    return str(candidate)
        return ""

    def cancel_all(self) -> None:
        with self._lock:
            downloads = list(self._downloads.values())
        for download in downloads:
            download.cancel()

    def stats(self) -> dict:
        total = 0
        files = 0
        try:
            for entry in os.scandir(self.cache_dir):
                if entry.is_file() and not entry.name.endswith(".json"):
                    total += entry.stat().st_size
                    files += 1
        except OSError:
            pass
        return {"files": files, "bytes": total}

    def clear_cache(self) -> int:
        self.cancel_all()
        with self._lock:
            self._downloads.clear()
        removed = 0
        try:
            for entry in os.scandir(self.cache_dir):
                if not entry.is_file():
                    continue
                try:
                    os.unlink(entry.path)
                    removed += 1
                except OSError:
                    pass
        except OSError:
            pass
        return removed

    def prune(self, max_bytes: int) -> int:
        if max_bytes <= 0:
            return 0
        try:
            entries = [
                (entry.stat().st_mtime, entry.stat().st_size, entry.path)
                for entry in os.scandir(self.cache_dir)
                if entry.is_file() and not entry.name.endswith(".json")
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
                os.unlink(str(Path(path).with_suffix(".meta.json")))
            except OSError:
                pass
            try:
                total -= size
                removed += 1
            except Exception:
                pass
        return removed

    # -- 请求处理 --------------------------------------------------------
    def _resolve(self, raw_path: str) -> Download | None:
        if not raw_path.startswith("/audio/"):
            return None
        token = raw_path[len("/audio/") :].split("?", 1)[0]
        with self._lock:
            download = self._downloads.get(token)
        if download is not None:
            download.last_access = time.time()
            return download
        meta = _read_meta(self.cache_dir / f"{token}.meta.json")
        for candidate in self.cache_dir.glob(f"{token}.*"):
            if candidate.suffix == ".json":
                continue
            download = Download(token, "", {}, candidate, meta_path=self.cache_dir / f"{token}.meta.json")
            download.total = candidate.stat().st_size
            download.available = download.total
            download.complete = bool(meta.get("complete"))
            with self._lock:
                self._downloads[token] = download
            return download
        return None

    def _serve(self, handler: BaseHTTPRequestHandler, *, head_only: bool) -> None:
        download = self._resolve(handler.path)
        if download is None:
            handler.send_error(404, "unknown audio token")
            return

        range_header = handler.headers.get("Range", "")
        start = 0
        end = -1
        if range_header.startswith("bytes="):
            spec = range_header[6:].split(",")[0].strip()
            try:
                left, _, right = spec.partition("-")
                start = int(left) if left else 0
                end = int(right) if right else -1
            except ValueError:
                start, end = 0, -1

        if not download.complete and not download.error:
            download.start()
        if not download.complete and not download.wait_for(max(start, 1)):
            if download.error:
                handler.send_error(502, download.error[:160] or "audio unavailable")
            else:
                handler.send_error(504, "audio not ready")
            return

        path = download.dest
        if not path.exists():
            handler.send_error(502, download.error[:160] or "audio unavailable")
            return

        size = path.stat().st_size
        total = download.total or (size if download.complete else 0)
        if total and start >= total:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{total}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        if end < 0 or (total and end >= total):
            end = (total or size) - 1
        if end < start:
            end = start

        length = end - start + 1
        status = 206 if range_header else 200
        handler.send_response(status)
        handler.send_header("Content-Type", _MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream"))
        handler.send_header("Accept-Ranges", "bytes")
        if status == 206:
            handler.send_header(
                "Content-Range", f"bytes {start}-{end}/{total if total else '*'}"
            )
        handler.send_header("Content-Length", str(length))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        if head_only:
            return

        sent = 0
        try:
            with open(path, "rb") as handle:
                handle.seek(start)
                while sent < length:
                    want = min(_CHUNK, length - sent)
                    if not download.complete:
                        if not download.wait_for(start + sent + want, timeout=30.0):
                            break
                        try:
                            size = path.stat().st_size
                        except OSError:
                            break
                        want = min(want, size - (start + sent))
                        if want <= 0:
                            break
                    data = handle.read(want)
                    if not data:
                        break
                    handler.wfile.write(data)
                    sent += len(data)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pragma: no cover - 网络异常
            log.debug("代理写出失败: %s", exc)
