from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.services.unified_search_service import UnifiedSearchService
from app.ui.unified_search_panel import UnifiedSearchResultsPanel


class FakeOnlineSourceClient(QObject):
    responseReceived = Signal(int, str, object)
    searchFinished = Signal(int, str, list)
    requestFailed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.next_request_id = 1
        self.list_requests: list[int] = []
        self.search_requests: dict[int, tuple[str, str]] = {}
        self.cancelled: list[int] = []

    def _next_id(self) -> int:
        request_id = self.next_request_id
        self.next_request_id += 1
        return request_id

    def list_sources(self, timeout_ms: int = 8000) -> int:
        assert timeout_ms == 8000
        request_id = self._next_id()
        self.list_requests.append(request_id)
        return request_id

    def search(
        self,
        source_id: str,
        keyword: str,
        page: int = 1,
        search_type: str = "music",
        timeout_ms: int = 9000,
    ) -> int:
        assert page == 1
        assert search_type == "music"
        assert timeout_ms == 9000
        request_id = self._next_id()
        self.search_requests[request_id] = (source_id, keyword)
        return request_id

    def cancel_request(self, request_id: int) -> bool:
        self.cancelled.append(int(request_id))
        return True

    def answer_sources(self, request_id: int, sources: list[dict]) -> None:
        self.responseReceived.emit(request_id, "listSources", sources)

    def answer_search(self, request_id: int, results: list[dict]) -> None:
        source_id, _keyword = self.search_requests[request_id]
        self.searchFinished.emit(request_id, source_id, results)

    def fail_search(self, request_id: int, message: str) -> None:
        self.requestFailed.emit(request_id, "search", message)


def source_fixture(source_id: str, name: str, enabled: bool = True) -> dict:
    return {
        "id": source_id,
        "name": name,
        "sourceUrl": f"https://example.invalid/{source_id}.js",
        "userInstalled": True,
        "enabled": enabled,
        "fileExists": True,
        "scanError": "",
        "sha256": source_id * 8,
        "capabilities": {"search": True, "playback": True, "download": True},
    }


def stop_debounce_and_start(service: UnifiedSearchService) -> int:
    service.start_pending_search()
    return service._source_list_request


def test_parallel_failure_stale_and_cache() -> None:
    client = FakeOnlineSourceClient()
    service = UnifiedSearchService(client, debounce_ms=500, cache_ttl_seconds=180)
    emissions: list[tuple[int, str, list, dict]] = []
    service.resultsChanged.connect(
        lambda generation, keyword, results, summary:
        emissions.append((generation, keyword, list(results), dict(summary)))
    )

    service.schedule_search("first")
    list_request = stop_debounce_and_start(service)
    client.answer_sources(
        list_request,
        [
            source_fixture("source_a", "Source A"),
            source_fixture("source_disabled", "Disabled", enabled=False),
            source_fixture("source_b", "Source B"),
        ],
    )
    active = dict(client.search_requests)
    assert {source_id for source_id, _keyword in active.values()} == {"source_a", "source_b"}
    assert all(keyword == "first" for _source_id, keyword in active.values())
    request_a = next(key for key, value in active.items() if value[0] == "source_a")
    request_b = next(key for key, value in active.items() if value[0] == "source_b")
    client.answer_search(
        request_a,
        [{"id": "a1", "title": "Song", "artist": "Artist", "album": "Album", "duration": 180}],
    )
    client.fail_search(request_b, "fixture failure")
    final = emissions[-1]
    assert final[1] == "first"
    assert final[3]["final"] is True
    assert [item["id"] for item in final[2]] == ["a1"]
    assert "source_b" in final[3]["errors"]

    old_search_count = len(client.search_requests)
    service.schedule_search("first")
    cached_list_request = stop_debounce_and_start(service)
    client.answer_sources(
        cached_list_request,
        [source_fixture("source_a", "Source A")],
    )
    assert len(client.search_requests) == old_search_count
    assert emissions[-1][3]["final"] is True
    assert emissions[-1][2][0]["id"] == "a1"

    service.schedule_search("old")
    old_list_request = stop_debounce_and_start(service)
    client.answer_sources(old_list_request, [source_fixture("source_a", "Source A")])
    stale_request = max(client.search_requests)
    service.schedule_search("new")
    assert stale_request in client.cancelled
    client.answer_search(
        stale_request,
        [{"id": "stale", "title": "Stale", "artist": "Artist", "album": "Album", "duration": 180}],
    )
    new_list_request = stop_debounce_and_start(service)
    client.answer_sources(new_list_request, [source_fixture("source_a", "Source A")])
    new_request = max(client.search_requests)
    client.answer_search(
        new_request,
        [{"id": "new", "title": "New", "artist": "Artist", "album": "Album", "duration": 181}],
    )
    assert emissions[-1][1] == "new"
    assert [item["id"] for item in emissions[-1][2]] == ["new"]

    list_count = len(client.list_requests)
    service.schedule_search("local", local_only=True)
    assert len(client.list_requests) == list_count
    assert emissions[-1][3]["localOnly"] is True
    service.schedule_search("")
    assert emissions[-1][1] == ""
    assert emissions[-1][2] == []


def test_cross_source_deduplication() -> None:
    client = FakeOnlineSourceClient()
    service = UnifiedSearchService(client)
    emissions = []
    service.resultsChanged.connect(
        lambda _generation, _keyword, results, summary:
        emissions.append((list(results), dict(summary)))
    )
    service.schedule_search("same")
    list_request = stop_debounce_and_start(service)
    client.answer_sources(
        list_request,
        [source_fixture("source_a", "A"), source_fixture("source_b", "B")],
    )
    requests = list(client.search_requests)
    duplicate = {
        "title": "Same Song",
        "artist": "Same Artist",
        "album": "Same Album",
        "duration": 180,
    }
    client.answer_search(requests[0], [{"id": "a", **duplicate}])
    client.answer_search(requests[1], [{"id": "b", **duplicate}])
    assert len(emissions[-1][0]) == 1


def test_result_panel_requires_explicit_play(app: QApplication) -> None:
    panel = UnifiedSearchResultsPanel()
    track = {
        "id": "track-1",
        "sourceId": "source_a",
        "sourceName": "Source A",
        "title": "Fixture",
        "artist": "Artist",
        "album": "Album",
        "duration": 120,
        "availability": "available",
        "capabilities": {"playback": True, "download": True},
    }
    played: list[dict] = []
    panel.playRequested.connect(lambda result: played.append(dict(result)))
    panel.set_results("fixture", [track], {"final": True})
    result_item = panel.result_list.item(1)
    panel.browse_result(result_item)
    assert played == []
    panel.request_playback(result_item)
    assert played and played[0]["id"] == "track-1"


def main() -> int:
    app = QApplication.instance() or QApplication([])
    test_parallel_failure_stale_and_cache()
    test_cross_source_deduplication()
    test_result_panel_requires_explicit_play(app)
    print("unified search smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
