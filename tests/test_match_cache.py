"""歌单匹配：搜索候选可以复用，但「选了哪首」必须按当前行重新判断。"""

from __future__ import annotations

from hushplayer.services.playlist_import import PlaylistEntry
from hushplayer.services.playlist_matcher import PlaylistMatcher


class _Tracks:
    def search_local(self, *_args, **_kwargs):
        return []


class _Lib:
    tracks = _Tracks()


class FakeClient:
    """A fake source that always returns the same candidate pool."""

    def __init__(self, items=None) -> None:
        self.sources = [
            {"id": "fake", "name": "假音源", "platform": "qq", "enabled": True,
             "capabilities": {"search": True, "playback": True, "lyrics": True}},
        ]
        self._items = list(items or [])
        self.searches: list[str] = []
        self.resolves: list[str] = []

    def search(self, source_id, keyword, page=1, callback=None, *, timeout=0, kind="music"):
        self.searches.append(keyword)
        callback({"ok": True, "data": list(self._items)})
        return 1

    def resolve_playback(self, source_id, track, callback=None, timeout=0, **_kw):
        self.resolves.append(str((track or {}).get("id") or ""))
        callback({"ok": True, "data": {"url": "http://example/a.mp3"}})
        return 1


def _item(title: str, artist: str, *, album: str = "羲和", duration: int = 242000,
          sid: str = "remote-1") -> dict:
    return {"id": sid, "title": title, "artist": artist, "album": album,
            "duration": duration, "artwork": ""}


def _pump(qapp, matcher, *, timeout: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if all(row.status != "pending" for row in matcher.rows):
            qapp.processEvents()
            return
        time.sleep(0.005)
    raise AssertionError("matcher did not settle: " + repr([r.status for r in matcher.rows]))


def _run(qapp, entries, client):
    matcher = PlaylistMatcher(client, _Lib())
    matcher.start(entries, online=True, strength="balanced", auto_adopt=True)
    _pump(qapp, matcher)
    return matcher


POOL = [
    _item("晴天", "周杰伦", album="叶惠美", duration=200000, sid="studio-1"),
    _item("晴天", "周杰伦", album="演唱会", duration=300000, sid="live-9"),
]


def test_same_title_different_version_does_not_reuse_choice(qapp) -> None:
    """同名不同版本：旧实现按标题+歌手复用整行结果，第二首会被写成第一首。"""
    client = FakeClient(POOL)
    entries = [
        PlaylistEntry(title="晴天", artist="周杰伦", album="叶惠美", duration_ms=200000),
        PlaylistEntry(title="晴天", artist="周杰伦", album="演唱会", duration_ms=300000,
                      origin_platform="wy", origin_remote_id="live-9"),
    ]
    matcher = _run(qapp, entries, client)
    first, second = matcher.rows
    assert first.track is not None and second.track is not None
    assert first.track.remote_id == "studio-1", "第一行按自己的时长应选录音室版"
    assert second.track.remote_id == "live-9", "第二行必须按自己的版本/时长重新评分"
    assert len(client.searches) == 2, "身份不同的行不能共用同一次搜索结论"


def test_identical_rows_reuse_search_candidates(qapp) -> None:
    client = FakeClient(POOL)
    entries = [
        PlaylistEntry(title="晴天", artist="周杰伦", album="叶惠美", duration_ms=200000),
        PlaylistEntry(title="晴天", artist="周杰伦", album="叶惠美", duration_ms=200000),
    ]
    matcher = _run(qapp, entries, client)
    assert len(client.searches) == 1, "完全相同的行才允许复用搜索候选"
    assert matcher.rows[0].track is not None
    assert matcher.rows[1].track is not None
    assert matcher.rows[0].track.remote_id == matcher.rows[1].track.remote_id


def test_cached_row_is_reverified(qapp) -> None:
    """缓存只复用候选；播放可用性必须重新验证（不能复制 verified 标记）。"""
    client = FakeClient(POOL)
    entries = [
        PlaylistEntry(title="晴天", artist="周杰伦", album="叶惠美", duration_ms=200000),
        PlaylistEntry(title="晴天", artist="周杰伦", album="叶惠美", duration_ms=200000),
    ]
    matcher = _run(qapp, entries, client)
    assert len(client.resolves) == 2, "两行都要各自 resolve 一次才算可播放"


def test_unmatched_rows_are_not_cached(qapp) -> None:
    client = FakeClient([])
    entries = [
        PlaylistEntry(title="本地有", artist="歌手"),
        PlaylistEntry(title="本地有", artist="歌手"),
    ]
    matcher = _run(qapp, entries, client)
    assert matcher.rows[0].status == "unmatched"
    assert matcher.rows[1].status == "unmatched"
    base_query = f"{entries[0].title} {entries[0].artist}"
    # 每行 3 次查询（原词 + 2 个变体）；若「无候选」被当成缓存命中，
    # 第二行会直接复用第一行的失败结论，查询次数就会减半。
    assert client.searches.count(base_query) == 4, "没有候选的结论不能缓存成命中"
    assert len(client.searches) == 6
