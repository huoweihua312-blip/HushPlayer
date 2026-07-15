from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QProcess, QThread, Qt
from PySide6.QtWidgets import QApplication

from app.models.media_item import MediaItem
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore
from app.ui.library_page import LibraryPage
from app.ui.main_window import MainWindow


RESULT_PREFIX = "STARTUP_LIBRARY_RESULT="
BENCHMARK_SIZES = (0, 300, 1000, 5000)
BENCHMARK_RUNS = 3


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def local_song(path: Path, index: int) -> dict:
    return {
        "title": f"启动歌曲 {index:05d}",
        "artist": f"歌手 {index % 37:02d}",
        "album": f"专辑 {index % 83:02d}",
        "path": str(path),
        "added_at": index + 1,
        "duration": 180 + index % 60,
    }


def prepare_storage(
    root: Path,
    song_count: int,
    *,
    remote_count: int = 0,
    include_restore_state: bool = False,
) -> tuple[list[dict], dict[str, dict]]:
    data_dir = root / "appdata" / "data"
    music_dir = root / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    songs = []
    for index in range(song_count):
        path = music_dir / f"track_{index:05d}.mp3"
        path.touch()
        songs.append(local_song(path, index))

    remote_tracks: dict[str, dict] = {}
    for index in range(remote_count):
        matching_local = songs[0] if index == 0 and songs else {}
        track = {
            "sourceId": "startup_fixture",
            "id": f"remote-{index:05d}",
            "title": matching_local.get("title", f"远程歌曲 {index:05d}"),
            "artist": matching_local.get("artist", f"远程歌手 {index % 19:02d}"),
            "album": matching_local.get("album", f"远程专辑 {index % 31:02d}"),
            "duration": 210 + index % 40,
            "raw": {"id": f"remote-{index:05d}"},
        }
        stable_id, record = RemoteTrackStore.build_record(
            track,
            "https://example.invalid/startup-fixture.js",
        )
        remote_tracks[stable_id] = record

    remote_ids = list(remote_tracks)
    liked_songs = [songs[0]["path"]] if songs else []
    liked_remote = remote_ids[:1]
    custom_songs = [songs[1]["path"]] if len(songs) > 1 else []
    custom_remote = remote_ids[1:2]
    playlists = {
        "liked": {
            "name": "我喜欢",
            "songs": liked_songs,
            "remoteSongs": liked_remote,
            "members": [
                *(
                    [{"kind": "local", "id": liked_songs[0], "added_at": 10}]
                    if liked_songs
                    else []
                ),
                *(
                    [{"kind": "remote", "id": liked_remote[0], "added_at": 11}]
                    if liked_remote
                    else []
                ),
            ],
            "membershipVersion": PlaylistMembership.VERSION,
            "fixed": True,
        },
        "startup_custom": {
            "name": "启动测试歌单",
            "songs": custom_songs,
            "remoteSongs": custom_remote,
            "members": [
                *(
                    [{"kind": "local", "id": custom_songs[0], "added_at": 20}]
                    if custom_songs
                    else []
                ),
                *(
                    [{"kind": "remote", "id": custom_remote[0], "added_at": 21}]
                    if custom_remote
                    else []
                ),
            ],
            "membershipVersion": PlaylistMembership.VERSION,
            "fixed": False,
        },
    }
    playback_session = (
        {
            "path": songs[2]["path"],
            "position": 42_000,
            "library_view": "all",
        }
        if include_restore_state and len(songs) > 2
        else {}
    )
    play_queue: list = []
    if include_restore_state and len(songs) > 1:
        play_queue.append(songs[1]["path"])
    if include_restore_state and remote_ids:
        remote_track = RemoteTrackStore.to_online_track(
            remote_ids[0],
            remote_tracks[remote_ids[0]],
        )
        remote_track["sourceName"] = "启动测试来源"
        play_queue.append(
            {
                "kind": "remote",
                "media_item": MediaItem.from_online(remote_track).to_dict(),
            }
        )

    defaults = {
        "ignored_imports.json": [],
        "library.json": songs,
        "pending_imports.json": [],
        "playback_session.json": playback_session,
        "playlists.json": playlists,
        "play_queue.json": play_queue,
        "remote_tracks.json": {"version": 1, "tracks": remote_tracks},
        "settings.json": {
            "library_content_view": "tracks",
            "restore_last_playback": include_restore_state,
        },
        "stats.json": {},
        "lyrics_bindings.json": {},
    }
    for filename, value in defaults.items():
        write_json(data_dir / filename, value)

    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    write_json(cache_dir / "metadata_cache.json", {})
    write_json(
        root / "appdata" / "source_runtime" / "source_registry.json",
        {
            "version": 1,
            "sources": (
                [
                    {
                        "id": "startup_fixture",
                        "name": "启动测试来源",
                        "enabled": True,
                        "sourceUrl": "https://example.invalid/startup-fixture.js",
                        "capabilities": {"search": True, "playback": True},
                    }
                ]
                if remote_tracks
                else []
            ),
        },
    )
    return songs, remote_tracks


