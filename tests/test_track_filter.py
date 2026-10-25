from __future__ import annotations

from types import SimpleNamespace

from hushplayer.model.track import Track
from hushplayer.ui.pages.trackpage import filter_tracks, play_queue_for


def _track(title: str, artist: str, album: str = "", source: str = "") -> Track:
    return Track(id=f"id-{title}-{artist}", title=title, artist=artist,
                 album=album, source_name=source, kind="online")


def test_filter_empty_returns_all() -> None:
    tracks = [_track("晴天", "周杰伦"), _track("夜航", "Aurora")]
    assert filter_tracks(tracks, "   ") == tracks


def test_filter_matches_title_artist_album_and_source() -> None:
    tracks = [
        _track("晴天", "周杰伦", "叶惠美", "网易云"),
        _track("夜航信号", "Aurora Field", "夜航", "酷狗"),
    ]
    assert [t.title for t in filter_tracks(tracks, "晴天")] == ["晴天"]
    assert [t.title for t in filter_tracks(tracks, "周杰伦")] == ["晴天"]
    assert [t.title for t in filter_tracks(tracks, "叶惠美")] == ["晴天"]
    assert [t.title for t in filter_tracks(tracks, "酷狗")] == ["夜航信号"]


def test_filter_supports_multiple_tokens() -> None:
    tracks = [
        _track("晴天", "周杰伦", "叶惠美", "网易云"),
        _track("晴天", "孙燕姿", "Start", "QQ"),
    ]
    assert [t.artist for t in filter_tracks(tracks, "晴天 孙燕姿")] == ["孙燕姿"]


def test_filter_is_case_insensitive() -> None:
    tracks = [_track("Long Way Home", "The Paper Lanterns", "Home", "kw")]
    assert len(filter_tracks(tracks, "long way")) == 1
    assert len(filter_tracks(tracks, "PAPER")) == 1


class _Bindings:
    def __init__(self) -> None:
        self.calls = []

    def manual_choose(self, track_id, choice):
        self.calls.append((track_id, choice))
        return True


def test_manual_replace_emits_update_and_keeps_artwork(loaded_library) -> None:
    track = Track(
        id="online:test:1", title="家书", artist="加木", album="羲和",
        kind="online", source_id="custom_source_kg", source_name="酷狗",
        remote_id="kg-9", artwork_url="http://old/cover.jpg", duration_ms=242000,
    )
    loaded_library.tracks.upsert(track)
    loaded_library.source_bindings = _Bindings()

    changed: list[str] = []
    loaded_library.track_updated.connect(changed.append)

    candidate = SimpleNamespace(
        source_id="custom_source_wy", source_name="网易音乐", remote_id="wy-9",
        title="家书", artist="加木", album="羲和", duration_ms=242000,
        artwork_url="http://new/cover.jpg", raw={"id": "wy-9"},
    )
    updated = loaded_library.replace_online_source(track.id, candidate)

    assert updated is not None
    assert loaded_library.source_bindings.calls
    assert changed == [track.id]


def test_manual_binding_writes_new_artwork(loaded_library) -> None:
    from hushplayer.services.binding import BindingChoice, TrackBindingService

    track = Track(
        id="online:test:2", title="家书", artist="加木", album="羲和",
        kind="online", source_id="custom_source_kg", source_name="酷狗",
        remote_id="kg-10", artwork_url="http://old/cover.jpg", duration_ms=242000,
    )
    loaded_library.tracks.upsert(track)
    service = TrackBindingService(loaded_library)
    assert service.manual_choose(
        track.id,
        BindingChoice(
            source_id="custom_source_wy", source_name="网易音乐", remote_id="wy-10",
            title="家书", artist="加木", album="羲和", duration_ms=242000,
            artwork_url="http://new/cover.jpg", raw={"id": "wy-10"},
        ),
    )
    stored = loaded_library.tracks.get(track.id)
    assert stored is not None
    assert stored.source_id == "custom_source_wy"
    assert stored.remote_id == "wy-10"
    assert stored.artwork_url == "http://new/cover.jpg"


def test_play_queue_uses_full_page_order_when_filtered() -> None:
    tracks = [
        _track("A", "林俊杰"),
        _track("B", "林俊杰"),
        _track("C", "其他"),
        _track("D", "林俊杰"),
    ]
    visible = filter_tracks(tracks, "林俊杰")
    assert [t.title for t in visible] == ["A", "B", "D"]

    # 双击搜索结果里的第二首（B），队列仍应是整页顺序，并且从 B 在整页里的位置开始。
    queue, start = play_queue_for(tracks, visible, 1)
    assert queue is tracks
    assert start == 1
    assert queue[start].title == "B"

    # 下一首应当是整页的下一首 C，而不是搜索结果里的下一首 D。
    assert queue[start + 1].title == "C"


def test_play_queue_falls_back_when_anchor_missing() -> None:
    tracks = [_track("A", "x")]
    visible = [_track("Z", "y")]
    queue, start = play_queue_for(tracks, visible, 0)
    assert queue is visible
    assert start == 0


def test_play_queue_handles_empty_visible() -> None:
    tracks = [_track("A", "x")]
    queue, start = play_queue_for(tracks, [], 3)
    assert queue is tracks
    assert start == 0
