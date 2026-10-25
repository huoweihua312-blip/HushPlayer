"""替换来源：结果解析与回调。

覆盖真实插件返回形态（data 可能是 dict 也可能是 list），以及回调异常不能
让请求悬挂（之前出现过 AttributeError 之后 _pending 永不清空、对话框只能等超时）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hushplayer.model.track import Track
from hushplayer.online.models import SourceInfo
from hushplayer.services.source_replace import SourceReplaceSearch


class _Client(QObject):
    failure = Signal(str)
    sources_changed = Signal(list)

    running = True

    def __init__(self, payload) -> None:
        super().__init__()
        self.payload = payload
        self.calls: list[str] = []

    def ensure_started(self) -> None:  # pragma: no cover - not needed here
        pass

    def search(self, source_id, keyword, page, callback, *, timeout=0, kind="music"):
        self.calls.append(source_id)
        callback({"ok": True, "data": self.payload})
        return 1


def _source(ident: str, label: str) -> SourceInfo:
    return SourceInfo(
        id=ident,
        name=label,
        platform=label,
        enabled=True,
        user_installed=True,
        content_policy="user_owned",
        capabilities={
            "search": True,
            "metadata": True,
            "lyrics": True,
            "playback": True,
            "download": False,
            "downloadViaPlayback": False,
        },
    )


def _track() -> Track:
    return Track(
        id="online:kw:demo",
        kind="online",
        title="晴天",
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
        source_id="kw",
        source_name="酷我",
        remote_id="demo",
    )


def _run(payload) -> tuple[list, list, list[str]]:
    client = _Client(payload)
    sources = [_source("kw", "酷我"), _source("wy", "网易音乐")]
    captured: dict = {}

    def done(candidates, errors) -> None:
        captured["candidates"] = candidates
        captured["errors"] = errors

    search = SourceReplaceSearch(client, _track(), sources, done, timeout_ms=5_000)
    search.start()
    return captured.get("candidates", []), captured.get("errors", []), client.calls


def test_search_tolerates_list_payload(qapp) -> None:
    payload = [
        {
            "id": "1",
            "title": "晴天",
            "artist": "周杰伦",
            "album": "叶惠美",
            "duration": 269000,
        }
    ]
    candidates, errors, calls = _run(payload)
    assert "kw" not in calls  # current source is skipped
    assert calls == ["wy"]
    assert errors == []
    assert len(candidates) == 1
    assert candidates[0].title == "晴天"
    assert candidates[0].score > 100


def test_search_accepts_nested_data_payload(qapp) -> None:
    payload = {
        "data": [
            {
                "id": "2",
                "title": "晴天 (Live)",
                "artist": "周杰伦",
                "album": "演唱会",
                "duration": 240000,
            }
        ]
    }
    candidates, errors, _ = _run(payload)
    assert errors == []
    assert len(candidates) == 1
    assert candidates[0].remote_id == "2"


def test_broken_item_does_not_hang(qapp) -> None:
    payload = {"data": [None, 42, {"title": ""}]}
    candidates, errors, _ = _run(payload)
    assert candidates == []
    assert errors == []
