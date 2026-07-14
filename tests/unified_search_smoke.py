from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from app.services.unified_search_service import UnifiedSearchService
from app.ui.search_page import SearchPage, SearchSourceSelector
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
    partial = emissions[-1]
    partial_states = {
        state["sourceId"]: state["status"]
        for state in partial[3]["sources"]
    }
    assert partial[3]["final"] is False
    assert partial_states == {"source_a": "success", "source_b": "searching"}
    assert [item["id"] for item in partial[2]] == ["a1"]
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


def test_selected_sources_and_empty_selection() -> None:
    client = FakeOnlineSourceClient()
    service = UnifiedSearchService(client)
    emissions = []
    catalogs = []
    service.resultsChanged.connect(
        lambda _generation, _keyword, results, summary:
        emissions.append((list(results), dict(summary)))
    )
    service.sourceCatalogChanged.connect(
        lambda sources, selected_ids: catalogs.append((list(sources), list(selected_ids)))
    )
    service.set_selected_source_ids(["source_b"], restart=False)
    service.schedule_search("selected")
    list_request = stop_debounce_and_start(service)
    unavailable = source_fixture("source_unavailable", "Unavailable")
    unavailable["scanError"] = "fixture"
    client.answer_sources(
        list_request,
        [
            source_fixture("source_a", "A"),
            source_fixture("source_b", "B"),
            unavailable,
        ],
    )
    assert catalogs[-1][1] == ["source_b"]
    assert [source["id"] for source in catalogs[-1][0]] == [
        "source_a",
        "source_b",
        "source_unavailable",
    ]
    assert catalogs[-1][0][-1]["selectable"] is False
    assert catalogs[-1][0][-1]["reason"] == "能力检测失败"
    active = dict(client.search_requests)
    assert {source_id for source_id, _keyword in active.values()} == {"source_b"}
    request_b = next(iter(active))
    client.answer_search(request_b, [])
    assert emissions[-1][1]["sources"][0]["status"] == "empty"

    service.schedule_search("timeout")
    timeout_list_request = stop_debounce_and_start(service)
    client.answer_sources(
        timeout_list_request,
        [source_fixture("source_a", "A"), source_fixture("source_b", "B")],
    )
    timeout_request = max(client.search_requests)
    client.fail_search(timeout_request, "请求超时，请检查网络或音源状态。")
    assert emissions[-1][1]["sources"][0]["status"] == "timeout"

    list_count = len(client.list_requests)
    service.set_selected_source_ids([])
    assert len(client.list_requests) == list_count
    assert emissions[-1][1]["final"] is True
    assert emissions[-1][1]["selectedSourceIds"] == []


def test_cross_source_results_remain_separate() -> None:
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
    assert len(emissions[-1][0]) == 2
    assert [item["sourceId"] for item in emissions[-1][0]] == ["source_a", "source_b"]


def test_source_selector_labels_and_unavailable_entries(app: QApplication) -> None:
    selector = SearchSourceSelector()
    emitted: list[list[str]] = []
    selector.selectionChanged.connect(lambda source_ids: emitted.append(list(source_ids)))
    selector.set_sources(
        [
            {"id": "source_a", "name": "A", "selectable": True, "reason": ""},
            {"id": "source_b", "name": "B", "selectable": True, "reason": ""},
            {
                "id": "source_bad",
                "name": "Bad",
                "selectable": False,
                "reason": "来源文件不可用",
            },
        ],
        ["source_a", "source_b"],
    )
    assert selector.text() == "全部来源"
    assert selector._checkboxes["source_bad"].isEnabled() is False
    assert selector._checkboxes["source_bad"].toolTip() == "来源文件不可用"
    selector._checkboxes["source_b"].setChecked(False)
    assert selector.text() == "A"
    assert emitted[-1] == ["source_a"]
    selector.clear_selection()
    assert selector.text() == "未选择来源"
    selector.select_all()
    assert selector.text() == "全部来源"


def test_search_page_restores_and_saves_source_selection(app: QApplication) -> None:
    client = FakeOnlineSourceClient()
    service = UnifiedSearchService(client)
    host = QWidget()
    saved_updates: list[dict] = []
    host.unified_search_service = service
    host.get_user_setting = (
        lambda key, default=None: ["source_b"]
        if key == "online_search_selected_sources"
        else default
    )
    host.save_hush_settings = lambda updates: saved_updates.append(dict(updates))
    page = SearchPage(parent=host)
    page.show_tab("online")
    list_request = service._source_list_request
    assert list_request > 0
    client.answer_sources(
        list_request,
        [source_fixture("source_a", "A"), source_fixture("source_b", "B")],
    )
    assert page.source_selector.text() == "B"
    assert service.selected_source_ids == ["source_b"]
    page.source_selector._checkboxes["source_a"].setChecked(True)
    assert service.selected_source_ids == ["source_a", "source_b"]
    assert saved_updates[-1] == {
        "online_search_selected_sources": ["source_a", "source_b"]
    }
    page.deleteLater()
    host.deleteLater()


def test_result_panel_groups_update_and_collapse(app: QApplication) -> None:
    panel = UnifiedSearchResultsPanel()
    track = {
        "id": "track-a",
        "sourceId": "source_a",
        "sourceName": "Source A",
        "title": "Fixture",
        "artist": "Artist",
        "album": "Album",
        "duration": 120,
        "availability": "available",
        "capabilities": {"playback": True, "download": True},
    }
    panel.set_results(
        "fixture",
        [track],
        {
            "final": False,
            "pendingCount": 1,
            "sources": [
                {
                    "sourceId": "source_a",
                    "sourceName": "Source A",
                    "status": "success",
                    "resultCount": 1,
                    "message": "",
                },
                {
                    "sourceId": "source_b",
                    "sourceName": "Source B",
                    "status": "searching",
                    "resultCount": 0,
                    "message": "",
                },
            ],
        },
    )
    assert panel.result_list.count() == 3
    assert "1 条结果" in panel.result_list.item(0).text()
    assert "搜索中" in panel.result_list.item(2).text()
    panel.toggle_source_group("source_a")
    assert panel.is_source_collapsed("source_a") is True
    assert panel.result_list.count() == 2
    assert panel.result_list.item(0).text().startswith("▶")
    panel.toggle_source_group("source_a")
    assert panel.result_list.count() == 3


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
    assert played and played[0]["track_id"] == "track-1"
    assert played[0]["media_type"] == "online"


def main() -> int:
    app = QApplication.instance() or QApplication([])
    test_parallel_failure_stale_and_cache()
    test_selected_sources_and_empty_selection()
    test_cross_source_results_remain_separate()
    test_source_selector_labels_and_unavailable_entries(app)
    test_search_page_restores_and_saves_source_selection(app)
    test_result_panel_groups_update_and_collapse(app)
    test_result_panel_requires_explicit_play(app)
    print("unified search smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
