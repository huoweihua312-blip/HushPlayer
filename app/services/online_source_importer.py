"""Async URL-source management for the Quiet Orbit online-source surface."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.core.version import APP_USER_AGENT
from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import (
    MAX_SOURCE_BYTES,
    SourceRegistryError,
    SourceRegistryManager,
)


class OnlineSourceImporter(QObject):
    """Own one cancellable URL-import queue without creating a second registry."""

    status_changed = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    sources_changed = Signal()
    busy_changed = Signal(bool)

    def __init__(
        self,
        registry: SourceRegistryManager,
        client: OnlineSourceClient,
        parent: QObject | None = None,
        *,
        network_manager: QNetworkAccessManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.client = client
        self.network_manager = network_manager or QNetworkAccessManager(self)
        self._queue: list[dict[str, str]] = []
        self._active_reply: QNetworkReply | None = None
        self._active_entry: dict[str, str] | None = None
        self._failed_messages: list[str] = []
        self._completed_count = 0
        self._skipped_count = 0
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def prepare_urls(self, text: str) -> tuple[list[str], list[str], int]:
        urls: list[str] = []
        errors: list[str] = []
        duplicate_count = 0
        seen: set[str] = set()
        for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
            value = raw_line.strip()
            if not value:
                continue
            try:
                normalized = self.registry.normalize_source_url(value)
                suffix = Path(urlsplit(normalized).path).suffix.lower()
                if suffix not in {".js", ".json"}:
                    raise SourceRegistryError("URL 必须指向 .js 或 .json 文件")
                if normalized in seen or self.registry.find_by_source_url(normalized) is not None:
                    duplicate_count += 1
                    continue
            except SourceRegistryError as error:
                errors.append(f"第 {line_number} 行：{error}")
                continue
            seen.add(normalized)
            urls.append(normalized)
        return urls, errors, duplicate_count

    def import_urls(self, text: str, content_policy: str) -> bool:
        if self._busy:
            self.failed.emit("已有来源正在添加，请等待当前操作完成。")
            return False
        policy = str(content_policy or "").strip().lower()
        if policy not in {"open", "user_owned"}:
            self.failed.emit("添加来源前必须选择内容授权范围。")
            return False
        urls, errors, duplicate_count = self.prepare_urls(text)
        if errors:
            self.failed.emit("；".join(errors[:4]))
            return False
        if not urls:
            message = (
                "输入的来源均已注册，没有重复安装。"
                if duplicate_count
                else "请输入至少一个 .js 或 .json URL。"
            )
            self.failed.emit(message)
            return False
        self._queue = [
            {"url": url, "policy": policy}
            for url in urls
        ]
        self._failed_messages = []
        self._completed_count = 0
        self._skipped_count = duplicate_count
        self._set_busy(True)
        self._start_next()
        return True

    def set_enabled(self, source_id: str, enabled: bool) -> bool:
        try:
            self.registry.set_enabled(str(source_id or ""), bool(enabled))
        except SourceRegistryError as error:
            self.failed.emit(str(error))
            return False
        self._reload_sources()
        return True

    def remove_source(self, source_id: str) -> bool:
        try:
            self.registry.remove_source(str(source_id or ""))
        except SourceRegistryError as error:
            self.failed.emit(str(error))
            return False
        self._reload_sources()
        self.completed.emit("在线来源已移除。")
        return True

    def shutdown(self) -> None:
        self.cancel()

    def cancel(self) -> None:
        self._queue.clear()
        if self._active_reply is not None:
            self._active_reply.abort()
            self._active_reply.deleteLater()
            self._active_reply = None
        self._active_entry = None
        self._set_busy(False)

    def _start_next(self) -> None:
        if not self._queue:
            self._finish_queue()
            return
        entry = self._queue.pop(0)
        self._active_entry = entry
        request = QNetworkRequest(QUrl(entry["url"]))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setRawHeader(b"User-Agent", f"{APP_USER_AGENT} quiet-orbit-source-manager".encode("ascii"))
        request.setRawHeader(b"Accept", b"application/javascript, application/json, text/plain, */*")
        reply = self.network_manager.get(request)
        self._active_reply = reply
        self.status_changed.emit(
            f"正在下载并检查来源，剩余 {len(self._queue) + 1} 个…"
        )
        reply.downloadProgress.connect(
            lambda received, total, current=reply: self._guard_size(current, received, total)
        )
        reply.finished.connect(lambda current=reply: self._finish_reply(current))

    @staticmethod
    def _guard_size(reply: QNetworkReply, received: int, total: int) -> None:
        if received > MAX_SOURCE_BYTES or total > MAX_SOURCE_BYTES:
            reply.setProperty("sourceTooLarge", True)
            reply.abort()

    def _finish_reply(self, reply: QNetworkReply) -> None:
        if reply is not self._active_reply:
            reply.deleteLater()
            return
        entry = dict(self._active_entry or {})
        self._active_reply = None
        self._active_entry = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = (
                "来源文件超过 2 MB"
                if reply.property("sourceTooLarge")
                else reply.errorString()
            )
            self._failed_messages.append(message)
            reply.deleteLater()
            self._start_next()
            return
        content = bytes(reply.readAll())
        suggested_name = Path(reply.url().path()).name or "custom_source.js"
        reply.deleteLater()
        try:
            candidate = self.registry.stage_bytes(
                content,
                suggested_name,
                source_url=entry.get("url", ""),
                content_policy=entry.get("policy", "unknown"),
                user_installed=True,
            )
            self.registry.install_candidate(candidate, enabled=True)
            self._completed_count += 1
        except SourceRegistryError as error:
            self._failed_messages.append(str(error))
        self._start_next()

    def _finish_queue(self) -> None:
        self._set_busy(False)
        if self._completed_count:
            self._reload_sources()
        parts = [f"成功 {self._completed_count} 个"]
        if self._skipped_count:
            parts.append(f"重复 {self._skipped_count} 个")
        if self._failed_messages:
            parts.append(f"失败 {len(self._failed_messages)} 个")
        message = "来源处理完成：" + "，".join(parts) + "。"
        if self._completed_count:
            self.completed.emit(message)
        else:
            self.failed.emit(message)

    def _reload_sources(self) -> None:
        self.client.reload_sources(timeout_ms=10000)
        self.sources_changed.emit()

    def _set_busy(self, busy: bool) -> None:
        value = bool(busy)
        if value == self._busy:
            return
        self._busy = value
        self.busy_changed.emit(value)
