from __future__ import annotations

import time
import unicodedata
from collections import OrderedDict

from PySide6.QtCore import QObject, QTimer, Signal

from app.services.online_source_client import OnlineSourceClient


class UnifiedSearchService(QObject):
    """Coordinate debounced concurrent searches across registered custom sources."""

    resultsChanged = Signal(int, str, list, dict)
    statusChanged = Signal(str)
    searchStarted = Signal(int, str, int)
    sourceFailed = Signal(int, str, str, str)

    MIN_KEYWORD_LENGTH = 2
    SOURCE_LIST_TIMEOUT_MS = 8000
    SOURCE_SEARCH_TIMEOUT_MS = 9000

    def __init__(
        self,
        client: OnlineSourceClient,
        parent: QObject | None = None,
        debounce_ms: int = 500,
        cache_ttl_seconds: int = 180,
    ) -> None:
        super().__init__(parent)
        self.client = client
        try:
            normalized_debounce = int(debounce_ms)
        except (TypeError, ValueError):
            normalized_debounce = 500
        try:
            normalized_ttl = int(cache_ttl_seconds)
        except (TypeError, ValueError):
            normalized_ttl = 180
        self.debounce_ms = max(300, min(1500, normalized_debounce))
        self.cache_ttl_seconds = max(30, min(600, normalized_ttl))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.debounce_ms)
        self._timer.timeout.connect(self.start_pending_search)
        self._generation = 0
        self._keyword = ""
        self._local_only = False
        self._source_list_request = 0
        self._pending_requests: dict[int, tuple[int, str, str]] = {}
        self._source_order: list[str] = []
        self._source_meta: dict[str, dict] = {}
        self._source_results: dict[str, list[dict]] = {}
        self._source_errors: OrderedDict[str, str] = OrderedDict()
        self._cache: dict[tuple[str, str], tuple[float, str, list[dict]]] = {}
        self.client.responseReceived.connect(self._on_response_received)
        self.client.searchFinished.connect(self._on_search_finished)
        self.client.requestFailed.connect(self._on_request_failed)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def keyword(self) -> str:
        return self._keyword

    def schedule_search(self, keyword: str, local_only: bool = False) -> int:
        self._generation += 1
        self._keyword = str(keyword or "").strip()
        self._local_only = bool(local_only)
        self._timer.stop()
        self._cancel_active_requests()
        self._source_order = []
        self._source_meta = {}
        self._source_results = {}
        self._source_errors = OrderedDict()

        if not self._keyword:
            self.statusChanged.emit("")
            self._emit_results(final=True)
        elif self._local_only:
            self.statusChanged.emit("仅搜索本地音乐。")
            self._emit_results(final=True)
        elif len(self._keyword) < self.MIN_KEYWORD_LENGTH:
            self.statusChanged.emit("输入至少 2 个字符后才会搜索在线来源。")
            self._emit_results(final=True)
        else:
            self.statusChanged.emit("等待输入完成后搜索在线来源…")
            self._emit_results(final=False)
            self._timer.start()
        return self._generation

    def start_pending_search(self) -> None:
        self._timer.stop()
        if (
            self._local_only
            or len(self._keyword) < self.MIN_KEYWORD_LENGTH
            or not self._keyword
        ):
            return
        self._source_list_request = self.client.list_sources(
            timeout_ms=self.SOURCE_LIST_TIMEOUT_MS
        )
        self.statusChanged.emit("正在读取已启用的自定义来源…")

    def invalidate_source(self, source_id: str = "") -> None:
        target = str(source_id or "").strip()
        if target:
            for key in [key for key in self._cache if key[0] == target]:
                self._cache.pop(key, None)
            self._source_results.pop(target, None)
            self._source_errors.pop(target, None)
            self._source_meta.pop(target, None)
            self._source_order = [item for item in self._source_order if item != target]
            for request_id, (_generation, pending_id, _name) in list(
                self._pending_requests.items()
            ):
                if pending_id == target:
                    self.client.cancel_request(request_id)
                    self._pending_requests.pop(request_id, None)
        else:
            self._cache.clear()
            self._cancel_active_requests()
            self._source_order = []
            self._source_meta = {}
            self._source_results = {}
            self._source_errors = OrderedDict()
        if self._keyword:
            self.statusChanged.emit("来源状态已变化，相关在线搜索缓存已清除。")
            self._emit_results(final=not self._pending_requests)

    def clear_cache(self) -> None:
        self._cache.clear()

    def shutdown(self) -> None:
        self._timer.stop()
        self._cancel_active_requests()

    def _cancel_active_requests(self) -> None:
        if self._source_list_request:
            self.client.cancel_request(self._source_list_request)
            self._source_list_request = 0
        for request_id in list(self._pending_requests):
            self.client.cancel_request(request_id)
        self._pending_requests.clear()

    def _on_response_received(self, request_id: int, action: str, data) -> None:
        if request_id != self._source_list_request or action != "listSources":
            return
        self._source_list_request = 0
        if not isinstance(data, list):
            self._source_errors["__registry__"] = "来源列表格式无效"
            self.statusChanged.emit("读取自定义来源失败。")
            self._emit_results(final=True)
            return

        sources: list[dict] = []
        for source in data:
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("id") or "").strip()
            if (
                not source_id
                or not source.get("userInstalled")
                or not source.get("sourceUrl")
                or not source.get("enabled")
            ):
                continue
            source_name = str(source.get("name") or source_id)
            capabilities = source.get("capabilities")
            capabilities = capabilities if isinstance(capabilities, dict) else {}
            if source.get("scanError"):
                self._source_errors[source_id] = f"{source_name}：能力检测失败"
                self.sourceFailed.emit(
                    self._generation,
                    source_id,
                    source_name,
                    "能力检测失败",
                )
                continue
            if not source.get("fileExists", True):
                self._source_errors[source_id] = f"{source_name}：来源文件不可用"
                self.sourceFailed.emit(
                    self._generation,
                    source_id,
                    source_name,
                    "来源文件不可用",
                )
                continue
            if capabilities.get("search") is not True:
                continue
            sources.append(dict(source))

        self._source_order = [str(source.get("id") or "") for source in sources]
        self._source_meta = {
            str(source.get("id") or ""): dict(source) for source in sources
        }
        if not sources:
            if self._source_errors:
                self.statusChanged.emit("没有可搜索的在线来源；部分来源当前不可用。")
            else:
                self.statusChanged.emit("没有已启用且支持搜索的自定义来源。")
            self._emit_results(final=True)
            return

        self.searchStarted.emit(self._generation, self._keyword, len(sources))
        self.statusChanged.emit(f"正在搜索 {len(sources)} 个在线来源…")
        normalized_keyword = self._normalize_text(self._keyword)
        now = time.monotonic()
        for source in sources:
            source_id = str(source.get("id") or "")
            source_name = str(source.get("name") or source_id)
            fingerprint = self._source_fingerprint(source)
            cache_key = (source_id, normalized_keyword)
            cached = self._cache.get(cache_key)
            if cached and cached[0] > now and cached[1] == fingerprint:
                self._source_results[source_id] = [dict(item) for item in cached[2]]
                continue
            request_id = self.client.search(
                source_id,
                self._keyword,
                timeout_ms=self.SOURCE_SEARCH_TIMEOUT_MS,
            )
            self._pending_requests[request_id] = (
                self._generation,
                source_id,
                source_name,
            )

        if not self._pending_requests:
            self.statusChanged.emit("在线搜索已从缓存完成。")
            self._emit_results(final=True)
        else:
            self._emit_results(final=False)

    def _on_search_finished(
        self,
        request_id: int,
        source_id: str,
        results: list,
    ) -> None:
        pending = self._pending_requests.pop(request_id, None)
        if pending is None:
            return
        generation, expected_source_id, _source_name = pending
        if generation != self._generation or source_id != expected_source_id:
            return
        source = self._source_meta.get(source_id, {})
        normalized = self._normalize_source_results(source, results)
        self._source_results[source_id] = normalized
        cache_key = (source_id, self._normalize_text(self._keyword))
        self._cache[cache_key] = (
            time.monotonic() + self.cache_ttl_seconds,
            self._source_fingerprint(source),
            [dict(item) for item in normalized],
        )
        self._finish_or_update()

    def _on_request_failed(self, request_id: int, action: str, message: str) -> None:
        if request_id == self._source_list_request and action == "listSources":
            self._source_list_request = 0
            self._source_errors["__registry__"] = str(message or "读取来源列表失败")
            self.statusChanged.emit("读取自定义来源失败。")
            self._emit_results(final=True)
            return
        pending = self._pending_requests.pop(request_id, None)
        if pending is None or action != "search":
            return
        generation, source_id, source_name = pending
        if generation != self._generation:
            return
        safe_message = str(message or "搜索失败")
        self._source_errors[source_id] = f"{source_name}：{safe_message}"
        self.sourceFailed.emit(generation, source_id, source_name, safe_message)
        self._finish_or_update()

    def _finish_or_update(self) -> None:
        final = not self._pending_requests
        if final:
            result_count = len(self._combined_results())
            failed_count = len(self._source_errors)
            if result_count <= 0 and failed_count:
                self.statusChanged.emit(f"在线搜索结束，{failed_count} 个来源失败，没有找到结果。")
            elif result_count <= 0:
                self.statusChanged.emit("在线搜索完成，没有找到结果。")
            elif failed_count:
                self.statusChanged.emit(
                    f"在线搜索完成，找到 {result_count} 条结果；{failed_count} 个来源失败。"
                )
            else:
                self.statusChanged.emit(f"在线搜索完成，找到 {result_count} 条结果。")
        self._emit_results(final=final)

    def _emit_results(self, final: bool) -> None:
        results = self._combined_results()
        summary = {
            "final": bool(final),
            "sourceCount": len(self._source_order),
            "pendingCount": len(self._pending_requests),
            "resultCount": len(results),
            "errors": dict(self._source_errors),
            "localOnly": self._local_only,
        }
        self.resultsChanged.emit(
            self._generation,
            self._keyword,
            results,
            summary,
        )

    def _combined_results(self) -> list[dict]:
        combined: list[dict] = []
        cross_source_keys: set[tuple] = set()
        for source_id in self._source_order:
            for result in self._source_results.get(source_id, []):
                key = self._cross_source_key(result)
                if key and key in cross_source_keys:
                    continue
                if key:
                    cross_source_keys.add(key)
                combined.append(dict(result))
        return combined

    def _normalize_source_results(self, source: dict, results: list) -> list[dict]:
        source_id = str(source.get("id") or "")
        source_name = str(source.get("name") or source_id or "未知来源")
        capabilities = source.get("capabilities")
        capabilities = dict(capabilities) if isinstance(capabilities, dict) else {}
        normalized: list[dict] = []
        seen: set[tuple] = set()
        for raw_result in results if isinstance(results, list) else []:
            if not isinstance(raw_result, dict):
                continue
            result = dict(raw_result)
            result["resultKind"] = "remote"
            result["sourceId"] = source_id
            result["sourceName"] = source_name
            result["capabilities"] = dict(capabilities)
            result["availability"] = "available"
            key = self._within_source_key(result)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(result)
        return normalized

    @classmethod
    def _within_source_key(cls, result: dict) -> tuple:
        remote_id = str(result.get("id") or result.get("songmid") or "").strip()
        if remote_id:
            return ("id", remote_id)
        return (
            "metadata",
            cls._normalize_text(result.get("title")),
            cls._normalize_text(result.get("artist")),
            cls._normalize_text(result.get("album")),
            cls._safe_duration(result.get("duration")),
        )

    @classmethod
    def _cross_source_key(cls, result: dict) -> tuple | None:
        title = cls._normalize_text(result.get("title"))
        artist = cls._normalize_text(result.get("artist"))
        album = cls._normalize_text(result.get("album"))
        duration = cls._safe_duration(result.get("duration"))
        if not title or not artist or not album or duration <= 0:
            return None
        return (title, artist, album, int(round(duration / 2.0)))

    @staticmethod
    def _source_fingerprint(source: dict) -> str:
        capabilities = source.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        capability_key = ",".join(
            f"{key}:{bool(capabilities.get(key))}"
            for key in ("search", "playback", "download")
        )
        return "|".join(
            [
                str(source.get("sha256") or ""),
                str(source.get("version") or ""),
                str(bool(source.get("enabled"))),
                capability_key,
            ]
        )

    @staticmethod
    def _safe_duration(value) -> int:
        try:
            return max(0, int(float(value or 0)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_text(value) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return " ".join(text.split())
