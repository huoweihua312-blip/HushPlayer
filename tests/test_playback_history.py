"""播放历史：一次逻辑收听会话最多记一次，失败可重试，seek/拖到结尾不算收听。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from hushplayer.audio.controller import LISTEN_CONFIRM_MS, PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.model.track import ONLINE, Track
from hushplayer.online.models import SourceInfo

SOURCE = SourceInfo(
    id="custom_source_hist",
    name="历史测试源",
    platform="wy",
    enabled=True,
    capabilities={"search": True, "playback": True},
)


class _Client(QObject):
    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.sources: list[SourceInfo] = []
        self.resolve_calls: list[dict] = []
        self.search_calls: list[tuple[str, str]] = []

    def resolve_playback(self, source_id, track, callback=None, *, quality="standard", timeout=22000):
        self.resolve_calls.append({"source_id": source_id, "payload": dict(track or {}), "quality": quality})
        if callback:
            callback({"ok": True, "data": {"url": "https://cdn.example.com/a.mp3",
                                           "mime": "audio/mpeg", "ext": "mp3"}})
        return len(self.resolve_calls)

    def search(self, source_id, keyword, page=1, callback=None, *, timeout=8000, kind="music"):
        self.search_calls.append((source_id, keyword))
        if callback:
            callback({"ok": True, "data": []})
        return len(self.search_calls)

    def cancel(self, request_id) -> None:
        return None

    def ensure_started(self) -> None:
        return None


class _Engine(PlaybackEngine):
    """No real decoder: tests drive state/positions by hand."""

    def __init__(self) -> None:
        super().__init__()
        self.fake_state = "stopped"
        self.loads: list[str] = []

    @property
    def state(self) -> str:
        return self.fake_state

    def load(self, source: str, *, duration_hint: int = 0, autoplay: bool = True) -> None:
        self.loads.append(str(source))
        self.fake_state = "playing" if autoplay else "stopped"
        self.state_changed.emit(self.fake_state)

    def play(self) -> None:
        self.fake_state = "playing"
        self.state_changed.emit("playing")

    def stop(self) -> None:
        self.fake_state = "stopped"
        self.state_changed.emit("stopped")


def _track(track_id: str = "t1", *, duration_ms: int = 180_000, remote: str = "remote-1") -> Track:
    return Track(
        id=track_id,
        kind=ONLINE,
        title=f"歌 {track_id}",
        artist="测试歌手",
        album="测试专辑",
        duration_ms=duration_ms,
        source_id=SOURCE.id,
        source_name=SOURCE.name,
        remote_id=remote,
        raw={"id": remote},
    )


def _controller(library, *, source: SourceInfo = SOURCE):
    client = _Client()
    engine = _Engine()
    controller = PlayerController(engine=engine, client=client)
    controller._sources = [source]
    return controller, engine, client


def _wire(controller: PlayerController, library) -> list[tuple[str, bool]]:
    recorded: list[tuple[str, bool]] = []

    def record(track) -> None:
        ok = library.record_play(track)
        recorded.append((track.id, ok))
        controller.note_play_recorded(track.id, ok)

    controller.listening_confirmed.connect(record)
    return recorded


def _advance(controller: PlayerController, start_ms: int, seconds: int, step_ms: int = 1000) -> int:
    """模拟真实播放推进（每步 ≤1200ms 才算有效推进）。"""
    position = start_ms
    controller._on_state("playing")
    for _ in range(seconds):
        position += step_ms
        controller._on_position(position)
    return position


def _play_count(library, track_id: str) -> int:
    row = library.db.connection().execute(
        "SELECT play_count FROM tracks WHERE id=?", (track_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def _history_count(library, track_id: str) -> int:
    row = library.db.connection().execute(
        "SELECT COUNT(*) FROM history WHERE track_id=?", (track_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def test_pause_resume_does_not_double_count(library, qapp) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get(track.id)], 0)
    position = _advance(controller, 0, 25)

    # 暂停/继续多次：不得再记一次。
    for _ in range(4):
        controller._on_state("paused")
        position = _advance(controller, position, 2)

    assert recorded == [(track.id, True)]
    assert _play_count(library, track.id) == 1
    assert _history_count(library, track.id) == 1


def test_switching_track_starts_new_episode(library, qapp) -> None:
    first, second = _track("a"), _track("b", remote="remote-2")
    library.tracks.upsert(first)
    library.tracks.upsert(second)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get("a"), library.tracks.get("b")], 0)
    _advance(controller, 0, 22)
    controller.play_tracks([library.tracks.get("b")], 0)
    _advance(controller, 0, 22)

    assert [item[0] for item in recorded] == ["a", "b"]
    assert _play_count(library, "a") == 1
    assert _play_count(library, "b") == 1


def test_seek_does_not_add_listen_time(library, qapp) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get(track.id)], 0)
    controller._on_state("playing")
    controller._on_position(1000)
    # 拖到 2:00：单次跳变远超 1200ms，不计入累计时间。
    controller._on_position(120_000)
    assert controller.listening_listened_ms == 1000
    position = _advance(controller, 120_000, 10)
    assert recorded == []
    position = _advance(controller, position, 15)
    assert recorded == [(track.id, True)]


def test_drag_to_end_is_not_a_listen(library, qapp) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get(track.id)], 0)
    controller._on_state("playing")
    controller._on_position(179_000)  # 直接拖到结尾
    controller._on_end_of_media()

    assert recorded == []
    assert _play_count(library, track.id) == 0


def test_short_track_counts_when_played_through(library, qapp) -> None:
    track = _track("short", duration_ms=8_000)
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get("short")], 0)
    _advance(controller, 0, 8)
    controller._on_end_of_media()

    assert recorded == [("short", True)]
    assert _play_count(library, "short") == 1


def test_repeat_one_creates_new_episode(library, qapp) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)
    controller.queue.set_repeat("one")

    controller.play_tracks([library.tracks.get(track.id)], 0)
    _advance(controller, 0, 21)
    episode = controller.listening_episode

    controller._on_end_of_media()
    assert controller.listening_episode == episode + 1
    assert controller.listening_listened_ms == 0

    _advance(controller, 0, 21)
    assert [item[0] for item in recorded] == [track.id, track.id]
    assert _play_count(library, track.id) == 2


def test_retry_load_keeps_same_episode(library, qapp) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get(track.id)], 0)
    position = _advance(controller, 0, 10)
    episode = controller.listening_episode

    # 换音质 / URL 重试走的是同一次 _load，不得开新会话。
    controller._load(controller.current_track, position=position)
    assert controller.listening_episode == episode
    assert controller.listening_listened_ms >= 10_000

    _advance(controller, position, 12)
    assert recorded == [(track.id, True)]


def test_recorded_episode_is_not_written_again(library, qapp) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get(track.id)], 0)
    position = _advance(controller, 0, 25)
    _advance(controller, position, 30)

    assert recorded == [(track.id, True)]
    assert _play_count(library, track.id) == 1


def test_failed_db_write_is_retried_once_successfully(library, qapp, monkeypatch) -> None:
    track = _track()
    library.tracks.upsert(track)
    controller, _engine, _client = _controller(library)

    original = library.record_play
    calls = {"n": 0}

    def flaky(track_obj, context=""):
        calls["n"] += 1
        if calls["n"] < 3:
            return False
        return original(track_obj, context)

    monkeypatch.setattr(library, "record_play", flaky)
    recorded: list[tuple[str, bool]] = []

    def record(track_obj) -> None:
        ok = library.record_play(track_obj, controller.queue.context)
        recorded.append((track_obj.id, ok))
        controller.note_play_recorded(track_obj.id, ok)

    controller.listening_confirmed.connect(record)

    controller.play_tracks([library.tracks.get(track.id)], 0)
    _advance(controller, 0, 21)
    assert recorded == [(track.id, False)]
    assert controller._episode_recorded is False

    controller._retry_listening_record()
    controller._retry_listening_record()
    assert recorded == [(track.id, False), (track.id, False), (track.id, True)]
    assert controller._episode_recorded is True
    assert _play_count(library, track.id) == 1

    # 已 recorded：后续位置推进和手动重试都不能再写。
    controller._retry_listening_record()
    assert len(recorded) == 3


def test_switching_away_discards_unrecorded_episode(library, qapp) -> None:
    first, second = _track("a"), _track("b", remote="remote-2")
    library.tracks.upsert(first)
    library.tracks.upsert(second)
    controller, _engine, _client = _controller(library)
    recorded = _wire(controller, library)

    controller.play_tracks([library.tracks.get("a")], 0)
    _advance(controller, 0, 25)
    controller.play_tracks([library.tracks.get("b")], 0)
    controller._on_state("playing")
    # A 已记录的迟到确认不能写到 B 的会话上。
    controller.note_play_recorded("a", True)
    assert controller._episode_recorded is False
    _advance(controller, 0, 21)

    assert [item[0] for item in recorded] == ["a", "b"]