def install_storage_environment(root: Path) -> dict[str, str | None]:
    names = (
        "HUSHPLAYER_APP_DATA_DIR",
        "HUSHPLAYER_CACHE_DIR",
        "HUSHPLAYER_LOG_DIR",
    )
    previous = {name: os.environ.get(name) for name in names}
    os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
    os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
    os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
    return previous


def restore_storage_environment(previous: dict[str, str | None]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def benchmark_once(app: QApplication, root: Path, song_count: int) -> dict:
    songs, _remote_tracks = prepare_storage(root, song_count)
    previous_env = install_storage_environment(root)
    counts = {
        "load": 0,
        "sync": 0,
        "filter": 0,
        "scope": 0,
        "scope_fresh_scan": 0,
        "set_scope": 0,
        "identity_rebuild": 0,
        "remote_item_scan": 0,
        "sort": 0,
        "create_item": 0,
        "dict_conversion": 0,
        "library_reads": 0,
    }
    timings = {
        "load_ms": 0.0,
        "sync_ms": 0.0,
        "filter_ms": 0.0,
        "scope_ms": 0.0,
    }
    originals = {
        "load": MainWindow.load_music_library,
        "sync": MainWindow.sync_remote_song_items,
        "filter": MainWindow.filter_song_list,
        "scope": MainWindow.update_library_page_scope,
        "set_scope": LibraryPage.set_scope,
        "identity_rebuild": MainWindow.rebuild_song_identity_index,
        "sort": MainWindow.sort_song_list_for_current_view,
        "create_item": MainWindow.create_song_list_item,
        "dict_conversion": MainWindow.media_item_from_song_data,
        "path_open": Path.open,
    }
    if hasattr(MainWindow, "collect_remote_song_items"):
        originals["remote_item_scan"] = MainWindow.collect_remote_song_items

    def timed_wrapper(name: str, timing_name: str):
        original = originals[name]

        def wrapped(self, *args, **kwargs):
            counts[name] += 1
            started_at = time.perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                timings[timing_name] += (time.perf_counter() - started_at) * 1000

        return wrapped

    def counted_wrapper(name: str):
        original = originals[name]

        def wrapped(self, *args, **kwargs):
            counts[name] += 1
            return original(self, *args, **kwargs)

        return wrapped

    def counted_scope(self, *args, **kwargs):
        counts["scope"] += 1
        visible_song_data = (
            args[0]
            if args
            else kwargs.get("visible_song_data")
        )
        if visible_song_data is None:
            counts["scope_fresh_scan"] += 1
        started_at = time.perf_counter()
        try:
            return originals["scope"](self, *args, **kwargs)
        finally:
            timings["scope_ms"] += (time.perf_counter() - started_at) * 1000

    library_path = (root / "appdata" / "data" / "library.json").resolve()

    def counted_path_open(path_self: Path, *args, **kwargs):
        mode = str(args[0] if args else kwargs.get("mode", "r"))
        try:
            is_library_read = path_self.resolve() == library_path and "r" in mode
        except OSError:
            is_library_read = False
        if is_library_read:
            counts["library_reads"] += 1
        return originals["path_open"](path_self, *args, **kwargs)

    MainWindow.load_music_library = timed_wrapper("load", "load_ms")
    MainWindow.sync_remote_song_items = timed_wrapper("sync", "sync_ms")
    MainWindow.filter_song_list = timed_wrapper("filter", "filter_ms")
    MainWindow.update_library_page_scope = counted_scope
    LibraryPage.set_scope = counted_wrapper("set_scope")
    MainWindow.rebuild_song_identity_index = counted_wrapper("identity_rebuild")
    MainWindow.sort_song_list_for_current_view = counted_wrapper("sort")
    MainWindow.create_song_list_item = counted_wrapper("create_item")
    MainWindow.media_item_from_song_data = counted_wrapper("dict_conversion")
    if "remote_item_scan" in originals:
        MainWindow.collect_remote_song_items = counted_wrapper("remote_item_scan")
    Path.open = counted_path_open

    window = None
    construct_ms = 0.0
    first_paint_ms = 0.0
    final_count = -1
    running_threads = -1
    running_processes = -1
    visible_windows_after_close = -1
    try:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            started_at = time.perf_counter()
            window = MainWindow()
            construct_ms = (time.perf_counter() - started_at) * 1000
            final_count = window.song_list.count()
            show_started_at = time.perf_counter()
            window.show()
            app.processEvents()
            first_paint_ms = (time.perf_counter() - show_started_at) * 1000
        assert final_count == len(songs)
        assert counts["library_reads"] == 1
        assert counts["create_item"] == song_count
    finally:
        MainWindow.load_music_library = originals["load"]
        MainWindow.sync_remote_song_items = originals["sync"]
        MainWindow.filter_song_list = originals["filter"]
        MainWindow.update_library_page_scope = originals["scope"]
        LibraryPage.set_scope = originals["set_scope"]
        MainWindow.rebuild_song_identity_index = originals["identity_rebuild"]
        MainWindow.sort_song_list_for_current_view = originals["sort"]
        MainWindow.create_song_list_item = originals["create_item"]
        MainWindow.media_item_from_song_data = originals["dict_conversion"]
        if "remote_item_scan" in originals:
            MainWindow.collect_remote_song_items = originals["remote_item_scan"]
        Path.open = originals["path_open"]
        if window is not None:
            running_threads = sum(
                1 for thread in window.findChildren(QThread) if thread.isRunning()
            )
            running_processes = sum(
                1
                for process in window.findChildren(QProcess)
                if process.state() != QProcess.ProcessState.NotRunning
            )
            window.close()
            window.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(
                None,
                QEvent.Type.DeferredDelete,
            )
            app.processEvents()
            visible_windows_after_close = sum(
                1 for widget in app.topLevelWidgets() if widget.isVisible()
            )
        restore_storage_environment(previous_env)

    return {
        "songs": song_count,
        "construct_ms": construct_ms,
        "load_ms": timings["load_ms"],
        "sync_ms": timings["sync_ms"],
        "filter_ms": timings["filter_ms"],
        "scope_ms": timings["scope_ms"],
        "first_paint_ms": first_paint_ms,
        "final_count": final_count,
        "running_threads": running_threads,
        "running_processes": running_processes,
        "visible_windows_after_close": visible_windows_after_close,
        "counts": counts,
    }


class FixtureRegistry:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def list_sources(self) -> list[dict]:
        return [
            {
                "id": "startup_fixture",
                "name": "启动测试来源",
                "enabled": self.enabled,
                "sourceUrl": "https://example.invalid/startup-fixture.js",
                "capabilities": {"search": True, "playback": True},
            }
        ]

    def get_source(self, source_id: str) -> dict | None:
        if source_id != "startup_fixture":
            return None
        return dict(self.list_sources()[0])


def close_window(app: QApplication, window: MainWindow | None) -> None:
    if window is None:
        return
    window.media_player.stop()
    window.online_source_client.stop()
    window.close()
    window.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def visible_song_data(window: MainWindow) -> list[dict]:
    values = []
    for row in range(window.song_list.count()):
        item = window.song_list.item(row)
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if item is not None and not item.isHidden() and isinstance(data, dict):
            values.append(data)
    return values


def construct_counted_window() -> tuple[MainWindow, dict[str, int]]:
    counts = {
        "load": 0,
        "sync": 0,
        "filter": 0,
        "scope": 0,
        "set_scope": 0,
        "identity_rebuild": 0,
        "remote_item_scan": 0,
        "sort": 0,
        "create_item": 0,
    }
    originals = {
        "load": MainWindow.load_music_library,
        "sync": MainWindow.sync_remote_song_items,
        "filter": MainWindow.filter_song_list,
        "scope": MainWindow.update_library_page_scope,
        "set_scope": LibraryPage.set_scope,
        "identity_rebuild": MainWindow.rebuild_song_identity_index,
        "remote_item_scan": MainWindow.collect_remote_song_items,
        "sort": MainWindow.sort_song_list_for_current_view,
        "create_item": MainWindow.create_song_list_item,
    }

    def counted(name: str):
        original = originals[name]

        def wrapped(self, *args, **kwargs):
            counts[name] += 1
            return original(self, *args, **kwargs)

        return wrapped

    MainWindow.load_music_library = counted("load")
    MainWindow.sync_remote_song_items = counted("sync")
    MainWindow.filter_song_list = counted("filter")
    MainWindow.update_library_page_scope = counted("scope")
    LibraryPage.set_scope = counted("set_scope")
    MainWindow.rebuild_song_identity_index = counted("identity_rebuild")
    MainWindow.collect_remote_song_items = counted("remote_item_scan")
    MainWindow.sort_song_list_for_current_view = counted("sort")
    MainWindow.create_song_list_item = counted("create_item")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return MainWindow(), counts
    finally:
        MainWindow.load_music_library = originals["load"]
        MainWindow.sync_remote_song_items = originals["sync"]
        MainWindow.filter_song_list = originals["filter"]
        MainWindow.update_library_page_scope = originals["scope"]
        LibraryPage.set_scope = originals["set_scope"]
        MainWindow.rebuild_song_identity_index = originals["identity_rebuild"]
        MainWindow.collect_remote_song_items = originals["remote_item_scan"]
        MainWindow.sort_song_list_for_current_view = originals["sort"]
        MainWindow.create_song_list_item = originals["create_item"]


def test_empty_library(app: QApplication) -> None:
    window = None
    with tempfile.TemporaryDirectory(prefix="hushplayer_startup_empty_") as temp_dir:
        root = Path(temp_dir)
        prepare_storage(root, 0)
        previous_env = install_storage_environment(root)
        try:
            window, counts = construct_counted_window()
            assert window.song_list.count() == 0
            assert window.song_list.isHidden()
            assert not window.song_list_empty_hint.isHidden()
            assert window.library_page._scope_tracks == []
            assert counts == {
                "load": 1,
                "sync": 1,
                "filter": 1,
                "scope": 1,
                "set_scope": 1,
                "identity_rebuild": 0,
                "remote_item_scan": 0,
                "sort": 0,
                "create_item": 0,
            }
        finally:
            close_window(app, window)
            restore_storage_environment(previous_env)


def test_missing_local_library_entry(app: QApplication) -> None:
    window = None
    with tempfile.TemporaryDirectory(prefix="hushplayer_startup_missing_") as temp_dir:
        root = Path(temp_dir)
        prepare_storage(root, 0)
        missing_song = local_song(root / "music" / "missing.mp3", 0)
        library_path = root / "appdata" / "data" / "library.json"
        write_json(library_path, [missing_song])
        previous_env = install_storage_environment(root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                window = MainWindow()
            assert window.song_list.count() == 0
            assert window.song_list.isHidden()
            assert json.loads(library_path.read_text(encoding="utf-8")) == [
                missing_song
            ]
        finally:
            close_window(app, window)
            restore_storage_environment(previous_env)


def test_remote_startup_and_state(app: QApplication, remote_count: int) -> None:
    window = None
    with tempfile.TemporaryDirectory(
        prefix=f"hushplayer_startup_remote_{remote_count}_"
    ) as temp_dir:
        root = Path(temp_dir)
        songs, remote_tracks = prepare_storage(
            root,
            12,
            remote_count=remote_count,
            include_restore_state=True,
        )
        remote_ids = list(remote_tracks)
        previous_env = install_storage_environment(root)
        try:
            window, counts = construct_counted_window()
            assert window.song_list.count() == len(songs) + remote_count
            assert counts == {
                "load": 1,
                "sync": 1,
                "filter": 1,
                "scope": 1,
                "set_scope": 1,
                "identity_rebuild": 0,
                "remote_item_scan": 0,
                "sort": 0,
                "create_item": len(songs) + remote_count,
            }
            assert window.library_data_revision == (1 if remote_count else 0)
            assert not window.library_list_dirty
            # Remote records stay in the master list but the existing "all"
            # view intentionally shows local library entries only.
            assert len(window.library_page._scope_tracks) == len(songs)
            assert window.song_list.currentRow() == 0
            assert window.song_list.currentItem() is not None

            if not remote_ids:
                return

            local_identity = MediaItem.from_local(songs[0]).stable_identity
            remote_data = RemoteTrackStore.to_song_data(
                remote_ids[0],
                remote_tracks[remote_ids[0]],
                source_available=True,
            )
            remote_identity = window.track_identity_for_song_data(remote_data)
            assert local_identity != remote_identity
            assert window.find_song_item_by_identity(local_identity) is not None
            assert window.find_song_item_by_identity(remote_identity) is not None

            assert len(window.play_queue) == 2
            assert [item.kind for item in window.play_queue] == ["local", "remote"]
            window.restore_playback_session()
            assert window.pending_lazy_restore_song_data is not None
            assert window.normalize_song_path(
                window.pending_lazy_restore_song_data["path"]
            ) == window.normalize_song_path(songs[2]["path"])
            assert window.pending_restore_position == 42_000

            window.set_library_view("liked")
            assert len(visible_song_data(window)) == 2
            window.set_library_view("playlist:startup_custom")
            assert len(visible_song_data(window)) == 2
            window.set_library_view("all")
            assert len(visible_song_data(window)) == len(songs)

            playing_item = window.find_song_item_by_identity(local_identity)
            selected_identity = MediaItem.from_local(songs[-1]).stable_identity
            selected_item = window.find_song_item_by_identity(selected_identity)
            assert playing_item is not None and selected_item is not None
            window.current_media_item = MediaItem.from_local(songs[0])
            window.current_song_path = songs[0]["path"]
            window.refresh_playing_song_indicators()
            assert playing_item.text().startswith("▶ ")
            window.song_list.clearSelection()
            window.song_list.setCurrentItem(selected_item)
            selected_item.setSelected(True)
            window.sort_library_by_column("title")
            selected_after_sort = {
                window.track_identity_for_song_data(
                    item.data(Qt.ItemDataRole.UserRole)
                )
                for item in window.song_list.selectedItems()
            }
            assert selected_identity in selected_after_sort
            playing_after_sort = window.find_song_item_by_identity(local_identity)
            assert playing_after_sort is not None
            assert playing_after_sort.text().startswith("▶ ")

            revision_before_source_change = window.library_data_revision
            window.source_registry_manager = FixtureRegistry(enabled=False)
            window._source_registry_snapshot = None
            window._source_registry_snapshot_manager_id = 0
            window.sync_remote_song_items()
            assert window.library_data_revision == revision_before_source_change + 1
            assert window.library_list_dirty
            remote_after_source_change = window.find_song_item_by_identity(
                remote_identity
            )
            assert remote_after_source_change is not None
            assert (
                remote_after_source_change.data(Qt.ItemDataRole.UserRole)["onlineStatus"]
                == "来源不可用"
            )

            revision_before_removal = window.library_data_revision
            window.remote_tracks = {}
            window.remote_tracks_error = ""
            window.sync_remote_song_items()
            assert window.song_list.count() == len(songs)
            assert window.library_data_revision == revision_before_removal + 1
            assert window.find_song_item_by_identity(remote_identity) is None

            scan_calls = 0
            rebuild_calls = 0
            original_collect = window.collect_remote_song_items
            original_rebuild = window.rebuild_song_identity_index

            def counted_collect():
                nonlocal scan_calls
                scan_calls += 1
                return original_collect()

            def counted_rebuild():
                nonlocal rebuild_calls
                rebuild_calls += 1
                return original_rebuild()

            window.collect_remote_song_items = counted_collect
            window.rebuild_song_identity_index = counted_rebuild
            window.remote_tracks_error = "远程记录损坏"
            window.sync_remote_song_items(song_list_is_local_only=True)
            assert scan_calls == 1
            assert rebuild_calls == 1
        finally:
            close_window(app, window)
            restore_storage_environment(previous_env)


def run_correctness_tests(app: QApplication) -> None:
    test_empty_library(app)
    test_missing_local_library_entry(app)
    test_remote_startup_and_state(app, 3)
    test_remote_startup_and_state(app, 300)
    print("startup library correctness: OK")


def run_benchmark_child(song_count: int) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(
        prefix=f"hushplayer_startup_{song_count}_"
    ) as temp_dir:
        result = benchmark_once(app, Path(temp_dir), song_count)
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def run_isolated_benchmarks() -> dict[int, dict]:
    results: dict[int, dict] = {}
    for song_count in BENCHMARK_SIZES:
        samples = []
        for _ in range(BENCHMARK_RUNS):
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--benchmark-case",
                    str(song_count),
                ],
                cwd=PROJECT_ROOT,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            marker = next(
                line
                for line in completed.stdout.splitlines()
                if line.startswith(RESULT_PREFIX)
            )
            samples.append(json.loads(marker[len(RESULT_PREFIX):]))
        summary = {
            key: statistics.median(sample[key] for sample in samples)
            for key in (
                "construct_ms",
                "load_ms",
                "sync_ms",
                "filter_ms",
                "scope_ms",
                "first_paint_ms",
            )
        }
        summary["counts"] = samples[0]["counts"]
        summary["final_count"] = samples[0]["final_count"]
        summary["running_threads"] = max(
            sample["running_threads"] for sample in samples
        )
        summary["running_processes"] = max(
            sample["running_processes"] for sample in samples
        )
        summary["visible_windows_after_close"] = max(
            sample["visible_windows_after_close"] for sample in samples
        )
        results[song_count] = summary
        print(
            "startup library benchmark: "
            f"songs={song_count} construct={summary['construct_ms']:.1f} ms "
            f"load={summary['load_ms']:.1f} ms sync={summary['sync_ms']:.1f} ms "
            f"filter={summary['filter_ms']:.1f} ms scope={summary['scope_ms']:.1f} ms "
            f"paint={summary['first_paint_ms']:.1f} ms counts={summary['counts']}"
        )
    return results


def assert_benchmark_results(results: dict[int, dict]) -> None:
    construct_limits = {0: 500, 300: 1500, 1000: 3000, 5000: 12000}
    for song_count, result in results.items():
        counts = result["counts"]
        assert counts == {
            "create_item": song_count,
            "dict_conversion": song_count,
            "filter": 1,
            "identity_rebuild": 0,
            "library_reads": 1,
            "load": 1,
            "remote_item_scan": 0,
            "scope": 1,
            "scope_fresh_scan": 0,
            "set_scope": 1,
            "sort": 0,
            "sync": 1,
        }
        assert result["final_count"] == song_count
        assert result["construct_ms"] < construct_limits[song_count]
        assert result["sync_ms"] < 10
        assert result["first_paint_ms"] < 250
        assert result["running_threads"] == 0
        assert result["running_processes"] == 0
        assert result["visible_windows_after_close"] == 0
    assert [
        results[song_count]["construct_ms"] for song_count in BENCHMARK_SIZES
    ] == sorted(
        results[song_count]["construct_ms"] for song_count in BENCHMARK_SIZES
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-case", type=int)
    parser.add_argument("--benchmark-suite", action="store_true")
    args = parser.parse_args()
    if args.benchmark_case is not None:
        return run_benchmark_child(args.benchmark_case)
    if args.benchmark_suite:
        results = run_isolated_benchmarks()
        assert_benchmark_results(results)
        return 0
    app = QApplication.instance() or QApplication(sys.argv)
    run_correctness_tests(app)
    results = run_isolated_benchmarks()
    assert_benchmark_results(results)
    print("startup library performance smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
