"""Asynchronous remote-media resolution for the one production player."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from app.models.playback_queue_item import PlaybackQueueItem
from app.services.online_source_client import OnlineSourceClient


@dataclass(slots=True)
class _PendingResolution:
    token: int
    generation: int
    identity: str
    source_id: str
    client_request_id: int = 0
    timeout_timer: QTimer | None = None


class OnlineMediaResolver(QObject):
    """Resolve one remote queue item without owning multimedia state."""

    RESOLVE_TIMEOUT_MS = 20_000

    resolve_started = Signal(int, int, str)
    resolve_succeeded = Signal(int, int, str, object)
    resolve_failed = Signal(int, int, str, str, str)
    status_changed = Signal(str, str)

    def __init__(
        self,
        client: OnlineSourceClient,
        parent: QObject | None = None,
        *,
        source_catalog_provider: Callable[[], list[dict]] | None = None,
        source_catalog_loaded: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self._source_catalog_provider = source_catalog_provider
        self._source_catalog_loaded = source_catalog_loaded
        self._next_token = 1
        self._pending: dict[int, _PendingResolution] = {}
        self._client_to_token: dict[int, int] = {}
        self._active_token = 0
        self._closed = False
        client.playbackResolved.connect(self._on_playback_resolved)
        client.requestFailed.connect(self._on_request_failed)

    @property
    def active_token(self) -> int:
        return self._active_token

    def resolve(self, item: PlaybackQueueItem, generation: int) -> int:
        """Start one resolve and return a resolver-local request token."""

        if self._closed or item.kind != "remote":
            return 0
        self.cancel_active()
        token = self._next_token
        self._next_token += 1
        pending = _PendingResolution(
            token=token,
            generation=int(generation),
            identity=item.stable_identity,
            source_id=item.source_id,
        )
        self._pending[token] = pending
        self._active_token = token

        capability = self._playback_capability(item.source_id)
        if capability is False:
            self._schedule_failure(
                token,
                "SourceUnavailable",
                "当前在线来源不支持播放。",
            )
            return token

        self.resolve_started.emit(token, pending.generation, pending.identity)
        self.status_changed.emit("resolving", "正在解析在线播放地址…")
        try:
            client_request_id = self.client.resolve_playback(
                item.source_id,
                item.media_item.to_legacy_online(),
            )
        except Exception as error:  # the controller receives a safe user message
            self._schedule_failure(token, "ResolveFailed", str(error))
            return token
        pending.client_request_id = int(client_request_id or 0)
        if pending.client_request_id:
            self._client_to_token[pending.client_request_id] = token
            timeout_timer = QTimer(self)
            timeout_timer.setSingleShot(True)
            timeout_timer.timeout.connect(
                lambda current_token=token: self._on_timeout(current_token)
            )
            pending.timeout_timer = timeout_timer
            timeout_timer.start(self.RESOLVE_TIMEOUT_MS)
        else:
            self._schedule_failure(token, "ResolveFailed", "在线来源未接受播放请求。")
        return token

    def cancel_active(self, *, notify: bool = False) -> None:
        token = self._active_token
        if not token:
            return
        pending = self._pending.pop(token, None)
        self._active_token = 0
        if pending is None:
            return
        self._stop_timeout(pending)
        if pending.client_request_id:
            self._client_to_token.pop(pending.client_request_id, None)
            self.client.cancel_request(pending.client_request_id)
        if notify:
            self.resolve_failed.emit(
                pending.token,
                pending.generation,
                pending.identity,
                "Cancelled",
                "在线播放请求已取消。",
            )

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel_active()
        self._pending.clear()
        self._client_to_token.clear()

    def _playback_capability(self, source_id: str) -> bool | None:
        provider = self._source_catalog_provider
        if provider is None:
            return None
        try:
            catalog = [item for item in provider() if isinstance(item, dict)]
        except Exception:
            return False
        loaded_provider = self._source_catalog_loaded
        loaded = bool(loaded_provider()) if loaded_provider is not None else bool(catalog)
        if not loaded:
            return None
        target = next(
            (item for item in catalog if str(item.get("id") or "") == source_id),
            None,
        )
        if target is None or target.get("selectable") is False:
            return False
        capabilities = target.get("capabilities")
        return bool(isinstance(capabilities, dict) and capabilities.get("playback") is True)

    def _schedule_failure(self, token: int, code: str, message: str) -> None:
        QTimer.singleShot(
            0,
            lambda: self._emit_failure(token, code, message),
        )

    def _emit_failure(self, token: int, code: str, message: str) -> None:
        pending = self._pending.pop(token, None)
        if pending is None or self._closed:
            return
        self._stop_timeout(pending)
        if pending.client_request_id:
            self._client_to_token.pop(pending.client_request_id, None)
        if self._active_token == token:
            self._active_token = 0
        self.status_changed.emit("failed", str(message or "在线播放解析失败。"))
        self.resolve_failed.emit(
            pending.token,
            pending.generation,
            pending.identity,
            str(code or "ResolveFailed"),
            str(message or "在线播放解析失败。"),
        )

    def _on_playback_resolved(self, request_id: int, source_id: str, resolution: dict) -> None:
        token = self._client_to_token.pop(int(request_id), 0)
        if not token or self._closed:
            return
        pending = self._pending.pop(token, None)
        if pending is None:
            return
        self._stop_timeout(pending)
        if self._active_token == token:
            self._active_token = 0
        if str(source_id or "") != pending.source_id:
            self.resolve_failed.emit(
                pending.token,
                pending.generation,
                pending.identity,
                "ResolveFailed",
                "在线播放地址与当前来源不匹配。",
            )
            return
        self.status_changed.emit("resolved", "在线播放地址已准备。")
        self.resolve_succeeded.emit(
            pending.token,
            pending.generation,
            pending.identity,
            dict(resolution) if isinstance(resolution, dict) else {},
        )

    def _on_request_failed(self, request_id: int, action: str, message: str) -> None:
        if str(action or "") != "resolvePlayback":
            return
        token = self._client_to_token.get(int(request_id), 0)
        if not token:
            return
        code = "NetworkError" if "网络" in str(message or "") else "ResolveFailed"
        self._emit_failure(token, code, message)

    def _on_timeout(self, token: int) -> None:
        pending = self._pending.get(int(token))
        if pending is None or self._closed:
            return
        if pending.client_request_id:
            self.client.cancel_request(pending.client_request_id)
        self._emit_failure(
            int(token),
            "NetworkError",
            "在线播放地址解析超时，请检查网络或来源状态。",
        )

    @staticmethod
    def _stop_timeout(pending: _PendingResolution) -> None:
        timer = pending.timeout_timer
        if timer is None:
            return
        timer.stop()
        timer.deleteLater()
        pending.timeout_timer = None
