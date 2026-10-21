"""音乐库：元数据、导入、搜索、收藏、歌单与文件失效处理。"""

from __future__ import annotations

from hushplayer.model.track import format_duration
from hushplayer.services.library import LibraryQuery


def titles(tracks) -> list[str]:
    return [track.title for track in tracks]


def test_import_reads_metadata(loaded_library) -> None:
    tracks = loaded_library.tracks_page(LibraryQuery(limit=100))
    assert len(tracks) == 8
    by_title = {track.title: track for track in tracks}
    night = by_title["夜航信号"]
    assert night.artist == "Aurora Field"
    assert night.album == "夜航信号"
    assert night.duration_ms == 12000
    assert night.codec in {"mp3", "MPEG 1 Layer 3", "mp3float", "MP3"}
    assert night.kind == "local"
    assert night.available is True
    assert night.artwork_path and "artwork" in night.artwork_path.lower()

    long_name = next(title for title in by_title if title.startswith("一首名字非常非常长"))
    assert by_title[long_name].duration_ms == 15000
    untagged = by_title["无名之歌"]
    assert untagged.artist == "无名歌手"
    assert untagged.album == ""


def test_scan_error_recorded_for_corrupt_file(loaded_library) -> None:
    errors = loaded_library.scan_errors()
    assert errors, "损坏的 mp3 应记录扫描错误"
    messages = " ".join(str(item) for item in errors)
    assert "corrupt" in messages.lower() or "MPEG" in messages


def test_stats_and_dimensions(loaded_library) -> None:
    stats = loaded_library.stats
    assert stats.track_count == 8
    assert stats.album_count == 3
    assert stats.artist_count == 4

    albums = loaded_library.albums()
    names = {album.name for album in albums}
    assert "夜航信号" in names and "Long Way Home" in names
    night_album = next(album for album in albums if album.name == "夜航信号")
    assert night_album.track_count == 3
    assert night_album.artist == "Aurora Field"

    artists = {artist.name: artist for artist in loaded_library.artists()}
    assert artists["Aurora Field"].track_count == 3
    assert artists["林间小径"].album_count == 1


def test_search_local(loaded_library) -> None:
    hits = [track.title for track in loaded_library.search_local("夜航")]
    assert hits[0] == "夜航信号"
    assert set(hits) == {"夜航信号", "Static Bloom", "凌晨四点的海"}  # 同专辑/歌手也会命中
    assert len(loaded_library.search_local("Aurora")) == 3
    assert loaded_library.search_local("不存在的歌曲") == []
    assert [album.name for album in loaded_library.albums(search="Long")] == ["Long Way Home"]


def test_sorting_and_paging(loaded_library) -> None:
    ascending = loaded_library.tracks_page(LibraryQuery(sort="title", descending=False, limit=100))
    descending = loaded_library.tracks_page(LibraryQuery(sort="title", descending=True, limit=100))
    assert titles(ascending)[:3] != titles(descending)[:3]
    page = loaded_library.tracks_page(LibraryQuery(sort="title", limit=3, offset=0))
    next_page = loaded_library.tracks_page(LibraryQuery(sort="title", limit=3, offset=3))
    assert len(page) == 3 and len(next_page) == 3
    assert set(track.id for track in page).isdisjoint(track.id for track in next_page)


def test_favorites(loaded_library) -> None:
    track = loaded_library.search_local("夜航")[0]
    assert loaded_library.is_favorite(track) is False
    loaded_library.toggle_favorite(track)
    assert loaded_library.is_favorite(track) is True
    favorites = loaded_library.favorites()
    assert [item.id for item in favorites] == [track.id]

    playlist_id = loaded_library.favorites_playlist_id()
    assert [item.id for item in loaded_library.playlist_tracks(playlist_id)] == [track.id]

    loaded_library.toggle_favorite(track)
    assert loaded_library.favorites() == []


def test_playlist_crud_and_order(loaded_library) -> None:
    tracks = loaded_library.tracks_page(LibraryQuery(sort="title", limit=100))
    playlist_id = loaded_library.create_playlist("通勤")
    assert isinstance(playlist_id, int)
    assert loaded_library.add_to_playlist(playlist_id, tracks[:4]) == 4
    items = loaded_library.playlist_tracks(playlist_id)
    assert len(items) == 4

    loaded_library.move_playlist_item(playlist_id, 0, 3)
    moved = loaded_library.playlist_tracks(playlist_id)
    assert moved[3].id == items[0].id

    loaded_library.rename_playlist(playlist_id, "深夜通勤")
    assert loaded_library.playlist(playlist_id).name == "深夜通勤"

    loaded_library.remove_from_playlist(playlist_id, [moved[0].id])
    assert len(loaded_library.playlist_tracks(playlist_id)) == 3

    containing = loaded_library.playlists_containing(moved[1].id)
    assert playlist_id in containing

    loaded_library.delete_playlist(playlist_id)
    assert loaded_library.playlist(playlist_id) is None


def test_adding_same_track_twice_does_not_duplicate(loaded_library) -> None:
    tracks = loaded_library.tracks_page(LibraryQuery(sort="title", limit=3))
    playlist_id = loaded_library.create_playlist("去重")
    loaded_library.add_to_playlist(playlist_id, tracks)
    loaded_library.add_to_playlist(playlist_id, tracks)
    assert len(loaded_library.playlist_tracks(playlist_id)) == 3


def test_reimport_updates_instead_of_duplicating(loaded_library, music_dir) -> None:
    before = loaded_library.stats.track_count
    result = loaded_library.import_files([str(path) for path in music_dir.rglob("*.mp3")])
    assert result.added == 0
    assert loaded_library.stats.track_count == before


def test_recording_play_updates_recent(loaded_library) -> None:
    track = loaded_library.search_local("Static Bloom")[0]
    loaded_library.record_play(track)
    recent = loaded_library.recent(10)
    assert recent and recent[0].id == track.id
    assert loaded_library.track(track.id).play_count >= 1


def test_remove_tracks(loaded_library) -> None:
    tracks = loaded_library.tracks_page(LibraryQuery(sort="title", limit=2))
    removed = loaded_library.remove_tracks([track.id for track in tracks])
    assert removed == 2
    assert loaded_library.track(tracks[0].id) is None


def test_format_duration() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(65_000) == "1:05"
    assert format_duration(3_725_000) == "1:02:05"

def test_favourited_online_track_shows_in_albums_and_artists(library):
    """Saved streaming tracks should be browsable, not only listed in 我喜欢."""
    from hushplayer.model.track import Track

    online = Track(
        id="kw:1", title="家书", artist="加木", album="羲和",
        duration_ms=242000, source_id="kw", kind="online",
    )
    library.toggle_favorite(online)

    albums = library.albums()
    artists = library.artists()
    assert any(album.name == "羲和" for album in albums)
    assert any(artist.name == "加木" for artist in artists)

    library.toggle_favorite(online)  # un-favourite
    assert not any(album.name == "羲和" for album in library.albums())


def test_record_play_persists_online_track_for_recent(library):
    from hushplayer.model.track import Track

    online = Track(
        id="kw:2", title="家书（现场）", artist="加木", album="羲和",
        duration_ms=242000, source_id="kw", kind="online",
    )
    library.record_play(online)
    recent = library.recent()
    assert any(track.id == "kw:2" for track in recent)
