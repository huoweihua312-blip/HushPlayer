from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


class OnlineSourceClient(QObject):
    sourceReady = Signal(dict)
    sourceListReceived = Signal(list)
    searchFinished = Signal(int, str, list)
    metadataFinished = Signal(int, str, dict)
    lyricFinished = Signal(int, str, dict)
    playbackResolved = Signal(int, str, dict)
    downloadResolved = Signal(int, str, dict)
    sourceTestFinished = Signal(int, str, dict)
    responseReceived = Signal(int, str, object)
    requestFailed = Signal(int, str, str)
    processError = Signal(str)
    nodeLog = Signal(str)
    processStopped = Signal()

    def __init__(
        self,
        project_root: Path,
        parent: QObject | None = None,
        *,
        runtime_dir: Path | None = None,
        registry_path: Path | None = None,
        user_sources_dir: Path | None = None,
        bundled_node_executable: Path | None = None,
        frozen: bool | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = Path(project_root).resolve()
        self.runtime_dir = (
            Path(runtime_dir).resolve()
            if runtime_dir is not None
            else self.project_root / "source_runtime"
        )
        self.runner_path = self.runtime_dir / "runner.js"
        inherited_registry = str(os.environ.get("HUSHPLAYER_SOURCE_REGISTRY") or "").strip()
        if registry_path is not None:
            self.registry_path = Path(registry_path).resolve()
            self.source_home_dir = self.registry_path.parent
        elif inherited_registry:
            # Preserve the original test/development override contract: source
            # filenames remain relative to the bundled runtime unless the
            # caller explicitly supplies the separated writable registry.
            self.registry_path = Path(inherited_registry).resolve()
            self.source_home_dir = self.runtime_dir
        else:
            self.registry_path = self.runtime_dir / "source_registry.json"
            self.source_home_dir = self.runtime_dir
        inherited_user_sources = str(
            os.environ.get("HUSHPLAYER_USER_SOURCES") or ""
        ).strip()
        self.user_sources_dir = (
            Path(user_sources_dir).resolve()
            if user_sources_dir is not None
            else Path(inherited_user_sources).resolve()
            if inherited_user_sources
            else self.project_root / "user_sources"
        )
        self.bundled_node_executable = (
            Path(bundled_node_executable).resolve()
            if bundled_node_executable is not None
            else self.project_root / "runtime" / "node" / "node.exe"
        )
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
        if self.bundled_node_executable.is_file():
            self.node_program = str(self.bundled_node_executable)
        elif self.frozen:
            self.node_program = ""
        else:
            self.node_program = shutil.which("node") or ""
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.runtime_dir))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("HUSHPLAYER_SOURCE_REGISTRY", str(self.registry_path))
        environment.insert("HUSHPLAYER_SOURCE_HOME", str(self.source_home_dir))
        environment.insert("HUSHPLAYER_USER_SOURCES", str(self.user_sources_dir))
        node_modules = str(self.runtime_dir / "node_modules")
        inherited_node_path = environment.value("NODE_PATH")
        environment.insert(
            "NODE_PATH",
            os.pathsep.join(
                item for item in (node_modules, inherited_node_path) if item
            ),
        )
        self.process.setProcessEnvironment(environment)
        self.process.readyReadStandardOutput.connect(self._read_standard_output)
        self.process.readyReadStandardError.connect(self._read_standard_error)
        self.process.started.connect(self._on_started)
        self.process.errorOccurred.connect(self._on_process_error)
        self.process.finished.connect(self._on_finished)
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._next_request_id = 1
        self._pending: dict[int, dict] = {}
        self._outbound_queue: list[tuple[int, bytes]] = []
        self._stopping = False

    def is_running(self) -> bool:
        return self.process.state() == QProcess.ProcessState.Running

    def start(self) -> bool:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return True

        if not self.node_program:
            if self.frozen:
                self.processError.emit(
                    f"发布包缺少内置 Node.js：{self.bundled_node_executable}"
                )
            else:
                self.processError.emit("没有找到 Node.js，请确认 node 已安装并加入 PATH。")
            return False

        if not self.runner_path.exists():
            self.processError.emit(f"Node runner 不存在：{self.runner_path}")
            return False

        self._stopping = False
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self.process.setProgram(self.node_program)
        self.process.setArguments([str(self.runner_path)])
        self.process.start()
        return True

    def stop(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._fail_all_pending("Node runner 已停止")
            return

        self._stopping = True
        shutdown_request = json.dumps(
            {"id": 0, "action": "shutdown"},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        self.process.write(shutdown_request)
        self.process.closeWriteChannel()

        if not self.process.waitForFinished(900):
            self.process.terminate()

            if not self.process.waitForFinished(700):
                self.process.kill()
                self.process.waitForFinished(500)

        self._fail_all_pending("应用正在退出")

    def ping(self, timeout_ms: int = 5000) -> int:
        return self.request("ping", timeout_ms=timeout_ms)

    def list_sources(self, timeout_ms: int = 8000) -> int:
        return self.request("listSources", timeout_ms=timeout_ms)

    def search(
        self,
        source_id: str,
        keyword: str,
        page: int = 1,
        search_type: str = "music",
        timeout_ms: int = 25000,
    ) -> int:
        return self.request(
            "search",
            sourceId=source_id,
            keyword=keyword,
            page=page,
            type=search_type,
            timeout_ms=timeout_ms,
        )

    def get_metadata(self, source_id: str, music_item: dict, timeout_ms: int = 25000) -> int:
        return self.request(
            "getMetadata",
            sourceId=source_id,
            musicItem=music_item,
            timeout_ms=timeout_ms,
        )

    def get_lyric(self, source_id: str, music_item: dict, timeout_ms: int = 25000) -> int:
        return self.request(
            "getLyric",
            sourceId=source_id,
            musicItem=music_item,
            timeout_ms=timeout_ms,
        )

    def resolve_playback(
        self,
        source_id: str,
        track: dict,
        quality: str = "standard",
        timeout_ms: int = 25000,
    ) -> int:
        return self.request(
            "resolvePlayback",
            sourceId=source_id,
            track=track,
            options={"quality": quality},
            timeout_ms=timeout_ms,
        )

    def resolve_download(
        self,
        source_id: str,
        track: dict,
        quality: str = "standard",
        timeout_ms: int = 25000,
    ) -> int:
        return self.request(
            "resolveDownload",
            sourceId=source_id,
            track=track,
            options={"quality": quality},
            timeout_ms=timeout_ms,
        )

    def cancel_request(self, request_id: int) -> bool:
        pending = self._pending.pop(int(request_id), None)
        if pending is None:
            return False

        pending["timer"].stop()
        pending["timer"].deleteLater()
        if self.is_running():
            payload = json.dumps(
                {"id": 0, "action": "cancel", "requestId": int(request_id)},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            self.process.write(payload)
        return True

    def test_source(self, source_id: str, keyword: str = "测试", timeout_ms: int = 50000) -> int:
        return self.request(
            "testSource",
            sourceId=source_id,
            keyword=keyword,
            timeout_ms=timeout_ms,
        )

    def reload_sources(self, source_id: str = "", timeout_ms: int = 10000) -> int:
        payload = {"sourceId": source_id} if source_id else {}
        return self.request("reloadSource", timeout_ms=timeout_ms, **payload)

    def request(self, action: str, timeout_ms: int = 20000, **payload) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        request = {"id": request_id, "action": action, **payload}
        encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda current_id=request_id: self._on_request_timeout(current_id))
        self._pending[request_id] = {
            "action": action,
            "sourceId": str(payload.get("sourceId") or ""),
            "timer": timer,
        }
        timer.start(max(1000, int(timeout_ms)))

        if self.is_running():
            self.process.write(encoded)
        else:
            self._outbound_queue.append((request_id, encoded))

            if not self.start():
                self._fail_request(request_id, "Node runner 无法启动")

        return request_id

    def _on_started(self) -> None:
        queued = list(self._outbound_queue)
        self._outbound_queue.clear()

        for request_id, payload in queued:
            if request_id in self._pending:
                self.process.write(payload)

        self.ping()

    def _read_standard_output(self) -> None:
        self._stdout_buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")

        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            line = line.strip()

            if line:
                self._handle_response_line(line)

    def _read_standard_error(self) -> None:
        self._stderr_buffer += bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")

        while "\n" in self._stderr_buffer:
            line, self._stderr_buffer = self._stderr_buffer.split("\n", 1)
            line = line.rstrip()

            if line:
                self.nodeLog.emit(line)

    def _handle_response_line(self, line: str) -> None:
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            self.processError.emit(f"Node runner 返回了非 JSON 内容：{error}: {line[:240]}")
            return

        request_id = response.get("id")

        if not isinstance(request_id, int):
            self.processError.emit("Node runner 响应缺少有效请求 id")
            return

        pending = self._pending.pop(request_id, None)

        if pending is None:
            if request_id != 0:
                self.nodeLog.emit(f"收到已过期或未知请求的响应：{request_id}")
            return

        timer = pending["timer"]
        timer.stop()
        timer.deleteLater()
        action = pending["action"]
        source_id = pending["sourceId"]

        if not response.get("success"):
            error = response.get("error") or {}
            message = str(error.get("message") or "未知音源错误")
            self.requestFailed.emit(request_id, action, message)
            return

        data = response.get("data")
        self.responseReceived.emit(request_id, action, data)

        if action == "ping" and isinstance(data, dict):
            self.sourceReady.emit(data)
        elif action in {"listSources", "reloadSource"} and isinstance(data, list):
            self.sourceListReceived.emit(data)
        elif action == "search" and isinstance(data, list):
            self.searchFinished.emit(request_id, source_id, data)
        elif action == "getMetadata" and isinstance(data, dict):
            self.metadataFinished.emit(request_id, source_id, data)
        elif action == "getLyric" and isinstance(data, dict):
            self.lyricFinished.emit(request_id, source_id, data)
        elif action == "resolvePlayback" and isinstance(data, dict):
            self.playbackResolved.emit(request_id, source_id, data)
        elif action == "resolveDownload" and isinstance(data, dict):
            self.downloadResolved.emit(request_id, source_id, data)
        elif action == "testSource" and isinstance(data, dict):
            self.sourceTestFinished.emit(request_id, source_id, data)

    def _on_request_timeout(self, request_id: int) -> None:
        pending = self._pending.pop(request_id, None)

        if pending is None:
            return

        pending["timer"].deleteLater()
        if self.is_running():
            payload = json.dumps(
                {"id": 0, "action": "cancel", "requestId": int(request_id)},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            self.process.write(payload)
        self.requestFailed.emit(request_id, pending["action"], "请求超时，请检查网络或音源状态。")

    def _fail_request(self, request_id: int, message: str) -> None:
        pending = self._pending.pop(request_id, None)

        if pending is None:
            return

        pending["timer"].stop()
        pending["timer"].deleteLater()
        self.requestFailed.emit(request_id, pending["action"], message)

    def _fail_all_pending(self, message: str) -> None:
        for request_id in list(self._pending):
            self._fail_request(request_id, message)

        self._outbound_queue.clear()

    def _on_process_error(self, _error) -> None:
        message = self.process.errorString() or "Node runner 进程错误"
        self.processError.emit(message)

        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._fail_all_pending(message)

    def _on_finished(self, _exit_code: int, _exit_status) -> None:
        if self._stderr_buffer.strip():
            self.nodeLog.emit(self._stderr_buffer.strip())
            self._stderr_buffer = ""

        if not self._stopping:
            self._fail_all_pending("Node runner 意外退出")
            self.processError.emit("Node runner 已退出；下次请求时会自动重启。")

        self.processStopped.emit()
