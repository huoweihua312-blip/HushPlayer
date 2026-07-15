from __future__ import annotations

import time
import unicodedata
from collections import OrderedDict

from PySide6.QtCore import QObject, QTimer, Signal

from app.services.online_source_client import OnlineSourceClient


class UnifiedSearchService(QObject):
    """Coordinate debounced concurrent searches across registered custom sources."""

    resultsChanged = Signal(int, str, list, dict)
    sourceResultsChanged = Signal(int, str, str, list, dict, dict)
    statusChanged = Signal(str)
    searchStarted = Signal(int, str, int)
    sourceFailed = Signal(int, str, str, str)
    sourceCatalogChanged = Signal(list, list)

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
        self._source_list_for_search = False
        self._source_list_generation = 0
        self._pending_requests: dict[int, tuple[int, str, str]] = {}
        self._source_catalog: list[dict] = []
        self._catalog_loaded = False
        self._selection_initialized = False
        self._select_all_requested = False
        self._selected_source_ids: list[str] = []
        self._source_order: list[str] = []
        self._source_meta: dict[str, dict] = {}
        self._source_results: dict[str, list[dict]] = {}
        self._combined_results_cache: list[dict] = []
        self._source_result_sizes: dict[str, int] = {}
        self._source_errors: OrderedDict[str, str] = OrderedDict()
        self._source_states: OrderedDict[str, dict] = OrderedDict()
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

    @property
    def source_catalog(self) -> list[dict]:
        return [dict(source) for source in self._source_catalog]

    @property
    def source_catalog_loaded(self) -> bool:
        return self._catalog_loaded

    @property
    def selected_source_ids(self) -> list[str]:
        return list(self._selected_source_ids)

    def set_selected_source_ids(
        self,
        source_ids,
        *,
        restart: bool = True,
    ) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for source_id in source_ids if isinstance(source_ids, (list, tuple, set)) else []:
            value = str(source_id or "").strip()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)

        if self._catalog_loaded:
            selectable_ids = self._selectable_source_ids()
            selectable_set = set(selectable_ids)
            normalized = [source_id for source_id in normalized if source_id in selectable_set]
            self._select_all_requested = bool(selectable_ids) and set(normalized) == selectable_set
        else:
            self._select_all_requested = False

        changed = (
            not self._selection_initialized
            or normalized != self._selected_source_ids
        )
        self._selection_initialized = True
        self._selected_source_ids = normalized
        if changed and restart and self._keyword and not self._local_only:
            self.schedule_search(self._keyword, local_only=False)
        return list(self._selected_source_ids)

    def ensure_source_catalog(self) -> int:
        if self._catalog_loaded or self._source_list_request:
            return self._source_list_request
        return self._request_source_catalog(for_search=False)

    def refresh_source_catalog(self) -> int:
        self._catalog_loaded = False
        if self._source_list_request:
            self.client.cancel_request(self._source_list_request)
            self._source_list_request = 0
        return self._request_source_catalog(for_search=False)

    def schedule_search(self, keyword: str, local_only: bool = False) -> int:
        self._generation += 1
        self._keyword = str(keyword or "").strip()
        self._local_only = bool(local_only)
        self._timer.stop()
        self._cancel_active_requests()
        self._source_order = []
        self._source_meta = {}
        self._source_results = {}
        self._combined_results_cache = []
        self._source_result_sizes = {}
        self._source_errors = OrderedDict()
        self._source_states = OrderedDict()

        if not self._keyword:
            self.statusChanged.emit("")
            self._emit_results(final=True)
        elif self._local_only:
            self.statusChanged.emit("仅搜索本地音乐。")
            self._emit_results(final=True)
        elif len(self._keyword) < self.MIN_KEYWORD_LENGTH:
            self.statusChanged.emit("输入至少 2 个字符后才会搜索在线来源。")
            self._emit_results(final=True)
        elif self._catalog_loaded and not self._selectable_source_ids():
            self.statusChanged.emit("没有已启用且支持搜索的自定义来源。")
            self._emit_results(final=True)
        elif self._catalog_loaded and not self._selected_source_ids:
            self.statusChanged.emit("请至少选择一个搜索来源。")
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
        self._request_source_catalog(for_search=True)

    def _request_source_catalog(self, *, for_search: bool) -> int:
        if self._source_list_request:
            self.client.cancel_request(self._source_list_request)
        self._source_list_for_search = bool(for_search)
        self._source_list_generation = self._generation
        self._source_list_request = self.client.list_sources(
            timeout_ms=self.SOURCE_LIST_TIMEOUT_MS
        )
        self.statusChanged.emit("正在读取已启用的自定义来源…")
        return self._source_list_request

    def invalidate_source(self, source_id: str = "") -> None:
        target = str(source_id or "").strip()
        self._catalog_loaded = False
        self._source_catalog = []
        if target:
            for key in [key for key in self._cache if key[0] == target]:
                self._cache.pop(key, None)
            self._source_results.pop(target, None)
            self._replace_combined_source_results(target, [])
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
            self._combined_results_cache = []
            self._source_result_sizes = {}
            self._source_errors = OrderedDict()
            self._source_states = OrderedDict()
        self.sourceCatalogChanged.emit([], list(self._selected_source_ids))
        if self._keyword and not self._local_only:
            self.schedule_search(self._keyword, local_only=False)
        else:
            self.statusChanged.emit("来源状态已变化，正在刷新搜索来源…")
            self.refresh_source_catalog()

    def clear_cache(self) -> None:
        self._cache.clear()

    def shutdown(self) -> None:
        self._timer.stop()
        self._cancel_active_requests()

    def _cancel_active_requests(self) -> None:
        if self._source_list_request:
            self.client.cancel_request(self._source_list_request)
            self._source_list_request = 0
        self._source_list_for_search = False
        self._source_list_generation = 0
        for request_id in list(self._pending_requests):
            self.client.cancel_request(request_id)
        self._pending_requests.clear()

    def _on_response_received(self, request_id: int, action: str, data) -> None:
        if request_id != self._source_list_request or action != "listSources":
            return
        for_search = self._source_list_for_search
        request_generation = self._source_list_generation
        self._source_list_request = 0
        self._source_list_for_search = False
        self._source_list_generation = 0
        if not isinstance(data, list):
            self._catalog_loaded = False
            self._source_catalog = []
            self.sourceCatalogChanged.emit([], list(self._selected_source_ids))
            if for_search:
                self._source_errors["__registry__"] = "来源列表格式无效"
            self.statusChanged.emit("读取自定义来源失败。")
            if for_search:
                self._emit_results(final=True)
            return

        catalog: list[dict] = []
        searchable_sources: list[dict] = []
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
            unavailable_reason = ""
            if source.get("scanError"):
                unavailable_reason = "能力检测失败"
            elif not source.get("fileExists", True):
                unavailable_reason = "来源文件不可用"
            elif capabilities.get("search") is not True:
                unavailable_reason = "不支持搜索"
            selectable = not unavailable_reason
            catalog.append(
                {
                    "id": source_id,
                    "name": source_name,
                    "selectable": selectable,
                    "reason": unavailable_reason,
                }
            )
            if selectable:
                searchable_sources.append(dict(source))

        self._source_catalog = catalog
        self._catalog_loaded = True
        selectable_ids = [str(source.get("id") or "") for source in searchable_sources]
        selectable_set = set(selectable_ids)
        if not self._selection_initialized or self._select_all_requested:
            self._selected_source_ids = list(selectable_ids)
            self._selection_initialized = True
            self._select_all_requested = bool(selectable_ids)
        else:
            self._selected_source_ids = [
                source_id
                for source_id in self._selected_source_ids
                if source_id in selectable_set
            ]
        self.sourceCatalogChanged.emit(
            self.source_catalog,
            list(self._selected_source_ids),
        )

        if not for_search:
            if selectable_ids:
                self.statusChanged.emit(f"已加载 {len(selectable_ids)} 个可搜索来源。")
            elif catalog:
                self.statusChanged.emit("当前自定义来源均不可用于搜索。")
            else:
                self.statusChanged.emit("没有已启用的自定义来源。")
            return
        if request_generation != self._generation:
            return

        selected_set = set(self._selected_source_ids)
        sources = [
            source
            for source in searchable_sources
            if str(source.get("id") or "") in selected_set
        ]
        self._source_order = [str(source.get("id") or "") for source in sources]
        self._source_meta = {
            str(source.get("id") or ""): dict(source) for source in sources
        }
        if not sources:
            if selectable_ids:
                self.statusChanged.emit("请至少选择一个搜索来源。")
            elif catalog:
                self.statusChanged.emit("没有可搜索的在线来源；部分来源当前不可用。")
            else:
                self.statusChanged.emit("没有已启用且支持搜索的自定义来源。")
            self._emit_results(final=True)
            return

        self.searchStarted.emit(self._generation, self._keyword, len(sources))
        self.statusChanged.emit(f"正在搜索 {len(sources)} 个在线来源…")
        normalized_keyword = self._normalize_text(self._keyword)
        now = time.monotonic()
        cached_source_ids: list[str] = []
        for source in sources:
            source_id = str(source.get("id") or "")
            source_name = str(source.get("name") or source_id)
            self._source_states[source_id] = self._source_state(
                source_id,
                source_name,
                "searching",
            )
            fingerprint = self._source_fingerprint(source)
            cache_key = (source_id, normalized_keyword)
            cached = self._cache.get(cache_key)
            if cached and cached[0] > now and cached[1] == fingerprint:
                self._source_results[source_id] = [dict(item) for item in cached[2]]
                self._replace_combined_source_results(
                    source_id,
                    self._source_results[source_id],
                )
                self._source_states[source_id] = self._source_state(
                    source_id,
                    source_name,
                    "success" if self._source_results[source_id] else "empty",
                    result_count=len(self._source_results[source_id]),
                )
                cached_source_ids.append(source_id)
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
        for source_id in cached_source_ids:
            self._emit_source_results(source_id, final=not self._pending_requests)

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
        self._replace_combined_source_results(source_id, normalized)
        source_name = str(source.get("name") or source_id)
        self._source_states[source_id] = self._source_state(
            source_id,
            source_name,
            "success" if normalized else "empty",
            result_count=len(normalized),
        )
        cache_key = (source_id, self._normalize_text(self._keyword))
        self._cache[cache_key] = (
            time.monotonic() + self.cache_ttl_seconds,
            self._source_fingerprint(source),
            [dict(item) for item in normalized],
        )
        self._finish_or_update(source_id)

    def _on_request_failed(self, request_id: int, action: str, message: str) -> None:
        if request_id == self._source_list_request and action == "listSources":
            for_search = self._source_list_for_search
            self._source_list_request = 0
            self._source_list_for_search = False
            self._source_list_generation = 0
            self._catalog_loaded = False
            self._source_catalog = []
            self.sourceCatalogChanged.emit([], list(self._selected_source_ids))
            if for_search:
                self._source_errors["__registry__"] = str(message or "读取来源列表失败")
            self.statusChanged.emit("读取自定义来源失败。")
            if for_search:
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
        self._source_states[source_id] = self._source_state(
            source_id,
            source_name,
            self._failure_status(safe_message),
            message=safe_message,
        )
        self._source_results[source_id] = []
        self._replace_combined_source_results(source_id, [])
        self.sourceFailed.emit(generation, source_id, source_name, safe_message)
        self._finish_or_update(source_id)

    def _finish_or_update(self, source_id: str) -> None:
        final = not self._pending_requests
        if final:
            result_count = len(self._combined_results_cache)
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
        else:
            completed_count = len(self._source_order) - len(self._pending_requests)
            self.statusChanged.emit(
                f"已完成 {completed_count}/{len(self._source_order)} 个来源，"
                f"其余来源继续搜索中…"
            )
        self._emit_results(final=final)
        self._emit_source_results(source_id, final=final)

    def _emit_results(self, final: bool) -> None:
        summary = self._build_summary(final)
        self.resultsChanged.emit(
            self._generation,
            self._keyword,
            list(self._combined_results_cache),
            summary,
        )

    def _emit_source_results(self, source_id: str, *, final: bool) -> None:
        state = self._source_states.get(source_id)
        if not isinstance(state, dict):
            return
        self.sourceResultsChanged.emit(
            self._generation,
            self._keyword,
            source_id,
            self._source_results.get(source_id, []),
            dict(state),
            self._build_summary(final),
        )

    def _build_summary(self, final: bool) -> dict:
        summary = {
            "final": bool(final),
            "sourceCount": len(self._source_order),
            "pendingCount": len(self._pending_requests),
            "resultCount": len(self._combined_results_cache),
            "errors": dict(self._source_errors),
            "localOnly": self._local_only,
            "sources": [
                dict(self._source_states[source_id])
                for source_id in self._source_order
                if source_id in self._source_states
            ],
            "selectedSourceIds": list(self._selected_source_ids),
        }
        return summary

    def _combined_results(self) -> list[dict]:
        return list(self._combined_results_cache)

    def _replace_combined_source_results(
        self,
        source_id: str,
        results: list[dict],
    ) -> None:
        if source_id not in self._source_order:
            return
        source_index = self._source_order.index(source_id)
        start = sum(
            self._source_result_sizes.get(item, 0)
            for item in self._source_order[:source_index]
        )
        previous_size = self._source_result_sizes.get(source_id, 0)
        self._combined_results_cache[start:start + previous_size] = results
        self._source_result_sizes[source_id] = len(results)

    @staticmethod
    def _source_state(
        source_id: str,
        source_name: str,
        status: str,
        *,
        result_count: int = 0,
        message: str = "",
    ) -> dict:
        return {
            "sourceId": str(source_id or ""),
            "sourceName": str(source_name or source_id or "未知来源"),
            "status": str(status or "searching"),
            "resultCount": max(0, int(result_count or 0)),
            "message": str(message or ""),
        }

    @staticmethod
    def _failure_status(message: str) -> str:
        normalized = str(message or "").casefold()
        if "超时" in normalized or "timeout" in normalized:
            return "timeout"
        if any(
            marker in normalized
            for marker in ("不可用", "未加载", "不存在", "disabled", "unavailable")
        ):
            return "unavailable"
        return "failed"

    def _selectable_source_ids(self) -> list[str]:
        return [
            str(source.get("id") or "")
            for source in self._source_catalog
            if source.get("selectable") and str(source.get("id") or "")
        ]

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
