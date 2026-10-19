"""在线搜索必须边返回边显示，并在超时后收尾。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QTest

from hushplayer.core.settings import Settings
from hushplayer.online.models import SourceInfo
from hushplayer.ui.context import AppContext, ctx, set_context
from hushplayer.ui.pages.search import SearchPage

SOURCE_A = SourceInfo(id="s_a", name="源A", platform="wy", enabled=True,
                      capabilities={"search": True, "playback": True})
SOURCE_B = SourceInfo(id="s_b", name="源B", platform="qq", enabled=True,
                      capabilities={"search": True, "playback": True})

ITEM = {"id": "x1", "title": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269000}


class FakeClient(QObject):
    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, object]] = []
        self.cancelled: list[int] = []
        self._next_id = 1

    def ensure_started(self):
        return True

    def search(self, source_id, keyword, page=1, callback=None, **kwargs):
        request_id = self._next_id
        self._next_id += 1
        self.calls.append((source_id, callback))
        return request_id

    def cancel(self, request_id):
        self.cancelled.append(request_id)


@pytest.fixture
def ui_context(library):
    settings = Settings()
    settings.load()
    context = AppContext(
        library=library,
        player=None,
        lyrics=None,
        cache=None,
        covers=library.covers,
        client=None,
        proxy=None,
        keeper=None,
        settings=settings,
        window=None,
        desktop_lyrics=None,
        immersive=None,
    )
    set_context(context)
    return context


def make_page(qapp, client) -> SearchPage:
    page = SearchPage()
    page._sources = [SOURCE_A, SOURCE_B]  # noqa: SLF001 - test seam
    page.source_filter.set_sources([(s.id, s.label) for s in page._sources])
    ctx().client = client
    return page


def test_results_render_before_every_source_finishes(qapp, ui_context) -> None:
    client = FakeClient()
    page = make_page(qapp, client)
    page._run_online("晴天")  # noqa: SLF001
    assert len(client.calls) == 2

    _source_id, first_callback = client.calls[0]
    first_callback({"ok": True, "data": [ITEM]})
    QTest.qWait(150)

    assert page.online_list.table.model().rowCount() >= 1
    assert not page._finished  # noqa: SLF001
    assert not page.online_list.isHidden()


def test_deadline_finishes_and_marks_timeouts(qapp, ui_context) -> None:
    client = FakeClient()
    page = make_page(qapp, client)
    page._run_online("晴天")  # noqa: SLF001
    page._on_deadline()  # noqa: SLF001

    assert page._finished  # noqa: SLF001
    assert page._timed_out == 2  # noqa: SLF001
    assert "超时" in page.online_status.text()
    assert len(client.cancelled) == 2


def test_repeat_query_is_served_from_cache(qapp, ui_context) -> None:
    client = FakeClient()
    page = make_page(qapp, client)
    page._run_online("晴天")  # noqa: SLF001
    for _source_id, callback in list(client.calls):
        callback({"ok": True, "data": [ITEM]})
    QTest.qWait(150)
    assert page._finished  # noqa: SLF001

    client.calls.clear()
    page._run_online("晴天")  # noqa: SLF001
    assert client.calls == []
    assert page.online_list.table.model().rowCount() >= 1


def test_idle_state_shows_intro_not_results(qapp, ui_context) -> None:
    client = FakeClient()
    page = make_page(qapp, client)

    page._run_online("")  # noqa: SLF001
    assert page.online_stack.currentWidget() is page._online_empty_page  # noqa: SLF001
    assert page.online_toolbar.isHidden()
    assert page.online_status.isHidden()

    page._run_online("晴天")  # noqa: SLF001
    assert page.online_stack.currentWidget() is page.online_list  # noqa: SLF001
    assert not page.online_toolbar.isHidden()
    assert not page.online_status.isHidden()
    assert page.online_list.table.model().rowCount() == 0


def test_local_search_switches_between_intro_and_results(qapp, ui_context) -> None:
    client = FakeClient()
    page = make_page(qapp, client)

    page._run_local("")  # noqa: SLF001
    assert page.local_stack.currentWidget() is page._local_intro  # noqa: SLF001

    page._run_local("不存在的东西")  # noqa: SLF001
    assert page.local_stack.currentWidget() is page._local_intro  # noqa: SLF001
