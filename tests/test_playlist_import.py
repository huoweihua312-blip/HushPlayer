"""Playlist import: parsing, link detection, matching and persistence."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from hushplayer.model.track import Track
from hushplayer.online.models import track_from_item
from hushplayer.services.playlist_import import (
    PlaylistEntry,
    parse_playlist,
    parse_playlist_text,
)
from hushplayer.services.playlist_link import (
    detect_platform,
    extract_playlist_id,
    fetch_link,
)
from hushplayer.services.playlist_matcher import (
    MatchRow,
    PlaylistMatcher,
    apply_import,
    find_playlist,
)


# --------------------------------------------------------------------------- parsing
def test_parse_m3u_keeps_order_and_duration(tmp_path: Path) -> None:
    path = tmp_path / "list.m3u8"
    path.write_text(
        "#EXTM3U\n#PLAYLIST:夜航\n#EXTINF:225,周杰伦 - 晴天\n/fake/晴天.mp3\n"
        "#EXTINF:4:02,加木 - 家书\n/fake/家书.flac\n",
        encoding="utf-8",
    )
    parsed = parse_playlist(path)
    assert parsed.name == "夜航"
    assert [entry.title for entry in parsed.entries] == ["晴天", "家书"]
    assert parsed.entries[0].artist == "周杰伦"
    assert parsed.entries[0].duration_ms == 225_000
    assert parsed.entries[1].duration_ms == 242_000


def test_parse_csv_detects_chinese_headers_and_bom(tmp_path: Path) -> None:
    path = tmp_path / "list.csv"
    path.write_bytes(
        "专辑,时长,歌手,歌曲\n羲和,4:02,加木,家书\n叶惠美,3:20,周杰伦,以父之名\n".encode("utf-8-sig")
    )
    parsed = parse_playlist(path)
    assert parsed.kind == "csv"
    assert [entry.title for entry in parsed.entries] == ["家书", "以父之名"]
    assert parsed.entries[0].album == "羲和"
    assert parsed.entries[0].artist == "加木"
    assert parsed.entries[0].duration_ms == 242_000


def test_parse_txt_strips_numbering_and_timestamps() -> None:
    text = "1. 周杰伦 - 晴天\n2、 [03:12] 加木 - 家书\n晴天\n"
    parsed = parse_playlist_text(text, name="粘贴")
    assert parsed.name == "粘贴"
    assert [entry.title for entry in parsed.entries] == ["晴天", "家书", "晴天"]
    assert parsed.entries[0].artist == "周杰伦"
    assert parsed.entries[1].duration_ms == 192_000
    assert parsed.entries[2].artist == ""


def test_parse_pls(tmp_path: Path) -> None:
    path = tmp_path / "list.pls"
    path.write_text(
        "[playlist]\nFile1=/music/a.mp3\nTitle1=家书\nLength1=242\nFile2=/music/b.flac\nTitle2=晴天\n",
        encoding="utf-8",
    )
    parsed = parse_playlist(path)
    assert [entry.title for entry in parsed.entries] == ["家书", "晴天"]
    assert parsed.entries[0].duration_ms == 242_000


def test_parse_apple_library_xml_restores_playlist_order(tmp_path: Path) -> None:
    data = {
        "Tracks": {
            "1": {
                "Track ID": 1,
                "Name": "家书",
                "Artist": "加木",
                "Album": "羲和",
                "Total Time": 242_000,
                "Location": "file://localhost/F:/Music/%E5%AE%B6%E4%B9%A6.mp3",
            },
            "2": {
                "Track ID": 2,
                "Name": "晴天",
                "Artist": "周杰伦",
                "Album": "叶惠美",
                "Total Time": 269_000,
            },
        },
        "Playlists": [
            {"Name": "音乐库", "Playlist Items": [{"Track ID": 1}, {"Track ID": 2}]},
        ],
    }
    path = tmp_path / "Library.xml"
    path.write_bytes(plistlib.dumps(data))
    parsed = parse_playlist(path)
    assert parsed.kind == "plist"
    assert [entry.title for entry in parsed.entries] == ["家书", "晴天"]
    assert parsed.entries[0].artist == "加木"
    assert parsed.entries[0].duration_ms == 242_000
    assert parsed.entries[0].path.endswith("家书.mp3")


# --------------------------------------------------------------------------- links
@pytest.mark.parametrize(
    "url,platform",
    [
        ("https://music.163.com/playlist?id=3778678", "netease"),
        ("https://music.apple.com/cn/playlist/foo/pl.123", "apple"),
        ("https://y.qq.com/n/ryqq/playlist/123456", "qq"),
        ("https://www.kugou.com/yy/special/single/12345.html", "kugou"),
        ("https://www.kuwo.cn/playlist_detail/123456", "kuwo"),
        ("https://example.com/x", "unknown"),
    ],
)
def test_detect_platform(url: str, platform: str) -> None:
    assert detect_platform(url) == platform


def test_extract_ids() -> None:
    assert extract_playlist_id("https://music.163.com/playlist?id=3778678") == "3778678"
    assert extract_playlist_id("https://music.apple.com/cn/playlist/foo/pl.abc-def") == "pl.abc-def"
    assert extract_playlist_id("https://y.qq.com/n/ryqq/playlist/123456") == "123456"


def test_unsupported_platforms_explain_why() -> None:
    result = fetch_link("https://music.apple.com/cn/playlist/foo/pl.123")
    assert result.supported is False
    assert result.reason
    assert "Apple" in result.reason or "导出" in result.reason




def _pump(qapp, matcher, *, timeout: float = 5.0) -> None:
    """Run the deferred matcher stages until every row has a verdict."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if all(row.status != "pending" for row in matcher.rows):
            # one extra round lets the finished/progress signals drain
            qapp.processEvents()
            return
        time.sleep(0.005)
    raise AssertionError(
        "matcher did not settle: " + repr([row.status for row in matcher.rows])
    )


