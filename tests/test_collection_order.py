"""新增歌曲必须待在「我喜欢」和歌单的最上面。

用户反馈（1.3.24）：把歌曲加到「我喜欢」或某个歌单后，它应该出现在第一行，
而不是被按标题排序或追加到末尾。
"""

from __future__ import annotations

from hushplayer.services.library import LibraryQuery


def _first_tracks(library, count: int):
    tracks = library.tracks_page(LibraryQuery(sort="title", limit=count))
    assert len(tracks) == count
    return tracks


def test_favorites_are_newest_first(loaded_library):
    library = loaded_library
    first, second = _first_tracks(library, 2)

    library.toggle_favorite(first)
    library.toggle_favorite(second)

    favorites = library.favorites()
    assert [track.id for track in favorites[:2]] == [second.id, first.id]


def test_refavoriting_moves_track_back_to_top(loaded_library):
    library = loaded_library
    first, second = _first_tracks(library, 2)

    library.toggle_favorite(first)
    library.toggle_favorite(second)
    assert library.favorites()[0].id == second.id

    # 取消再收藏第一首：它应该重新回到最上面。
    library.toggle_favorite(first)
    library.toggle_favorite(first)

    assert library.favorites()[0].id == first.id


def test_favorites_page_keeps_storage_order(loaded_library):
    """页面默认不再按标题排序，否则新收藏的歌曲会被排到中间。"""

    from hushplayer.ui.pages.collection import FavoritesPage, RecentPage
    from hushplayer.ui.pages.songs import SongsPage
    from hushplayer.ui.pages.trackpage import TrackListPage

    assert TrackListPage.default_sort == ""
    assert FavoritesPage.default_sort == ""
    assert RecentPage.default_sort == ""
    assert SongsPage.default_sort == "title"


def test_new_playlist_tracks_go_to_the_top(loaded_library):
    library = loaded_library
    tracks = _first_tracks(library, 3)
    playlist_id = library.create_playlist("置顶测试")

    library.add_to_playlist(playlist_id, tracks[:2])
    assert [track.id for track in library.playlist_tracks(playlist_id)] == [
        tracks[0].id,
        tracks[1].id,
    ]

    library.add_to_playlist(playlist_id, [tracks[2]])
    assert [track.id for track in library.playlist_tracks(playlist_id)] == [
        tracks[2].id,
        tracks[0].id,
        tracks[1].id,
    ]


def test_duplicate_playlist_add_does_not_reorder(loaded_library):
    library = loaded_library
    tracks = _first_tracks(library, 2)
    playlist_id = library.create_playlist("去重测试")

    library.add_to_playlist(playlist_id, tracks)
    before = [track.id for track in library.playlist_tracks(playlist_id)]

    assert library.add_to_playlist(playlist_id, [tracks[0], tracks[0]]) == 0
    assert [track.id for track in library.playlist_tracks(playlist_id)] == before


def test_favorites_system_playlist_matches_favorites_order(loaded_library):
    library = loaded_library
    first, second = _first_tracks(library, 2)
    library.toggle_favorite(first)
    library.toggle_favorite(second)

    playlist_id = library.favorites_playlist_id()
    assert playlist_id
    playlist_order = [track.id for track in library.playlist_tracks(playlist_id)]
    favorites_order = [track.id for track in library.favorites()]
    assert playlist_order[:2] == favorites_order[:2] == [second.id, first.id]
