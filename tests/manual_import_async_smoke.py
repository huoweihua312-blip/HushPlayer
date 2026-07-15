from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QProcess, QThread, QTimer, Qt, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


RESULT_PREFIX = "MANUAL_IMPORT_ASYNC_RESULT="
TIMEOUT_MS = 15000


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def prepare_isolated_storage(root: Path) -> None:
    data_dir = root / "appdata" / "data"
    defaults = {
        "ignored_imports.json": [],
        "library.json": [],
        "pending_imports.json": [],
        "playback_session.json": {},
        "playlists.json": {},
        "play_queue.json": [],
        "remote_tracks.json": {"version": 1, "tracks": {}},
        "settings.json": {
            "auto_scan_music_folders_on_startup": False,
            "music_scan_import_mode": "pending",
        },
        "stats.json": {},
        "lyrics_bindings.json": {},
    }
    for filename, value in defaults.items():
        write_json(data_dir / filename, value)
    write_json(root / "cache" / "metadata_cache.json", {})
    write_json(
        root / "appdata" / "source_runtime" / "source_registry.json",
        {"version": 1, "sources": []},
    )


def make_audio_files(folder: Path, count: int, *, prefix: str = "track") -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        path = folder / f"{prefix}_{index:05d}.mp3"
        path.write_bytes(b"fixture")
        paths.append(path)
    return paths


def process_events(app: QApplication, duration_ms: int = 0) -> None:
    deadline = time.monotonic() + max(0, duration_ms) / 1000.0
    while True:
        app.processEvents()
        if time.monotonic() >= deadline:
            return
        time.sleep(0.001)


def wait_until(app: QApplication, predicate, timeout_ms: int = TIMEOUT_MS) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return True
        time.sleep(0.001)
    app.processEvents()
    return bool(predicate())


class FakeInfo:
    length = 1.25


class FakeAudio:
    def __init__(self, path: Path, easy: bool) -> None:
        self.info = FakeInfo()
        self.tags = (
            {
                "title": [path.stem],
                "artist": ["测试艺术家"],
                "album": ["测试专辑"],
            }
            if easy and "empty_metadata" not in path.name
            else None
        )


class ControlledMutagen:
    delay_seconds = 0.00025
    thread_ids: list[int] = []
    calls = 0

    @classmethod
    def reset(cls, delay_seconds: float = 0.00025) -> None:
        cls.delay_seconds = float(delay_seconds)
        cls.thread_ids = []
        cls.calls = 0

    def __new__(cls, path, easy=False):
        cls.thread_ids.append(threading.get_ident())
        cls.calls += 1
        path = Path(path)
        if cls.delay_seconds:
            time.sleep(cls.delay_seconds)
        if "broken" in path.name:
            raise ValueError("controlled damaged media")
        if "delete_after_metadata" in path.name:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return FakeAudio(path, bool(easy))


class ThreadCheckedList(list):
    def __init__(self, gui_thread_id: int) -> None:
        super().__init__()
        self.gui_thread_id = gui_thread_id
        self.append_thread_ids: list[int] = []

    def append(self, value) -> None:
        thread_id = threading.get_ident()
        self.append_thread_ids.append(thread_id)
        assert thread_id == self.gui_thread_id
        super().append(value)


class FakeUrl:
    def __init__(self, path: Path) -> None:
        self.path = path

    def toLocalFile(self) -> str:
        return str(self.path)


class FakeMimeData:
    def __init__(self, paths: list[Path]) -> None:
        self._urls = [FakeUrl(path) for path in paths]

    def hasUrls(self) -> bool:
        return bool(self._urls)

    def urls(self) -> list[FakeUrl]:
        return list(self._urls)


class FakeDropEvent:
    def __init__(self, paths: list[Path]) -> None:
        self._mime_data = FakeMimeData(paths)
        self.accepted = False
        self.ignored = False

    def mimeData(self) -> FakeMimeData:
        return self._mime_data

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


def active_thread_count(window) -> int:
    return sum(1 for thread in window.findChildren(QThread) if thread.isRunning())


def active_process_count(window) -> int:
    return sum(
        1
        for process in window.findChildren(QProcess)
        if process.state() != QProcess.ProcessState.NotRunning
    )


