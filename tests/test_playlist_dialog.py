"""Import wizard smoke tests (headless, offline matching only)."""

from __future__ import annotations

import time

import pytest

from hushplayer.services.playlist_import import PlaylistEntry


class FakeClient:
    sources: list[dict] = []

    def search(self, *args, **kwargs):  # pragma: no cover - offline tests only
        raise AssertionError("offline dialog test must not search online")

    def resolve_playback(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("offline dialog test must not resolve playback")


@pytest.fixture
def inline_context(loaded_library, qapp):
    from hushplayer.ui.context import AppContext, ctx, set_context

    try:
        previous = ctx()
    except Exception:  # noqa: BLE001 - no context yet is fine
        previous = None
    set_context(
        AppContext(
            library=loaded_library,
            player=None,
            lyrics=None,
            cache=None,
            covers=loaded_library.covers,
            client=FakeClient(),
            proxy=None,
            keeper=None,
            settings=None,
        )
    )
    yield loaded_library
    if previous is not None:
        set_context(previous)


def _pump(app, dialog, *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        matcher = getattr(dialog, "_matcher", None)
        if matcher is None:
            time.sleep(0.005)
            continue
        if matcher.total and all(row.status != "pending" for row in matcher.rows):
            app.processEvents()
            return
        time.sleep(0.005)
    raise AssertionError("matching did not settle")


def test_dialog_walks_from_entries_to_preview(inline_context, qapp) -> None:
    from hushplayer.ui.playlist_import_dialog import PlaylistImportDialog

    dialog = PlaylistImportDialog()
    entries = [
        PlaylistEntry(title="夜航信号", artist="Aurora Field"),
        PlaylistEntry(title="没有人唱这首歌", artist="查无此人"),
    ]
    dialog._accept_entries("夜间通勤", entries, "测试")
    assert dialog.stage == 0 and len(dialog._entries) == 2

    dialog._go_next()  # source -> matching
    _pump(qapp, dialog)
    assert dialog.stage == 1

    statuses = [row.status for row in dialog._matcher.rows]
    assert statuses == ["local", "unmatched"]
    counts = dialog._matcher.counts()
    assert counts["local"] == 1 and counts["unmatched"] == 1


def test_dialog_apply_creates_playlist(inline_context, qapp) -> None:
    from hushplayer.ui.playlist_import_dialog import PlaylistImportDialog

    dialog = PlaylistImportDialog()
    dialog._accept_entries(
        "向导导入测试",
        [PlaylistEntry(title="夜航信号", artist="Aurora Field")],
        "",
    )
    dialog._go_next()
    _pump(qapp, dialog)
    dialog._go_next()  # matching -> apply
    qapp.processEvents()

    found = [item for item in inline_context.playlists_all() if item.name == "向导导入测试"]
    assert found, "playlist should be created by the wizard"
    assert found[0].track_count == 1
    assert dialog.stage >= 2

class MidClient:
    """Returns a single mid-score candidate so rows land in review."""

    def __init__(self):
        self.sources: list[dict] = [
            {"id": "fake", "name": "Fake", "platform": "test", "enabled": True,
             "filename": "fake.js", "capabilities": {"search": True, "playback": True}},
        ]

    def search(self, source_id, query, page, callback, **kwargs):
        callback({"ok": True, "data": [{"id": "m1", "title": query.split(" ")[0],
                                        "artist": kwargs.get("artist", "Unknown"),
                                        "album": "", "duration": 200000}]})
        return 1

    def resolve_playback(self, *args, **kwargs):
        raise AssertionError("verification disabled in this test")


def test_adopt_all_and_export_missing(inline_context, qapp) -> None:
    from hushplayer.ui.playlist_import_dialog import PlaylistImportDialog

    dialog = PlaylistImportDialog()
    dialog._accept_entries(
        "导出测试",
        [PlaylistEntry(title="完全陌生的歌", artist="陌生人")],
        "",
    )
    dialog.online_toggle.setChecked(False)
    dialog._start_matching()
    _pump(qapp, dialog)
    assert [row.status for row in dialog._matcher.rows] == ["unmatched"]

    target = dialog._export_missing(dialog._matcher.rows)
    csv_path = dialog.source_hint.text().split("导出到 ", 1)[-1]
    from pathlib import Path

    assert Path(csv_path).exists()
    text = Path(csv_path).read_text(encoding="utf-8-sig")
    assert "未匹配" in text and "完全陌生的歌" in text
