from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


ISOLATED_STORAGE = activate_isolated_app_storage("hushplayer-liked-rows-sidebar-")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore
from app.ui.main_window import (
    SIDEBAR_NAVIGATION_DEFAULT_ORDER,
    MainWindow,
    SettingsDialog,
    merge_sidebar_navigation_order,
)


def local_song(path: Path, index: int) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return {
        "title": f"本地歌曲 {index}",
        "artist": "测试歌手",
        "album": "测试专辑",
        "path": str(path),
        "added_at": index,
        "demo": False,
    }


def visible_identities(window: MainWindow) -> list[str]:
    result: list[str] = []
    for row in range(window.song_list.count()):
        item = window.song_list.item(row)
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if item is not None and not item.isHidden() and isinstance(value, dict):
            result.append(window.track_identity_for_song_data(value))
    return result


def reset_membership(window: MainWindow) -> None:
    window.playlists = {
        "liked": {
            "name": "我喜欢",
            "songs": [],
            "remoteSongs": [],
            "members": [],
            "membershipVersion": PlaylistMembership.VERSION,
            "fixed": True,
        }
    }
    window.invalidate_playlist_membership_snapshot()
    assert window.save_playlists()


def click_heart(app: QApplication, list_widget, item) -> None:
    list_widget.scrollToItem(item)
    app.processEvents()
    center = list_widget.like_rect_for_item(item).center().toPoint()
    QTest.mouseClick(
        list_widget.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        center,
    )
    app.processEvents()


