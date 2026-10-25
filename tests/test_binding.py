"""音源绑定（track_source_binding_state）的行为测试。

覆盖任务书里的几条硬要求：

* 导入只写 ``auto/pending``，不得伪造已验证；
* ``manual`` 一旦写入，自动路径永远不能覆盖；
* 异步回调拿着旧 revision 写入必须被拒绝；
* 首次播放直接用绑定源，**零次跨源搜索**；
* 缓存 key 使用真实播放源，而不是原曲来源。
"""

from __future__ import annotations

import pytest

from hushplayer.audio.controller import PlayerController
from hushplayer.audio.engine import PlaybackEngine
from hushplayer.model.track import Track, album_key
from hushplayer.services.binding import BindingChoice, TrackBindingService
from hushplayer.store.db import Database
from hushplayer.store.repository import TrackRepository
from PySide6.QtCore import QObject, Signal

from test_cross_source import KG, QQ, KG_ITEM, QQ_ITEM


class FakeLibrary:
    def __init__(self, tmp_path) -> None:
        self.db = Database(tmp_path / "binding.db")
        self.tracks = TrackRepository(self.db)


@pytest.fixture()
def library(tmp_path):
    return FakeLibrary(tmp_path)


def _service(library: FakeLibrary) -> TrackBindingService:
    return TrackBindingService(library)


def _track(source_id: str = KG.id, remote_id: str = "kg-1") -> Track:
    return Track(
        id="t1",
        kind="online",
        source_id=source_id,
        source_name="酷狗",
        remote_id=remote_id,
        title="晴天",
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
        raw=dict(KG_ITEM),
    )


def _choice(source_id: str = QQ.id, remote_id: str = "qq-3") -> BindingChoice:
    return BindingChoice(
        source_id=source_id,
        source_name="QQ音乐",
        remote_id=remote_id,
        title="晴天",
        artist="周杰伦",
        album="叶惠美",
        duration_ms=269000,
        artwork_url="",
        album_id=album_key("叶惠美", "周杰伦"),
        artist_id="",
        raw=dict(QQ_ITEM),
    )


def test_import_choice_writes_auto_pending(library):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)

    assert service.import_choice(track.id, BindingChoice.from_track(track)) is True

    state = service.state(track.id)
    assert (state.selection_mode, state.verify_state) == ("auto", "pending")
    assert state.revision == 1


def test_manual_is_not_overwritten_by_auto(library):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)

    assert service.manual_choose(track.id, _choice()) is True
    assert service.state(track.id).manual is True

    # 即使带着正确 revision，自动路径也不能覆盖 manual。
    revision = service.state(track.id).revision
    assert (
        service.commit_binding(
            track.id,
            _choice(QQ.id, "qq-other"),
            mode="auto",
            verify_state="verified",
            expected_revision=revision,
        )
        is False
    )
    updated = library.tracks.get(track.id)
    assert updated is not None and updated.source_id == QQ.id
    assert service.state(track.id).selection_mode == "manual"


def test_stale_revision_is_rejected(library):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)

    assert service.manual_choose(track.id, _choice()) is True
    revision = service.state(track.id).revision

    assert (
        service.commit_binding(
            track.id,
            _choice(QQ.id, "qq-late"),
            mode="manual",
            verify_state="pending",
            expected_revision=revision - 1,
        )
        is False
    )
    assert library.tracks.get(track.id).remote_id == "qq-3"


def test_play_verified_and_failed_transitions(library):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    service.import_choice(track.id, BindingChoice.from_track(track))

    service.mark_play_verified(
        track.id, expected_revision=service.state(track.id).revision
    )
    state = service.state(track.id)
    assert state.verify_state == "verified"
    assert state.verified_at > 0
    assert state.revision == 2

    service.mark_failed(track.id, expected_revision=state.revision)
    assert service.state(track.id).verify_state == "failed"


def test_fallback_adoption_bumps_revision_and_verifies(library):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    service.import_choice(track.id, BindingChoice.from_track(track))
    revision = service.state(track.id).revision

    assert (
        service.adopt_verified_fallback(
            track.id, _choice(), expected_revision=revision
        )
        is True
    )
    state = service.state(track.id)
    assert state.verify_state == "verified"
    assert state.revision == revision + 1
    assert library.tracks.get(track.id).source_id == QQ.id


class _FakeClient(QObject):
    sources_changed = Signal(list)
    failure = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.resolve_calls: list[tuple[str, str]] = []
        self.search_calls: list[tuple[str, str]] = []

    def search(self, source_id, keyword, page=1, callback=None, **kwargs):
        self.search_calls.append((source_id, keyword))
        if callback:
            callback({"ok": True, "data": []})
        return 0

    def resolve_playback(self, source_id, payload, callback, **kwargs):
        self.resolve_calls.append((source_id, str(kwargs.get("quality"))))
        callback(
            {
                "ok": True,
                "data": {
                    "url": f"https://cdn.example.com/{source_id}.mp3",
                    "headers": {},
                    "mimeType": "audio/mpeg",
                    "quality": kwargs.get("quality") or "standard",
                },
            }
        )
        return 0

    def stop(self) -> None:
        return None

    def cancel(self, request_id) -> None:  # noqa: ANN001
        return None