# --------------------------------------------------------------------------- matcher
class FakeClient:
    """Minimal OnlineSourceClient double: no QObject, callback based."""

    def __init__(self, items=None, *, playback_ok=True) -> None:
        self.sources = [
            {"id": "fake", "name": "假音源", "platform": "qq", "enabled": True,
             "capabilities": {"search": True, "playback": True, "lyrics": True}},
        ]
        self._items = items or {}
        self._playback_ok = playback_ok
        self.searches: list[str] = []

    def search(self, source_id, keyword, page=1, callback=None, *, timeout=0, kind="music"):
        self.searches.append(keyword)
        callback({"ok": True, "data": self._items.get(keyword, [])})
        return 1

    def resolve_playback(self, source_id, track, callback=None, timeout=0):
        if self._playback_ok:
            callback({"ok": True, "data": {"url": "http://example/a.mp3"}})
        else:
            callback({"ok": False, "error": {"message": "no"}})
        return 1


def _item(title: str, artist: str, *, duration: int = 242000, sid: str = "remote-1") -> dict:
    return {
        "id": sid,
        "title": title,
        "artist": artist,
        "album": "羲和",
        "duration": duration,
        "artwork": "",
    }


def test_matcher_prefers_local_and_marks_unmatched(loaded_library, qapp) -> None:
    entries = [
        PlaylistEntry(title="夜航信号", artist="Aurora Field"),
        PlaylistEntry(title="完全不存在的歌", artist="无名"),
    ]
    matcher = PlaylistMatcher(FakeClient(), loaded_library)
    matcher.start(entries, online=False)
    _pump(qapp, matcher)
    assert matcher.rows[0].status == "local"
    assert matcher.rows[1].status == "unmatched"
    assert matcher.rows[1].track is None


def test_matcher_uses_online_and_verifies(loaded_library, qapp) -> None:
    client = FakeClient(
        {"家书 加木": [_item("家书", "加木")]},
    )
    matcher = PlaylistMatcher(client, loaded_library)
    matcher.start([PlaylistEntry(title="家书", artist="加木")], online=True)
    _pump(qapp, matcher)
    row = matcher.rows[0]
    assert row.status == "online"
    assert row.verified is True
    assert row.track is not None and row.track.source_id == "fake"


def test_matcher_marks_unverified_when_playback_fails(loaded_library, qapp) -> None:
    client = FakeClient({"家书 加木": [_item("家书", "加木")]}, playback_ok=False)
    matcher = PlaylistMatcher(client, loaded_library)
    matcher.start([PlaylistEntry(title="家书", artist="加木")], online=True)
    _pump(qapp, matcher)
    row = matcher.rows[0]
    assert row.status == "unverified"
    assert row.verified is False
    assert "无法解析" in row.note


