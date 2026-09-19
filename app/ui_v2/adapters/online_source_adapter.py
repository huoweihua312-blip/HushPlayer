"""Source-management adapter with a non-destructive playback smoke test."""

from __future__ import annotations

import time
from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.online_adapter import OnlineAdapter


class OnlineSourceAdapter(QObject):
    VERIFY_SONGS = ("夜曲", "晴天", "青花瓷", "Shape of You", "Hotel California")
    sources_changed = Signal(object)
    verify_status_changed = Signal(str)
    verify_running_changed = Signal(bool)

    def __init__(self, online: OnlineAdapter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.online = online
        discovery = online.discovery
        self.importer = getattr(discovery, "source_importer", None)
        online.source_state_changed.connect(self._on_sources_changed)
        if self.importer is not None:
            self.importer.sources_changed.connect(online.refresh_sources)
            client = self.importer.client
            client.searchFinished.connect(self._on_search_finished)
            client.playbackResolved.connect(self._on_playback_resolved)
            client.requestFailed.connect(self._on_request_failed)
        self._verify_queue: list[str] = []
        self._verify_active = ""
        self._verify_song_index = 0
        self._verify_search_request = 0
        self._verify_playback_request = 0
        self._verify_started_at = 0.0
        self._verify_search_count = 0
        self._verify_playable_count = 0
        self._verify_song_hits = 0
        self._verify_overrides: dict[str, dict[str, object]] = {}

    def sources(self):
        return self._apply_verify_overrides(self.online.sources())

    def _on_sources_changed(self, sources) -> None:
        self.sources_changed.emit(self._apply_verify_overrides(sources))

    def _apply_verify_overrides(self, sources):
        return tuple(
            replace(
                source,
                status=str(self._verify_overrides.get(source.id, {}).get("status") or source.status),
                latency_ms=int(self._verify_overrides.get(source.id, {}).get("latency_ms") or source.latency_ms),
                result_count=int(
                    self._verify_overrides.get(source.id, {}).get("result_count")
                    if self._verify_overrides.get(source.id, {}).get("result_count") is not None
                    else source.result_count
                ),
                last_error=str(self._verify_overrides.get(source.id, {}).get("last_error") or source.last_error),
                test_summary=str(self._verify_overrides.get(source.id, {}).get("test_summary") or source.test_summary),
            )
            for source in sources
        )

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if self.importer is not None and self.importer.set_enabled(source_id, enabled):
            self.online.set_source_enabled(source_id, enabled)
            return
        self.online.set_source_enabled(source_id, enabled)

    def remove(self, source_id: str) -> bool:
        return bool(self.importer and self.importer.remove_source(source_id))

    def select_all(self) -> None:
        self.online.set_enabled_sources(source.id for source in self.online.sources())

    def clear_selection(self) -> None:
        self.online.set_enabled_sources(())

    def retry(self) -> bool:
        return self.online.retry()

    def verify_sources(self) -> bool:
        if self.importer is None or self._verify_active:
            return False
        self._verify_queue = [source.id for source in self.sources() if source.enabled]
        if not self._verify_queue:
            self.verify_status_changed.emit("没有已启用的在线来源可验证。")
            return False
        skipped = len(self.sources()) - len(self._verify_queue)
        self.verify_running_changed.emit(True)
        self.verify_status_changed.emit(
            f"开始快速验证：{len(self._verify_queue)} 个来源，"
            f"{len(self.VERIFY_SONGS)} 首内置歌曲"
            + (f"，已跳过 {skipped} 个停用来源。" if skipped else "。")
        )
        self._verify_next_source()
        return True

    def _verify_next_source(self) -> None:
        if not self._verify_queue:
            self.verify_running_changed.emit(False)
            self.verify_status_changed.emit("快速验证完成；来源行已显示搜索与播放解析结果。")
            self.sources_changed.emit(self.sources())
            return
        self._verify_active = self._verify_queue.pop(0)
        self._verify_song_index = 0
        self._verify_started_at = time.monotonic()
        self._verify_search_count = 0
        self._verify_playable_count = 0
        self._verify_song_hits = 0
        self._verify_next_song()

    def _verify_next_song(self) -> None:
        if self._verify_song_index >= len(self.VERIFY_SONGS):
            self._finish_source()
            return
        keyword = self.VERIFY_SONGS[self._verify_song_index]
        self._verify_song_index += 1
        source = next((item for item in self.sources() if item.id == self._verify_active), None)
        name = source.name if source is not None else self._verify_active
        self.verify_status_changed.emit(
            f"正在验证 {name}：第 {self._verify_song_index}/{len(self.VERIFY_SONGS)} 首“{keyword}”，"
            "搜索后解析播放地址…"
        )
        self._verify_search_request = self.importer.client.search(
            self._verify_active, keyword, timeout_ms=30000
        )

    def _on_search_finished(self, request_id: int, source_id: str, results: list) -> None:
        if request_id != self._verify_search_request or str(source_id) != self._verify_active:
            return
        self._verify_search_request = 0
        self._verify_search_count += len(results or [])
        if not results:
            self._verify_next_song()
            return
        self._verify_song_hits += 1
        self._verify_playback_request = self.importer.client.resolve_playback(
            self._verify_active, results[0], timeout_ms=30000
        )

    def _on_playback_resolved(self, request_id: int, source_id: str, resolution: dict) -> None:
        if request_id != self._verify_playback_request or str(source_id) != self._verify_active:
            return
        self._verify_playback_request = 0
        if isinstance(resolution, dict) and str(resolution.get("url") or "").strip():
            self._verify_playable_count += 1
        self._verify_next_song()

    def _on_request_failed(self, request_id: int, action: str, _message: str) -> None:
        if action == "search" and request_id == self._verify_search_request:
            self._verify_search_request = 0
            self._verify_next_song()
        elif action == "resolvePlayback" and request_id == self._verify_playback_request:
            self._verify_playback_request = 0
            self._verify_next_song()

    def _finish_source(self) -> None:
        elapsed_ms = max(0, int((time.monotonic() - self._verify_started_at) * 1000))
        summary = (
            f"可播放 {self._verify_playable_count}/{len(self.VERIFY_SONGS)}"
            f" · 搜索命中 {self._verify_song_hits}/{len(self.VERIFY_SONGS)}"
        )
        status = (
            "success"
            if self._verify_playable_count == len(self.VERIFY_SONGS)
            else "warning"
            if self._verify_playable_count or self._verify_song_hits
            else "failed"
        )
        error = "" if self._verify_playable_count else "没有解析出可播放地址"
        self._verify_overrides[self._verify_active] = {
            "status": status,
            "latency_ms": elapsed_ms,
            "result_count": self._verify_search_count,
            "last_error": error,
            "test_summary": summary,
        }
        self.importer.registry.record_test_result(
            self._verify_active,
            "passed"
            if self._verify_playable_count == len(self.VERIFY_SONGS)
            else "partial"
            if self._verify_playable_count or self._verify_song_hits
            else "failed",
            result_count=self._verify_search_count,
            latency_ms=elapsed_ms,
            playable_count=self._verify_playable_count,
            summary=summary,
            error=error,
        )
        source = next((item for item in self.sources() if item.id == self._verify_active), None)
        name = source.name if source is not None else self._verify_active
        self.sources_changed.emit(self.sources())
        self.verify_status_changed.emit(f"{name}：{summary}，耗时 {elapsed_ms} ms")
        self._verify_active = ""
        self._verify_next_source()
