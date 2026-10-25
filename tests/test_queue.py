"""播放队列：随机顺序一致性、循环模式、增删移动与持久化。"""

from __future__ import annotations

from hushplayer.audio.queue import PlayQueue
from hushplayer.model.track import Track


def make_tracks(count: int = 10) -> list[Track]:
    return [
        Track(
            id=f"local:track{index}",
            title=f"歌曲 {index}",
            artist=f"歌手 {index % 3}",
            album="专辑",
            duration_ms=60_000 + index,
            path=f"C:/music/{index}.mp3",
            kind="local",
        )
        for index in range(count)
    ]


def ids(tracks) -> list[str]:
    return [track.id for track in tracks]


def test_set_tracks_defaults_to_first() -> None:
    queue = PlayQueue()
    queue.set_tracks(make_tracks(5), context="专辑 · 专辑")
    assert queue.count == 5
    assert queue.current.title == "歌曲 0"
    assert queue.context == "专辑 · 专辑"
    assert queue.shuffle is False
    assert queue.repeat == "off"


def test_shuffle_keeps_current_and_covers_all() -> None:
    tracks = make_tracks(12)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=7)
    queue.set_shuffle(True)
    assert queue.current.id == tracks[7].id, "开启随机后当前曲目必须保持不变"
    assert sorted(ids(queue.items)) == sorted(ids(tracks))
    played = [queue.current.id]
    for _ in range(len(tracks) - 1):
        track = queue.next_track(auto=True)
        assert track is not None
        played.append(track.id)
    assert len(set(played)) == len(tracks), "一轮随机不应重复播放"


def test_shuffle_next_previous_walk_the_same_order() -> None:
    tracks = make_tracks(9)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=0)
    queue.set_shuffle(True)
    forward = [queue.current.id]
    for _ in range(4):
        forward.append(queue.next_track().id)
    landed = queue.current.id
    for _ in range(4):
        queue.previous_track()
    assert queue.current.id == forward[0]
    for _ in range(4):
        queue.next_track()
    assert queue.current.id == landed


def test_shuffle_toggle_off_restores_index_order() -> None:
    tracks = make_tracks(6)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=2)
    expected = queue.current.id
    queue.set_shuffle(True)
    queue.set_shuffle(False)
    assert ids(queue.items) == [track.id for track in queue.items]
    assert queue.current.id == expected
    assert queue.next_track().id == tracks[3].id


def test_repeat_one_keeps_track_on_auto_next() -> None:
    queue = PlayQueue()
    queue.set_tracks(make_tracks(4), start_index=0)
    queue.set_repeat("one")
    assert queue.next_track(auto=True).id == "local:track0"
    assert queue.next_track().id == "local:track1", "手动下一首应前进"


def test_repeat_all_wraps_around() -> None:
    queue = PlayQueue()
    queue.set_tracks(make_tracks(3), start_index=2)
    queue.set_repeat("all")
    assert queue.next_track(auto=True).id == "local:track0"


def test_repeat_off_stops_at_end() -> None:
    queue = PlayQueue()
    queue.set_tracks(make_tracks(3), start_index=1)
    assert queue.next_track(auto=True).id == "local:track2"
    assert queue.next_track(auto=True) is None
    assert queue.current.id == "local:track2"


def test_cycle_repeat() -> None:
    queue = PlayQueue()
    seen = [queue.cycle_repeat() for _ in range(4)]
    assert seen == ["all", "one", "off", "all"]


def test_append_while_shuffled_keeps_upcoming_consistent() -> None:
    tracks = make_tracks(5)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=0)
    queue.set_shuffle(True)
    upcoming_before = ids(queue.upcoming())
    extra = make_tracks(7)[5:]
    queue.append(extra)
    assert queue.count == 7
    planned = ids(queue.upcoming())
    # 追加歌曲排在末尾：已预告的 upcoming 顺序不被破坏
    assert planned[: len(upcoming_before)] == upcoming_before
    assert planned[-len(extra):] == ids(extra)


def test_insert_next_plays_immediately_after_current() -> None:
    tracks = make_tracks(4)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=0)
    bonus = make_tracks(5)[4]
    queue.insert_next([bonus])
    assert queue.upcoming()[0].id == bonus.id
    assert queue.next_track().id == bonus.id


def test_remove_rows_keeps_current_playing() -> None:
    tracks = make_tracks(5)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=2)
    queue.remove_rows([3])
    assert queue.count == 4
    assert queue.current.id == tracks[2].id
    assert tracks[3].id not in ids(queue.items)


def test_remove_current_falls_to_neighbour() -> None:
    tracks = make_tracks(5)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=2)
    queue.remove_rows([2])
    assert queue.current.id == tracks[3].id


def test_move_row_updates_order() -> None:
    tracks = make_tracks(4)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=0)
    assert queue.move_row(3, 0) is True
    assert queue.items[0].id == tracks[3].id
    assert queue.current.id == tracks[0].id, "移动其它行不应改变当前曲目"
    queue.set_current_row(0)
    assert queue.current.id == tracks[3].id


def test_snapshot_and_restore() -> None:
    tracks = make_tracks(4)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=1, context="歌单 · 测试")
    queue.set_shuffle(True)
    queue.set_repeat("all")
    payload = queue.to_dict()

    restored = PlayQueue()
    restored.restore(payload, resolver=lambda track_id: next((t for t in tracks if t.id == track_id), None))
    assert restored.count == 4
    assert restored.shuffle is True
    assert restored.repeat == "all"
    assert restored.context == "歌单 · 测试"
    assert restored.current.id == tracks[1].id


def test_restore_filters_missing_tracks() -> None:
    tracks = make_tracks(3)
    queue = PlayQueue()
    queue.set_tracks(tracks, start_index=0)
    payload = queue.to_dict()
    restored = PlayQueue()
    restored.restore(payload, resolver=lambda track_id: None)
    assert restored.count == 0
    assert restored.current is None


def test_clear() -> None:
    queue = PlayQueue()
    queue.set_tracks(make_tracks(3))
    queue.clear()
    assert queue.count == 0
    assert queue.current is None
    assert queue.next_track() is None

def test_replace_track_swaps_same_id_in_place() -> None:
    """来源替换后队列里的旧对象要被换掉，播放位置与顺序不动。"""

    queue = PlayQueue()
    queue.set_tracks(make_tracks(3), start_index=1)
    old = queue.current
    assert old is not None
    updated = Track(id=old.id, kind="online", title="新标题", artist="新歌手",
                    source_id="another", remote_id="remote:1")
    assert queue.replace_track(updated) is True
    assert queue.current is not None
    assert queue.current.title == "新标题"
    assert queue.current_order_pos == 1
    assert queue.replace_track(Track(id="local:missing", kind="local")) is False