def run_feature_test(app: QApplication) -> None:
    window = MainWindow()
    window.show()
    app.processEvents()
    reset_membership(window)

    music_root = ISOLATED_STORAGE.root / "music"
    songs = [
        local_song(music_root / "one.mp3", 1),
        local_song(music_root / "two.mp3", 2),
        local_song(music_root / "three.mp3", 3),
    ]
    window.rebuild_song_list_from_data(songs)
    window.current_library_view = "all"
    window.filter_song_list("")
    window.search_page.set_local_results("本地", songs)
    window.library_page.artist_view.detail_tracks.set_items(songs)
    app.processEvents()

    first_item = window.song_list.item(0)
    first_data = first_item.data(Qt.ItemDataRole.UserRole)
    first_identity = MediaItem.from_mapping(first_data).stable_identity
    assert not window.is_media_item_liked(first_data)
    assert not window.song_list.is_value_liked(first_data)

    clicked_rows: list[object] = []
    played_rows: list[object] = []
    window.song_list.itemClicked.connect(clicked_rows.append)
    window.song_list.itemDoubleClicked.connect(played_rows.append)
    selected_before = window.song_list.currentItem()
    order_before = [
        window.track_identity_for_song_data(
            window.song_list.item(row).data(Qt.ItemDataRole.UserRole)
        )
        for row in range(window.song_list.count())
    ]
    row_count_before = window.song_list.count()
    rebuild_calls = 0
    create_calls = 0
    save_calls = 0
    normalize_calls = 0
    original_rebuild = window.rebuild_song_list_from_data
    original_create = window.create_song_list_item
    original_save = window.save_playlists
    original_normalize = PlaylistMembership.normalize_playlist.__func__

    def counted_rebuild(values):
        nonlocal rebuild_calls
        rebuild_calls += 1
        return original_rebuild(values)

    def counted_create(value):
        nonlocal create_calls
        create_calls += 1
        return original_create(value)

    def counted_save():
        nonlocal save_calls
        save_calls += 1
        return original_save()

    def counted_normalize(cls, *args, **kwargs):
        nonlocal normalize_calls
        normalize_calls += 1
        return original_normalize(cls, *args, **kwargs)

    window.rebuild_song_list_from_data = counted_rebuild
    window.create_song_list_item = counted_create
    window.save_playlists = counted_save
    PlaylistMembership.normalize_playlist = classmethod(counted_normalize)
    try:
        click_heart(app, window.song_list, first_item)
        assert window.is_media_item_liked(first_data)
        assert window.song_list.is_value_liked(first_data)
        assert window.search_page.local_view.list_widget.is_value_liked(first_data)
        assert (
            window.library_page.artist_view.detail_tracks.list_widget.is_value_liked(
                first_data
            )
        )
        assert clicked_rows == []
        assert played_rows == []
        assert window.song_list.currentItem() is selected_before
        assert window.song_list.count() == row_count_before
        assert order_before == [
            window.track_identity_for_song_data(
                window.song_list.item(row).data(Qt.ItemDataRole.UserRole)
            )
            for row in range(window.song_list.count())
        ]
        assert rebuild_calls == 0
        assert create_calls == 0
        assert save_calls == 1
        assert normalize_calls == 0

        click_heart(app, window.song_list, first_item)
        assert not window.is_media_item_liked(first_data)
        assert not window.song_list.is_value_liked(first_data)
        assert rebuild_calls == 0
        assert create_calls == 0
        assert save_calls == 2
        assert normalize_calls == 0

        remote = {
            "media_type": "online",
            "sourceId": "fixture_source",
            "sourceName": "测试来源",
            "sourceUrl": "https://example.invalid/source.js",
            "id": "remote-track-1",
            "title": "在线歌曲",
            "artist": "在线歌手",
            "album": "在线专辑",
            "duration": 180,
            "capabilities": {"playback": True, "download": False},
            "availability": "available",
            "raw": {"id": "remote-track-1"},
        }
        window.unified_search_panel.set_results(
            "在线",
            [remote],
            {
                "final": True,
                "resultCount": 1,
                "sources": [
                    {
                        "sourceId": "fixture_source",
                        "sourceName": "测试来源",
                        "status": "success",
                        "resultCount": 1,
                    }
                ],
            },
        )
        remote_item = next(
            window.unified_search_panel.result_list.item(row)
            for row in range(window.unified_search_panel.result_list.count())
            if isinstance(
                window.unified_search_panel.result_list.item(row).data(
                    Qt.ItemDataRole.UserRole
                ),
                dict,
            )
        )
        remote_value = remote_item.data(Qt.ItemDataRole.UserRole)
        remote_identity = MediaItem.from_mapping(remote_value).stable_identity
        emitted: list[tuple[str, bool]] = []
        window.liked_state_changed.connect(
            lambda identity, liked: emitted.append((identity, liked))
        )
        click_heart(app, window.unified_search_panel.result_list, remote_item)
        stable_id = RemoteTrackStore.stable_id_for_track(remote)
        assert stable_id in window.get_playlist_remote_ids("liked")
        assert window.unified_search_panel.result_list.is_value_liked(remote_value)
        assert (remote_identity, True) in emitted
        assert rebuild_calls == 0
        assert save_calls == 3
        assert normalize_calls == 0

        window.set_media_item_liked(songs[0], True)
        window.set_media_item_liked(songs[1], True)
        assert save_calls == 5
        window.set_library_view("liked")
        app.processEvents()
        liked_before = visible_identities(window)
        target_item = window.find_song_item_by_identity(
            MediaItem.from_mapping(songs[1]).stable_identity
        )
        assert target_item is not None and not target_item.isHidden()
        scroll_before = window.song_list.verticalScrollBar().value()
        playback_context = {"fixture": True}
        window.playback_context = playback_context
        window.current_song_path = songs[1]["path"]
        click_heart(app, window.song_list, target_item)
        liked_after = visible_identities(window)
        assert liked_after == [
            identity for identity in liked_before if identity != MediaItem.from_mapping(songs[1]).stable_identity
        ]
        assert window.song_list.count() >= row_count_before
        assert window.song_list.verticalScrollBar().value() == scroll_before
        assert window.current_song_path == songs[1]["path"]
        assert window.playback_context is playback_context
        assert rebuild_calls == 0
        assert normalize_calls == 0

        # Leave one local and one online favorite persisted for restart checks.
        assert window.is_media_item_liked(songs[0])
        assert window.is_media_item_liked(remote)
        assert json.loads(window.playlists_file.read_text(encoding="utf-8"))[
            "liked"
        ]["members"]
    finally:
        PlaylistMembership.normalize_playlist = classmethod(original_normalize)
        window.rebuild_song_list_from_data = original_rebuild
        window.create_song_list_item = original_create
        window.save_playlists = original_save

    default_order = list(SIDEBAR_NAVIGATION_DEFAULT_ORDER)
    assert merge_sidebar_navigation_order(None) == default_order
    assert merge_sidebar_navigation_order([]) == default_order
    assert merge_sidebar_navigation_order(["unknown", "liked", "liked", "lyrics"]) == [
        "liked",
        "lyrics",
        *[item_id for item_id in default_order if item_id not in {"liked", "lyrics"}],
    ]
    assert window.sidebar_navigation.ordered_ids() == default_order
    assert window.settings_nav_button not in window.sidebar_navigation.navigation_buttons.values()
    assert window.sidebar_title not in window.sidebar_navigation.navigation_buttons.values()

    settings_dialog = SettingsDialog(window)
    assert settings_dialog.settings_scroll.widget() is settings_dialog.settings_scroll_content
    settings_dialog.deleteLater()
    app.processEvents()

    window.show_liked_playlist_page()
    page_instances = [
        window.content_stack.widget(index)
        for index in range(window.content_stack.count())
    ]
    liked_button = window.liked_playlist_button
    assert liked_button.property("active") is True
    window.sidebar_navigation.begin_navigation_drag(liked_button)
    assert window.sidebar_navigation.drop_indicator.isVisible()
    window.sidebar_navigation._drop_index = len(default_order) - 1
    window.sidebar_navigation.finish_navigation_drag(liked_button)
    assert window.sidebar_navigation.ordered_ids()[-1] == "liked"
    assert liked_button.property("active") is True
    assert page_instances == [
        window.content_stack.widget(index)
        for index in range(window.content_stack.count())
    ]
    saved_settings = json.loads(window.settings_file.read_text(encoding="utf-8"))
    assert saved_settings["sidebar_navigation_order"][-1] == "liked"

    window.search_nav_button.click()
    app.processEvents()
    assert window.content_stack.currentWidget() is window.search_page
    window.artists_nav_button.click()
    app.processEvents()
    assert window.content_stack.currentWidget() is window.library_page
    assert window.library_page.current_mode == "artists"
    assert window.artists_nav_button.property("active") is True

    window.close()
    window.deleteLater()
    app.processEvents()

    restarted = MainWindow()
    try:
        assert restarted.is_media_item_liked(songs[0])
        assert restarted.is_media_item_liked(remote)
        assert restarted.sidebar_navigation.ordered_ids()[-1] == "liked"
        assert len(restarted.sidebar_navigation.navigation_buttons) == len(default_order)
        settings_path = restarted.settings_file
    finally:
        restarted.close()
        restarted.deleteLater()
        app.processEvents()

    settings_path.write_text(
        json.dumps(
            {
                "volume": 65,
                "play_mode": "list_loop",
                "auto_scan_music_folders_on_startup": False,
                "sidebar_navigation_order": [
                    "unknown",
                    "liked",
                    "liked",
                    "lyrics",
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    compatible = MainWindow()
    try:
        assert compatible.sidebar_navigation.ordered_ids() == [
            "liked",
            "lyrics",
            *[
                item_id
                for item_id in default_order
                if item_id not in {"liked", "lyrics"}
            ],
        ]
    finally:
        compatible.close()
        compatible.deleteLater()
        app.processEvents()

    settings_path.write_text("{broken", encoding="utf-8")
    damaged = MainWindow()
    try:
        assert damaged.sidebar_navigation.ordered_ids() == default_order
    finally:
        damaged.close()
        damaged.deleteLater()
        app.processEvents()


def main() -> int:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        run_feature_test(app)
        print("liked rows and sidebar order smoke: OK")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