def install_window_counters(window, gui_thread_id: int) -> dict:
    counts = {
        "create_item": 0,
        "save": 0,
        "sort": 0,
        "filter": 0,
        "scope": 0,
        "pending_save": 0,
        "pending_refresh": 0,
        "create_threads": [],
        "save_threads": [],
        "sort_threads": [],
        "filter_threads": [],
        "scope_threads": [],
        "pending_save_threads": [],
        "pending_refresh_threads": [],
    }
    original_create = window.create_song_list_item
    original_save = window.save_music_library
    original_sort = window.apply_current_library_sort
    original_filter = window.filter_song_list
    original_scope = window.update_library_page_scope
    original_pending_save = window.save_pending_imports
    original_pending_refresh = window.refresh_pending_imports_list

    def create_item(song_data):
        counts["create_item"] += 1
        counts["create_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_create(song_data)

    def save_library():
        counts["save"] += 1
        counts["save_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_save()

    def apply_sort(refresh_view=True):
        counts["sort"] += 1
        counts["sort_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_sort(refresh_view=refresh_view)

    def filter_list(keyword):
        counts["filter"] += 1
        counts["filter_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_filter(keyword)

    def update_scope(visible_song_data=None):
        counts["scope"] += 1
        counts["scope_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_scope(visible_song_data)

    def save_pending():
        counts["pending_save"] += 1
        counts["pending_save_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_pending_save()

    def refresh_pending():
        counts["pending_refresh"] += 1
        counts["pending_refresh_threads"].append(threading.get_ident())
        assert threading.get_ident() == gui_thread_id
        return original_pending_refresh()

    window.create_song_list_item = create_item
    window.save_music_library = save_library
    window.apply_current_library_sort = apply_sort
    window.filter_song_list = filter_list
    window.update_library_page_scope = update_scope
    window.save_pending_imports = save_pending
    window.refresh_pending_imports_list = refresh_pending
    window.schedule_visible_library_durations = lambda: None
    window.select_song = lambda _item: None
    return counts


def reset_counts(counts: dict) -> None:
    for key, value in counts.items():
        if isinstance(value, list):
            value.clear()
        else:
            counts[key] = 0


def reset_window_library(window, gui_thread_id: int) -> None:
    window.song_list.clear()
    window.song_identity_to_item = {}
    window.pending_imports = ThreadCheckedList(gui_thread_id)
    window.ignored_imports = set()
    window.current_library_view = "all"
    window.library_sort_field = None
    window.library_sort_descending = False
    window.last_music_import_metrics = {}


def run_async_operation(app: QApplication, window, start_operation, counts: dict) -> dict:
    reset_counts(counts)
    heartbeat_times = [time.perf_counter()]
    worker_peak = [0]
    heartbeat = QTimer()
    heartbeat.setInterval(1)

    def beat() -> None:
        heartbeat_times.append(time.perf_counter())
        worker_peak[0] = max(
            worker_peak[0],
            sum(1 for thread in window.music_scan_threads if thread.isRunning()),
        )

    heartbeat.timeout.connect(beat)
    heartbeat.start()
    app.processEvents()
    started_at = time.perf_counter()
    dispatch_started_at = time.perf_counter()
    started = start_operation()
    dispatch_ms = (time.perf_counter() - dispatch_started_at) * 1000
    assert started is not False
    assert wait_until(
        app,
        lambda: (
            not window.music_scan_in_progress
            and not window.has_running_music_scan_threads()
            and not window.music_scan_lifecycle
        ),
    )
    total_ms = (time.perf_counter() - started_at) * 1000
    app.processEvents()
    heartbeat.stop()
    gaps = [
        (current - previous) * 1000
        for previous, current in zip(heartbeat_times, heartbeat_times[1:])
    ]
    metrics = dict(window.last_music_import_metrics)
    metrics.update(
        {
            "dispatch_ms": round(dispatch_ms, 3),
            "total_ms": round(total_ms, 3),
            "heartbeat_count": len(heartbeat_times),
            "heartbeat_max_ms": round(max(gaps) if gaps else total_ms, 3),
            "worker_peak": worker_peak[0],
            "save_count": counts["save"],
            "sort_count": counts["sort"],
            "filter_count": counts["filter"],
            "scope_count": counts["scope"],
            "pending_save_count": counts["pending_save"],
            "pending_refresh_count": counts["pending_refresh"],
            "item_count": counts["create_item"],
        }
    )
    return metrics


def assert_gui_only_counts(counts: dict, gui_thread_id: int) -> None:
    for key in (
        "create_threads",
        "save_threads",
        "sort_threads",
        "filter_threads",
        "scope_threads",
        "pending_save_threads",
        "pending_refresh_threads",
    ):
        assert all(thread_id == gui_thread_id for thread_id in counts[key]), key


def run_test(app: QApplication) -> dict:
    from app.core.app_paths import AppPaths
    import app.ui.main_window as main_window_module
    from app.ui.main_window import MainWindow, MusicFolderScanWorker

    gui_thread_id = threading.get_ident()
    original_mutagen = main_window_module.MutagenFile
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_migrate = AppPaths._migrate_legacy_data_files
    original_message_info = QMessageBox.information
    original_message_warning = QMessageBox.warning
    original_dialog_files = QFileDialog.getOpenFileNames
    original_dialog_folder = QFileDialog.getExistingDirectory
    original_scan_entries = MusicFolderScanWorker.scan_entries
    original_link_check = MusicFolderScanWorker.is_link_or_junction
    original_os_walk = main_window_module.os.walk
    original_shutdown_timeout = MainWindow.MUSIC_SCAN_SHUTDOWN_TIMEOUT_MS
    scan_thread_ids: list[int] = []
    dialog_messages: list[str] = []
    qt_messages: list[str] = []
    window = None
    close_window = None

    def collect_qt_message(_mode, _context, message: str) -> None:
        qt_messages.append(str(message))

    previous_handler = qInstallMessageHandler(collect_qt_message)

    def recorded_scan_entries(worker, result):
        scan_thread_ids.append(threading.get_ident())
        return original_scan_entries(worker, result)

    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    AppPaths._migrate_legacy_data_files = lambda self: None
    QMessageBox.information = lambda _parent, title, message, *args, **kwargs: (
        dialog_messages.append(f"{title}: {message}"),
        QMessageBox.StandardButton.Ok,
    )[1]
    QMessageBox.warning = QMessageBox.information
    MusicFolderScanWorker.scan_entries = recorded_scan_entries
    main_window_module.MutagenFile = ControlledMutagen

    results: dict = {}
    try:
        window = MainWindow()
        window.resize(1000, 700)
        window.show()
        process_events(app, 10)
        counts = install_window_counters(window, gui_thread_id)

        static_source = inspect.getsource(MusicFolderScanWorker)
        for forbidden in (
            "QWidget",
            "QMessageBox",
            "QMediaPlayer",
            "song_list",
            "setParent",
            "repaint",
        ):
            assert forbidden not in static_source

        benchmark_results = []
        for size in (100, 1000):
            reset_window_library(window, gui_thread_id)
            paths = make_audio_files(Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / f"benchmark_{size}", size)
            ControlledMutagen.reset(0.00025)
            before_scan_threads = len(scan_thread_ids)
            metrics = run_async_operation(
                app,
                window,
                lambda folder=paths[0].parent: window.start_manual_music_import(
                    [folder],
                    source="manual_folder",
                ),
                counts,
            )
            assert window.song_list.count() == size
            assert metrics["item_count"] == size
            assert metrics["save_count"] == 1
            assert metrics["sort_count"] == 1
            assert metrics["filter_count"] == 1
            assert metrics["scope_count"] == 1
            assert metrics["worker_peak"] == 1
            assert metrics["heartbeat_count"] >= 3
            assert metrics["heartbeat_max_ms"] < 400.0
            assert metrics["max_batch_ms"] < 100.0
            assert scan_thread_ids[before_scan_threads:] and all(
                thread_id != gui_thread_id for thread_id in scan_thread_ids[before_scan_threads:]
            )
            assert ControlledMutagen.thread_ids and all(
                thread_id != gui_thread_id for thread_id in ControlledMutagen.thread_ids
            )
            assert_gui_only_counts(counts, gui_thread_id)
            assert not window.music_scan_workers
            assert not window.music_scan_threads
            benchmark_results.append({"files": size, **metrics})
        results["benchmarks"] = benchmark_results

        dialog_results = {}
        dialog_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "dialogs"
        for label, file_count in (("single_file", 1), ("multiple_files", 3)):
            reset_window_library(window, gui_thread_id)
            dialog_paths = make_audio_files(
                dialog_root / label,
                file_count,
                prefix=label,
            )
            QFileDialog.getOpenFileNames = lambda *args, paths=dialog_paths, **kwargs: (
                [str(path) for path in paths],
                "",
            )
            dialog_metrics = run_async_operation(
                app,
                window,
                lambda: (window.import_music_files(), True)[1],
                counts,
            )
            assert window.song_list.count() == file_count
            dialog_results[label] = dialog_metrics

        reset_window_library(window, gui_thread_id)
        dialog_folder = dialog_root / "folder"
        dialog_folder_paths = make_audio_files(dialog_folder, 2, prefix="folder")
        QFileDialog.getExistingDirectory = lambda *args, **kwargs: str(dialog_folder)
        folder_dialog_metrics = run_async_operation(
            app,
            window,
            lambda: (window.import_music_folder(), True)[1],
            counts,
        )
        assert window.song_list.count() == len(dialog_folder_paths)
        dialog_results["folder"] = folder_dialog_metrics
        QFileDialog.getOpenFileNames = original_dialog_files
        QFileDialog.getExistingDirectory = original_dialog_folder
        results["file_dialog_entries"] = dialog_results

        reset_window_library(window, gui_thread_id)
        mixed_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "mixed"
        nested = make_audio_files(mixed_root / "nested" / "deep", 3, prefix="nested")
        same_a = mixed_root / "a" / "same_name.mp3"
        same_b = mixed_root / "b" / "same_name.mp3"
        same_a.parent.mkdir(parents=True, exist_ok=True)
        same_b.parent.mkdir(parents=True, exist_ok=True)
        same_a.write_bytes(b"fixture")
        same_b.write_bytes(b"fixture")
        broken = mixed_root / "broken.mp3"
        empty_metadata = mixed_root / "empty_metadata.mp3"
        deleted = mixed_root / "delete_after_metadata.mp3"
        unsupported = mixed_root / "notes.txt"
        for path in (broken, empty_metadata, deleted, unsupported):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        ControlledMutagen.reset()
        mixed_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import(
                [mixed_root, nested[0], same_a, same_a, unsupported],
                source="manual_mixed",
            ),
            counts,
        )
        imported_paths = {
            window.normalize_song_path(window.song_list.item(row).data(Qt.ItemDataRole.UserRole).get("path"))
            for row in range(window.song_list.count())
        }
        assert window.normalize_song_path(same_a) in imported_paths
        assert window.normalize_song_path(same_b) in imported_paths
        assert window.normalize_song_path(deleted) not in imported_paths
        assert mixed_metrics["failed_count"] >= 1
        assert mixed_metrics["duplicate_count"] >= 2
        assert mixed_metrics["skipped_count"] >= 1
        assert window.song_list.count() >= 7
        assert mixed_metrics["save_count"] == 1
        assert_gui_only_counts(counts, gui_thread_id)
        results["mixed_manual"] = mixed_metrics

        reset_window_library(window, gui_thread_id)
        empty_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "empty"
        empty_root.mkdir(parents=True, exist_ok=True)
        empty_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import([empty_root], source="manual_folder"),
            counts,
        )
        assert empty_metrics["scanned_count"] == 0
        assert empty_metrics["save_count"] == 0
        assert window.song_list.count() == 0

        denied_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "denied"
        denied_root.mkdir(parents=True, exist_ok=True)

        def permission_walk(top, *args, **kwargs):
            if Path(top) == denied_root:
                onerror = kwargs.get("onerror")
                if callable(onerror):
                    onerror(PermissionError("controlled permission error"))
                return iter(())
            return original_os_walk(top, *args, **kwargs)

        main_window_module.os.walk = permission_walk
        try:
            permission_metrics = run_async_operation(
                app,
                window,
                lambda: window.start_manual_music_import([denied_root], source="manual_folder"),
                counts,
            )
        finally:
            main_window_module.os.walk = original_os_walk
        assert permission_metrics["failed_count"] == 1
        assert permission_metrics["save_count"] == 0

        loop_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "loop_root"
        normal_path = make_audio_files(loop_root, 1, prefix="normal")[0]
        make_audio_files(loop_root / "loop", 1, prefix="must_not_follow")

        def controlled_link_check(path: Path) -> bool:
            return path.name == "loop" or original_link_check(path)

        MusicFolderScanWorker.is_link_or_junction = staticmethod(controlled_link_check)
        try:
            loop_metrics = run_async_operation(
                app,
                window,
                lambda: window.start_manual_music_import([loop_root], source="manual_folder"),
                counts,
            )
        finally:
            MusicFolderScanWorker.is_link_or_junction = staticmethod(original_link_check)
        assert loop_metrics["scanned_count"] == 1
        assert loop_metrics["added_count"] == 1
        assert window.song_list.count() == 1
        assert window.normalize_song_path(normal_path) == window.normalize_song_path(
            window.song_list.item(0).data(Qt.ItemDataRole.UserRole).get("path")
        )

        reset_window_library(window, gui_thread_id)
        order_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "folder_order"
        order_paths = [
            make_audio_files(order_root, 1, prefix="z_root")[0],
            make_audio_files(order_root / "a_nested", 1, prefix="a_nested")[0],
        ]
        order_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import([order_root], source="manual_folder"),
            counts,
        )
        imported_order = [
            window.normalize_song_path(
                window.song_list.item(row).data(Qt.ItemDataRole.UserRole).get("path")
            )
            for row in range(window.song_list.count())
        ]
        assert imported_order == sorted(
            [window.normalize_song_path(path) for path in order_paths],
            key=str.lower,
        )
        results["filesystem_edges"] = {
            "empty": empty_metrics,
            "permission": permission_metrics,
            "link_pruning": loop_metrics,
            "manual_folder_order": order_metrics,
        }

        reset_window_library(window, gui_thread_id)
        drop_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "drop"
        drop_files = make_audio_files(drop_root / "folder", 4, prefix="drop")
        extra_drop = make_audio_files(drop_root, 1, prefix="single")[0]
        drop_event = FakeDropEvent([drop_root / "folder", extra_drop])
        ControlledMutagen.reset()
        drop_metrics = run_async_operation(
            app,
            window,
            lambda: (window.dropEvent(drop_event), True)[1],
            counts,
        )
        assert drop_event.accepted and not drop_event.ignored
        assert window.song_list.count() == len(drop_files) + 1
        assert drop_metrics["save_count"] == 1
        results["drop"] = drop_metrics

        for label, dropped_paths in (
            ("single_file", [extra_drop]),
            ("multiple_files", drop_files[:2]),
        ):
            reset_window_library(window, gui_thread_id)
            entry_event = FakeDropEvent(dropped_paths)
            entry_metrics = run_async_operation(
                app,
                window,
                lambda event=entry_event: (window.dropEvent(event), True)[1],
                counts,
            )
            assert entry_event.accepted and not entry_event.ignored
            assert window.song_list.count() == len(dropped_paths)
            results[f"drop_{label}"] = entry_metrics

        reset_window_library(window, gui_thread_id)
        drop_event = FakeDropEvent([drop_root / "folder", extra_drop])
        drop_metrics = run_async_operation(
            app,
            window,
            lambda: (window.dropEvent(drop_event), True)[1],
            counts,
        )
        assert window.song_list.count() == len(drop_files) + 1

        duplicate_drop_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import(
                [drop_root / "folder", extra_drop],
                source="drop",
            ),
            counts,
        )
        assert duplicate_drop_metrics["duplicate_count"] == len(drop_files) + 1
        assert duplicate_drop_metrics["item_count"] == 0
        assert duplicate_drop_metrics["save_count"] == 0
        assert duplicate_drop_metrics["sort_count"] == 0
        assert duplicate_drop_metrics["filter_count"] == 0
        assert duplicate_drop_metrics["scope_count"] == 0
        assert window.song_list.count() == len(drop_files) + 1
        results["already_imported"] = duplicate_drop_metrics

        original_get_setting = window.get_user_setting
        auto_root = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "auto"
        auto_files = make_audio_files(auto_root, 6, prefix="auto")
        reset_window_library(window, gui_thread_id)
        window.get_user_setting = lambda name, default=None: (
            "auto" if name == "music_scan_import_mode" else original_get_setting(name, default)
        )
        ControlledMutagen.reset()
        auto_metrics = run_async_operation(
            app,
            window,
            lambda: (window.scan_music_folders(manual=False, folders=[str(auto_root)]), True)[1],
            counts,
        )
        assert window.song_list.count() == len(auto_files)
        assert auto_metrics["added_count"] == len(auto_files)
        assert auto_metrics["save_count"] == 1
        results["auto"] = auto_metrics

        reset_window_library(window, gui_thread_id)
        window.get_user_setting = lambda name, default=None: (
            "pending" if name == "music_scan_import_mode" else original_get_setting(name, default)
        )
        ignored_path = window.normalize_song_path(auto_files[0]).lower()
        window.ignored_imports = {ignored_path}
        ControlledMutagen.reset()
        pending_metrics = run_async_operation(
            app,
            window,
            lambda: (window.scan_music_folders(manual=False, folders=[str(auto_root)]), True)[1],
            counts,
        )
        assert window.song_list.count() == 0
        assert len(window.pending_imports) == len(auto_files) - 1
        assert pending_metrics["pending_count"] == len(auto_files) - 1
        assert pending_metrics["duplicate_count"] == 1
        assert pending_metrics["save_count"] == 0
        assert pending_metrics["sort_count"] == 0
        assert pending_metrics["filter_count"] == 0
        assert pending_metrics["scope_count"] == 0
        assert pending_metrics["pending_save_count"] == 1
        assert pending_metrics["pending_refresh_count"] == 1
        assert window.pending_imports.append_thread_ids and all(
            thread_id == gui_thread_id for thread_id in window.pending_imports.append_thread_ids
        )
        results["pending"] = pending_metrics
        window.get_user_setting = original_get_setting

        reset_window_library(window, gui_thread_id)
        slow_paths = make_audio_files(
            Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "concurrent",
            30,
            prefix="slow",
        )
        ControlledMutagen.reset(0.003)
        assert window.start_manual_music_import(slow_paths, source="manual_files")
        active_task_id = window.active_music_scan_task_id
        assert not window.start_manual_music_import([slow_paths[0]], source="manual_files")
        window.scan_music_folders(manual=False, folders=[str(slow_paths[0].parent)])
        rejected_drop = FakeDropEvent([slow_paths[0]])
        window.dropEvent(rejected_drop)
        assert window.active_music_scan_task_id == active_task_id
        assert wait_until(
            app,
            lambda: not window.music_scan_in_progress and not window.has_running_music_scan_threads(),
        )
        assert window.song_list.count() == len(slow_paths)
        assert any("已有音乐导入" in message for message in dialog_messages)
        results["concurrent_rejected"] = True

        reset_window_library(window, gui_thread_id)
        ControlledMutagen.reset()
        missing = Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "missing" / "gone.mp3"
        failure_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import([missing], source="manual_files"),
            counts,
        )
        assert failure_metrics["failed_count"] == 1
        retry_file = make_audio_files(missing.parent, 1, prefix="retry")[0]
        retry_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import([retry_file], source="manual_files"),
            counts,
        )
        assert retry_metrics["added_count"] == 1
        stale_count = window.song_list.count()
        window.on_music_scan_worker_finished(
            window.music_scan_generation - 1,
            {"new_songs": [{"path": str(retry_file), "title": "stale"}]},
        )
        assert window.song_list.count() == stale_count

        reset_window_library(window, gui_thread_id)
        save_failure_file = make_audio_files(
            Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "save_failure",
            1,
            prefix="save_failure",
        )[0]
        working_save_library = window.save_music_library
        window.save_music_library = lambda: (_ for _ in ()).throw(
            OSError("controlled library save failure")
        )
        try:
            save_failure_metrics = run_async_operation(
                app,
                window,
                lambda: window.start_manual_music_import(
                    [save_failure_file],
                    source="manual_files",
                ),
                counts,
            )
        finally:
            window.save_music_library = working_save_library
        assert save_failure_metrics["apply_failed"]
        assert not window.music_scan_in_progress
        assert window.song_list.count() == 1
        reset_window_library(window, gui_thread_id)
        save_retry_metrics = run_async_operation(
            app,
            window,
            lambda: window.start_manual_music_import(
                [save_failure_file],
                source="manual_files",
            ),
            counts,
        )
        assert not save_retry_metrics["apply_failed"]
        assert save_retry_metrics["added_count"] == 1
        assert save_retry_metrics["save_count"] == 1
        results["failure_retry_and_stale"] = {
            "save_failure": save_failure_metrics,
            "save_retry": save_retry_metrics,
        }

        assert window.close()
        process_events(app, 20)
        assert active_thread_count(window) == 0
        assert active_process_count(window) == 0
        assert not window.music_scan_apply_timer.isActive()
        assert not window.music_scan_finalize_timer.isActive()

        close_window = MainWindow()
        close_window.resize(900, 640)
        close_window.show()
        process_events(app, 5)
        close_counts = install_window_counters(close_window, gui_thread_id)
        reset_window_library(close_window, gui_thread_id)
        close_paths = make_audio_files(
            Path(os.environ["HUSHPLAYER_CACHE_DIR"]) / "close",
            4,
            prefix="close_slow",
        )
        ControlledMutagen.reset(0.12)
        MainWindow.MUSIC_SCAN_SHUTDOWN_TIMEOUT_MS = 20
        assert close_window.start_manual_music_import(close_paths, source="manual_files")
        assert wait_until(
            app,
            lambda: close_window.has_running_music_scan_threads() and ControlledMutagen.calls > 0,
            timeout_ms=1000,
        )
        close_started_at = time.perf_counter()
        initial_close_accepted = close_window.close()
        initial_close_ms = (time.perf_counter() - close_started_at) * 1000
        assert not initial_close_accepted
        assert initial_close_ms < 500.0
        assert wait_until(
            app,
            lambda: not close_window.isVisible() and not close_window.has_running_music_scan_threads(),
            timeout_ms=5000,
        )
        process_events(app, 20)
        assert close_counts["create_item"] == 0
        assert close_counts["save"] == 0
        assert close_window.song_list.count() == 0
        assert not close_window.music_scan_workers
        assert not close_window.music_scan_threads
        assert not close_window.music_scan_lifecycle
        assert not close_window.music_scan_in_progress
        assert active_thread_count(close_window) == 0
        assert active_process_count(close_window) == 0
        assert not close_window.music_scan_apply_timer.isActive()
        assert not close_window.music_scan_finalize_timer.isActive()
        results["close"] = {
            "initial_close_ms": round(initial_close_ms, 3),
            "active_qthreads": active_thread_count(close_window),
            "active_qprocesses": active_process_count(close_window),
            "ui_items_after_close": close_counts["create_item"],
            "library_saves_after_close": close_counts["save"],
        }

        forbidden_warnings = (
            "QObject::setParent",
            "Recursive repaint",
            "QBackingStore::endPaint",
            "QThread: Destroyed while thread is still running",
            "QPainter",
        )
        relevant_warnings = [
            message
            for message in qt_messages
            if any(token in message for token in forbidden_warnings)
        ]
        assert not relevant_warnings, relevant_warnings
        assert scan_thread_ids and all(thread_id != gui_thread_id for thread_id in scan_thread_ids)
        results["thread_boundary"] = {
            "gui_thread_id": gui_thread_id,
            "scan_thread_ids": sorted(set(scan_thread_ids)),
            "metadata_thread_ids": sorted(set(ControlledMutagen.thread_ids)),
            "qt_warning_count": len(relevant_warnings),
        }
        return results
    finally:
        MainWindow.MUSIC_SCAN_SHUTDOWN_TIMEOUT_MS = original_shutdown_timeout
        main_window_module.MutagenFile = original_mutagen
        main_window_module.os.walk = original_os_walk
        MusicFolderScanWorker.scan_entries = original_scan_entries
        MusicFolderScanWorker.is_link_or_junction = staticmethod(original_link_check)
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        AppPaths._migrate_legacy_data_files = original_migrate
        QMessageBox.information = original_message_info
        QMessageBox.warning = original_message_warning
        QFileDialog.getOpenFileNames = original_dialog_files
        QFileDialog.getExistingDirectory = original_dialog_folder
        qInstallMessageHandler(previous_handler)
        for candidate in (window, close_window):
            if candidate is None:
                continue
            try:
                candidate.shutdown_music_scan_workers(timeout_ms=1000)
                candidate.shutdown_media_workers(timeout_ms=1000)
                candidate.close()
                candidate.deleteLater()
            except RuntimeError:
                pass
        process_events(app, 20)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        process_events(app, 10)


def main() -> int:
    original_env = {
        name: os.environ.get(name)
        for name in (
            "HUSHPLAYER_APP_DATA_DIR",
            "HUSHPLAYER_CACHE_DIR",
            "HUSHPLAYER_LOG_DIR",
        )
    }
    app = QApplication.instance() or QApplication([])
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_manual_import_async_") as temp_dir:
            root = Path(temp_dir)
            prepare_isolated_storage(root)
            os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
            os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
            os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
            results = run_test(app)
        print(RESULT_PREFIX + json.dumps(results, ensure_ascii=False, sort_keys=True))
        print("manual import async smoke: PASS")
        return 0
    finally:
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    raise SystemExit(main())
