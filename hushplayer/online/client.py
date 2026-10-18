"""Client for the bundled Node.js online-source runtime.

The runtime is a long lived Node process that speaks newline delimited JSON on
stdin/stdout.  Every request carries an ``id`` and every response echoes it::

    {"id": 1, "success": true,  "data": ...}
    {"id": 2, "success": false, "error": {"message": "...", "stack": "..."}}

The client keeps the process warm between searches, dispatches responses to
per-request callbacks on the Qt main thread and transparently restarts a dead
runtime on the next request.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any, Callable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("online.client")

DEFAULT_TIMEOUT_MS = 25000
STARTUP_TIMEOUT_MS = 20000

Response = dict[str, Any]
Callback = Callable[[Response], None]


class OnlineSourceError(RuntimeError):
    """Raised when the runtime cannot be started at all."""


def _bundled_node() -> str:
    """Locate a Node.js executable usable by the source runtime."""
    try:
        candidate = paths.bundled_node()
    except Exception:  # pragma: no cover - defensive
        candidate = None
    if candidate and os.path.isfile(candidate):
        return candidate
    found = shutil.which("node")
    return found or ""


def runtime_available() -> bool:
    return bool(_bundled_node())


class OnlineSourceClient(QObject):
    """JSONL client around ``source_runtime/runner.js``."""

    ready = Signal(dict)          # ping payload
    state_changed = Signal(bool)  # running / stopped
    sources_changed = Signal(list)
    log_line = Signal(str)
    failure = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._buffer = b""
        self._pending: dict[int, tuple[Callback | None, QTimer, str]] = {}
        self._next_id = 0
        self._queue: list[tuple[int, str, dict[str, Any], int]] = []
        self._starting = False
        self._started_at = 0.0
        self._last_error = ""
        self._sources: list[dict[str, Any]] = []
        self._shutting_down = False

    # ------------------------------------------------------------- process
    @property
    def running(self) -> bool:
        return (
            self._process is not None
            and self._process.state() != QProcess.ProcessState.NotRunning
        )

    @property
    def sources(self) -> list[dict[str, Any]]:
        return self._sources

    @property
    def last_error(self) -> str:
        return self._last_error

    def _runner_path(self) -> str:
        runtime = paths.runtime_dir()
        if runtime is None:
            return ""
        runner = os.path.join(str(runtime), "runner.js")
        return runner if os.path.isfile(runner) else ""

    def ensure_started(self) -> bool:
        """Start the runtime if needed.  Returns False when unusable."""
        if self.running:
            return True
        if self._shutting_down:
            return False
        runner = self._runner_path()
        if not runner:
            self._last_error = "缺少在线音源运行时（runner.js），在线功能不可用。"
            self.failure.emit(self._last_error)
            return False
        node = _bundled_node()
        if not node:
            self._last_error = "没有找到 Node.js，在线音源不可用。请安装 Node.js 或使用完整安装包。"
            self.failure.emit(self._last_error)
            return False

        runtime_dir = os.path.dirname(runner)
        process = QProcess(self)
        process.setProgram(node)
        process.setArguments([runner])
        process.setWorkingDirectory(runtime_dir)

        env = QProcessEnvironment.systemEnvironment()
        registry = os.path.join(runtime_dir, "source_registry.json")
        user_sources = os.path.join(os.path.dirname(runtime_dir), "user_sources")
        node_modules = os.path.join(runtime_dir, "node_modules")
        env.insert("HUSHPLAYER_SOURCE_REGISTRY", registry)
        env.insert("HUSHPLAYER_SOURCE_HOME", runtime_dir)
        env.insert("HUSHPLAYER_USER_SOURCES", user_sources)
        inherited = env.value("NODE_PATH", "")
        parts = [p for p in (node_modules, inherited) if p]
        env.insert("NODE_PATH", os.pathsep.join(parts))
        env.insert("NODE_NO_WARNINGS", "1")
        process.setProcessEnvironment(env)

        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_process_error)

        self._process = process
        self._buffer = b""
        self._starting = True
        self._started_at = time.monotonic()
        process.start()
        if not process.waitForStarted(6000):
            self._last_error = "在线音源运行器启动失败。"
            self._starting = False
            self.failure.emit(self._last_error)
            return False
        log.info("online runtime started: %s", node)
        self.state_changed.emit(True)
        self._flush_queue()
        QTimer.singleShot(0, self.ping)
        return True

    def ping(self, callback: Callback | None = None) -> int | None:
        return self.request("ping", {}, callback or self._on_ping, timeout=8000)

    def _on_ping(self, response: Response) -> None:
        if response.get("ok"):
            self.ready.emit(response.get("data") or {})
        self.refresh_sources()

    def refresh_sources(self, callback: Callback | None = None) -> int | None:
        return self.request("listSources", {}, callback or self._on_sources, timeout=15000)

    def _on_sources(self, response: Response) -> None:
        if not response.get("ok"):
            return
        data = response.get("data") or []
        if isinstance(data, dict):
            data = data.get("sources") or []
        self._sources = [item for item in data if isinstance(item, dict)]
        self.sources_changed.emit(self._sources)

    def stop(self, timeout_ms: int = 2500) -> None:
        """Ask the runtime to shut down and make sure the process dies."""
        self._shutting_down = True
        self._fail_pending("在线音源已关闭")
        process = self._process
        if process is None:
            return
        if process.state() != QProcess.ProcessState.NotRunning:
            try:
                self._write({"id": 0, "action": "shutdown"})
            except Exception:  # pragma: no cover - best effort
                pass
            process.closeWriteChannel()
            if not process.waitForFinished(timeout_ms):
                process.terminate()
                if not process.waitForFinished(1200):
                    process.kill()
                    process.waitForFinished(600)
        self._process = None

    def shutdown(self) -> None:
        self.stop()

    # ------------------------------------------------------------- requests
    def search(
        self,
        source_id: str,
        keyword: str,
        page: int = 1,
        callback: Callback | None = None,
        *,
        timeout: int = DEFAULT_TIMEOUT_MS,
        kind: str = "music",
    ) -> int | None:
        payload = {
            "sourceId": source_id,
            "keyword": keyword,
            "page": int(page),
            "type": kind,
        }
        return self.request("search", payload, callback, timeout=timeout)

    def get_lyric(
        self,
        source_id: str,
        music_item: dict[str, Any] | str,
        callback: Callback | None = None,
        *,
        timeout: int = 15000,
    ) -> int | None:
        return self.request(
            "getLyric",
            {"sourceId": source_id, "musicItem": music_item},
            callback,
            timeout=timeout,
        )

    def get_metadata(
        self,
        source_id: str,
        music_item: dict[str, Any] | str,
        callback: Callback | None = None,
        *,
        timeout: int = 15000,
    ) -> int | None:
        return self.request(
            "getMetadata",
            {"sourceId": source_id, "musicItem": music_item},
            callback,
            timeout=timeout,
        )

    def resolve_playback(
        self,
        source_id: str,
        track: dict[str, Any] | str,
        callback: Callback | None = None,
        *,
        quality: str = "standard",
        timeout: int = 22000,
    ) -> int | None:
        return self.request(
            "resolvePlayback",
            {"sourceId": source_id, "track": track, "options": {"quality": quality}},
            callback,
            timeout=timeout,
        )

    def resolve_download(
        self,
        source_id: str,
        track: dict[str, Any] | str,
        callback: Callback | None = None,
        *,
        quality: str = "standard",
        timeout: int = 30000,
    ) -> int | None:
        return self.request(
            "resolveDownload",
            {"sourceId": source_id, "track": track, "options": {"quality": quality}},
            callback,
            timeout=timeout,
        )

    def reload_source(self, source_id: str = "", callback: Callback | None = None) -> int | None:
        payload = {"sourceId": source_id} if source_id else {}
        return self.request("reloadSource", payload, callback, timeout=30000)

    def request(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        callback: Callback | None = None,
        *,
        timeout: int = DEFAULT_TIMEOUT_MS,
    ) -> int | None:
        """Queue one request.  Returns the request id, or None if unusable."""
        if not self.ensure_started():
            if callback is not None:
                QTimer.singleShot(
                    0,
                    lambda: callback(
                        {"ok": False, "error": self._last_error, "action": action}
                    ),
                )
            return None

        self._next_id += 1
        request_id = self._next_id
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(max(2000, int(timeout)))
        timer.timeout.connect(lambda: self._on_timeout(request_id))
        self._pending[request_id] = (callback, timer, action)
        timer.start()

        message = {"id": request_id, "action": action}
        if payload:
            message.update(payload)
        if not self.running:
            self._queue.append((request_id, action, message, timeout))
            return request_id
        self._write(message)
        return request_id

    def cancel(self, request_id: int) -> None:
        """Drop a pending request locally and tell the runtime to skip it."""
        entry = self._pending.pop(request_id, None)
        if entry is not None:
            entry[1].stop()
            entry[1].deleteLater()
        self._queue = [item for item in self._queue if item[0] != request_id]
        if self.running:
            try:
                self._write({"id": 0, "action": "cancel", "requestId": int(request_id)})
            except Exception:  # pragma: no cover
                pass

    def cancel_where(self, prefix_action: str) -> None:
        for request_id, (_cb, _timer, action) in list(self._pending.items()):
            if action == prefix_action or action.startswith(prefix_action):
                self.cancel(request_id)

    # ------------------------------------------------------------- internals
    def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            raise OnlineSourceError("在线音源运行器未运行")
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        process.write(data)

    def _flush_queue(self) -> None:
        queue, self._queue = self._queue, []
        for request_id, _action, message, _timeout in queue:
            if request_id not in self._pending:
                continue
            try:
                self._write(message)
            except Exception as exc:  # pragma: no cover
                self._fail(request_id, f"无法写入在线音源：{exc}")
        self._starting = False

    def _on_stdout(self) -> None:
        process = self._process
        if process is None:
            return
        self._buffer += bytes(process.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            text = line.decode("utf-8", "replace").strip()
            if text:
                self._handle_line(text)

    def _handle_line(self, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            log.debug("non-json stdout: %s", text[:400])
            return
        if not isinstance(message, dict):
            return
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        callback, timer, _action = self._pending.pop(request_id, (None, None, ""))
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        if message.get("success") is True:
            response: Response = {"ok": True, "data": message.get("data"), "id": request_id}
        else:
            error = message.get("error") or {}
            if isinstance(error, dict):
                detail = str(error.get("message") or "未知错误").strip()
            else:
                detail = str(error or "未知错误").strip()
            response = {"ok": False, "error": detail, "id": request_id}
            log.info("runtime error: %s", detail)
        if callback is not None:
            try:
                callback(response)
            except Exception:
                log.exception("online callback failed")

    def _on_stderr(self) -> None:
        process = self._process
        if process is None:
            return
        raw = bytes(process.readAllStandardError()).decode("utf-8", "replace")
        for line in raw.splitlines():
            line = line.rstrip()
            if line:
                log.info("runtime: %s", line)
                self.log_line.emit(line)

    def _on_timeout(self, request_id: int) -> None:
        entry = self._pending.pop(request_id, None)
        if entry is None:
            return
        callback, timer, action = entry
        timer.deleteLater()
        message = f"在线音源响应超时（{action}）"
        log.info(message)
        if callback is not None:
            callback({"ok": False, "error": message, "timeout": True})
        self.cancel(request_id)

    def _fail(self, request_id: int, message: str) -> None:
        entry = self._pending.pop(request_id, None)
        if entry is None:
            return
        callback, timer, _action = entry
        timer.stop()
        timer.deleteLater()
        if callback is not None:
            callback({"ok": False, "error": message})

    def _fail_pending(self, message: str) -> None:
        for request_id in list(self._pending):
            self._fail(request_id, message)
        self._queue.clear()

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._starting = False
        self._process = None
        self.state_changed.emit(False)
        crashed = not self._shutting_down
        if crashed:
            self._last_error = f"在线音源运行器已退出（代码 {code}）"
            log.warning(self._last_error)
            self._fail_pending(self._last_error)
        else:
            self._fail_pending("在线音源已关闭")

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        self._last_error = f"在线音源运行器错误：{error.name if hasattr(error, 'name') else error}"
        log.warning(self._last_error)
        if error == QProcess.ProcessError.FailedToStart:
            self._starting = False
            self._process = None
            self.state_changed.emit(False)
            self._fail_pending(self._last_error)
            self.failure.emit(self._last_error)

    def __del__(self) -> None:  # pragma: no cover - defensive teardown
        try:
            process = self._process
            if process is not None and process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
        except Exception:
            pass