def test_matcher_surfaces_ambiguous_results_for_review(loaded_library, qapp) -> None:
    client = FakeClient(
        {"晴天 周杰伦": [_item("晴天", "周杰伦"), _item("晴天 (Live)", "周杰伦", sid="remote-2")]},
    )
    matcher = PlaylistMatcher(client, loaded_library)
    matcher.start([PlaylistEntry(title="晴天", artist="周杰伦")], online=True)
    _pump(qapp, matcher)
    row = matcher.rows[0]
    assert row.status in ("online", "review")
    if row.status == "review":
        assert row.candidates
        assert len(row.candidates) <= 5


def test_matcher_manual_skip_and_choose(loaded_library, qapp) -> None:
    matcher = PlaylistMatcher(FakeClient(), loaded_library)
    matcher.start(
        [
            PlaylistEntry(title="夜航信号", artist="Aurora Field"),
            PlaylistEntry(title="不存在的", artist=""),
        ],
        online=False,
    )
    _pump(qapp, matcher)
    matcher.skip(1)
    assert matcher.rows[1].status == "skipped"
    matcher.unskip(1)
    assert matcher.rows[1].status == "unmatched"
    local = loaded_library.tracks.search_local("夜航信号", limit=1)[0]
    matcher.choose(1, local)
    assert matcher.rows[1].status == "local"
    assert matcher.rows[1].track is local


# --------------------------------------------------------------------------- apply
def test_apply_import_new_merge_replace(loaded_library) -> None:
    local = loaded_library.tracks.search_local("夜航信号", limit=2)
    assert len(local) >= 1
    rows = [MatchRow(entry=PlaylistEntry("夜航信号"), status="local", track=local[0])]
    outcome = apply_import(loaded_library, "导入测试", rows)
    assert outcome.added == 1
    playlist = loaded_library.playlist(outcome.playlist_id)
    assert playlist is not None and playlist.track_count == 1

    rows.append(MatchRow(entry=PlaylistEntry("重复"), status="local", track=local[0]))
    merged = apply_import(loaded_library, "导入测试", rows, mode="merge", playlist_id=outcome.playlist_id)
    assert merged.added == 1
    assert merged.duplicates == 1

    replaced = apply_import(
        loaded_library,
        "导入测试",
        [MatchRow(entry=PlaylistEntry("夜航信号"), status="local", track=local[0])],
        mode="replace",
        playlist_id=outcome.playlist_id,
    )
    assert replaced.added == 1
    assert loaded_library.playlist(outcome.playlist_id).track_count == 1


def test_apply_import_skips_review_and_pending(loaded_library) -> None:
    local = loaded_library.tracks.search_local("夜航信号", limit=1)[0]
    rows = [
        MatchRow(entry=PlaylistEntry("a"), status="review", track=local),
        MatchRow(entry=PlaylistEntry("b"), status="pending"),
        MatchRow(entry=PlaylistEntry("c"), status="local", track=local),
    ]
    outcome = apply_import(loaded_library, "待确认测试", rows)
    assert outcome.added == 1
    assert outcome.pending == 2


def test_find_playlist_skips_system(loaded_library) -> None:
    assert find_playlist(loaded_library, "我喜欢") is None
    assert any(item.system for item in loaded_library.playlists_all())
    assert find_playlist(loaded_library, "不存在") is None

def test_match_strength_thresholds_and_helpers() -> None:
    from hushplayer.model.track import Track
    from hushplayer.services.playlist_import import PlaylistEntry
    from hushplayer.services.playlist_matcher import (
        MATCH_STRENGTHS,
        MatchCandidate,
        _dedupe_candidates,
        _query_variants,
    )

    assert MATCH_STRENGTHS["strict"] == (80, 15)
    assert MATCH_STRENGTHS["balanced"] == (75, 8)
    assert MATCH_STRENGTHS["loose"] == (60, 0)

    entry = PlaylistEntry(title="茶花开了 (Live)", artist="王睿卓", album="茶花开了")
    variants = _query_variants(entry)
    assert variants[0] == "茶花开了 (Live) 王睿卓"
    assert "茶花开了 王睿卓" in variants
    assert len(variants) == len(set(variants))

    a = Track(id="a", title="x", source_id="s1", remote_id="r1")
    b = Track(id="b", title="x", source_id="s1", remote_id="r1")
    c = Track(id="c", title="x", source_id="s2", remote_id="r1")
    deduped = _dedupe_candidates([
        MatchCandidate(track=a, score=90),
        MatchCandidate(track=b, score=70),
        MatchCandidate(track=c, score=80),
    ])
    assert [item.track.id for item in deduped] == ["a", "c"]