def test_bound_track_resolves_without_cross_source_search(library):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    service.manual_choose(track.id, _choice())  # 绑定到 QQ

    client = _FakeClient()
    controller = PlayerController(
        engine=PlaybackEngine(), client=client, binding=service
    )
    controller.set_volume(0.0)
    controller._sources = [KG, QQ]  # noqa: SLF001 - test seam
    loaded: list = []
    controller.engine.load = lambda *a, **kw: loaded.append((a, kw))  # type: ignore[assignment]
    controller.proxy.register = lambda *a, **kw: "http://127.0.0.1:9/audio/x"  # type: ignore[assignment]

    controller.play_tracks([track], 0)

    # 绑定源直接解析 —— 没有任何搜索。
    assert client.search_calls == []
    assert [source for source, _ in client.resolve_calls] == [QQ.id]
    assert loaded, "engine.load 应该被调用"

    target = service.get_target(track.id)
    assert target is not None and target.source_id == QQ.id
    key = controller._resolve_cache_key(target)  # noqa: SLF001
    assert key.startswith(f"{QQ.id}:")
    assert key != controller._resolve_cache_key(track)  # noqa: SLF001


def test_import_rows_write_pending_binding_with_origin(library):
    from hushplayer.services.playlist_import import PlaylistEntry
    from hushplayer.services.playlist_matcher import MatchRow, _bind_import_choices

    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    library.source_bindings = service

    entry = PlaylistEntry(
        title="晴天", artist="周杰伦", album="叶惠美",
        origin_platform="netease", origin_remote_id="net-9527",
    )
    row = MatchRow(entry=entry, status="matched", track=track)
    _bind_import_choices(library, [row])

    state = service.state(track.id)
    assert (state.selection_mode, state.verify_state) == ("auto", "pending")
    assert (state.origin_platform, state.origin_remote_id) == ("netease", "net-9527")


def test_reimport_does_not_overwrite_manual_binding(library):
    from hushplayer.services.playlist_import import PlaylistEntry
    from hushplayer.services.playlist_matcher import MatchRow, _bind_import_choices

    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    library.source_bindings = service
    service.manual_choose(track.id, _choice())  # 用户手动选 QQ

    entry = PlaylistEntry(title="晴天", artist="周杰伦", origin_platform="netease")
    _bind_import_choices(library, [MatchRow(entry=entry, status="matched", track=track)])

    state = service.state(track.id)
    assert state.selection_mode == "manual"
    assert library.tracks.get(track.id).source_id == QQ.id


def test_import_300_online_rows_binds_all(library):
    from hushplayer.services.playlist_import import PlaylistEntry
    from hushplayer.services.playlist_matcher import MatchRow, _bind_import_choices

    service = _service(library)
    library.source_bindings = service
    rows = []
    for index in range(300):
        track = Track(
            id=f"bulk-{index}",
            kind="online",
            source_id=QQ.id,
            source_name="QQ音乐",
            remote_id=f"qq-{index}",
            title=f"歌曲 {index}",
            artist="测试歌手",
            album="批量专辑",
            duration_ms=180000,
        )
        library.tracks.upsert(track)
        rows.append(
            MatchRow(
                entry=PlaylistEntry(
                    title=track.title, artist="测试歌手",
                    origin_platform="qq", origin_remote_id=track.remote_id,
                ),
                status="matched",
                track=track,
            )
        )

    _bind_import_choices(library, rows)

    bound = library.db.connection().execute(
        "SELECT COUNT(*) FROM track_source_binding_state"
    ).fetchone()[0]
    assert bound == 300
    pending = library.db.connection().execute(
        "SELECT COUNT(*) FROM track_source_binding_state WHERE verify_state='pending'"
    ).fetchone()[0]
    assert pending == 300


def test_binding_survives_restart(library, tmp_path):
    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    service.manual_choose(track.id, _choice())

    # 「重启」：重新打开同一个库文件，绑定必须仍然生效。
    reopened = FakeLibrary(tmp_path)
    service2 = _service(reopened)
    target = service2.get_target(track.id)
    assert target is not None and target.source_id == QQ.id
    assert service2.state(track.id).manual is True


def test_fallback_playback_adopts_source_after_position(qapp, library, tmp_path):
    from test_cross_source import WY, WY_ITEM, FakeClient

    from hushplayer.audio.controller import PlayerController
    from hushplayer.audio.engine import PlaybackEngine
    from hushplayer.services.binding import BindingChoice

    track = _track()
    library.tracks.upsert(track)
    service = _service(library)
    library.source_bindings = service
    service.import_choice(track.id, BindingChoice.from_track(track))

    client = FakeClient(resolve_failures=3, search_items=[WY_ITEM])

    class _AlwaysPlaying(PlaybackEngine):
        @property
        def state(self) -> str:  # noqa: D401 - test double
            return "playing"

    engine = _AlwaysPlaying()
    controller = PlayerController(engine=engine, client=client, binding=service)
    controller.set_volume(0.0)
    controller._sources = [KG, WY]  # noqa: SLF001
    engine.load = lambda *a, **kw: None  # type: ignore[assignment]
    controller.proxy.register = lambda *a, **kw: "http://127.0.0.1:9/audio/x"  # type: ignore[assignment]

    controller.play_tracks([track], 0, context="test")

    # 回退成功只是「待验证」，播放位置推进后才把来源写进数据库。
    assert library.tracks.get(track.id).source_id == KG.id
    controller._on_position(400)
    assert library.tracks.get(track.id).source_id == KG.id
    controller._on_position(1500)

    updated = library.tracks.get(track.id)
    assert updated.source_id == WY.id
    state = service.state(track.id)
    assert state.verify_state == "verified"
    assert state.selection_mode == "auto"
