from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, QProcess, QThread, Signal, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

import app.ui.main_window as main_window_module
from app.ui.main_window import MainWindow


class ControlledMediaWorker(QObject):
    status_changed = Signal(str, str)
    finished = Signal(str, object)

    kind = "media"
    created_count = 0
    active_count = 0
    peak_active = 0

    def __init__(
        self,
        request_id: str,
        file_path: str,
        title: str,
        artist: str,
        album: str,
        **_kwargs,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.file_path = file_path
        self.title = title
        self.artist = artist
        self.album = album
        self._cancel_requested = False
        type(self).created_count += 1

    @classmethod
    def reset_metrics(cls) -> None:
        cls.created_count = 0
        cls.active_count = 0
        cls.peak_active = 0

    def cancel(self) -> None:
        self._cancel_requested = True

    def is_cancelled(self) -> bool:
        return self._cancel_requested or QThread.currentThread().isInterruptionRequested()

    def result(self, source: str, ok: bool) -> dict:
        result = {
            "ok": ok,
            "source": source,
            "message": source,
            "song_path": self.file_path,
        }
        if ok and self.kind == "cover":
            result["cover_path"] = str(Path(self.file_path).with_suffix(".jpg"))
        if ok and self.kind == "lyrics":
            result["lyrics_path"] = str(Path(self.file_path).with_suffix(".lrc"))
        return result

    def run(self) -> None:
        worker_type = type(self)
        worker_type.active_count += 1
        worker_type.peak_active = max(worker_type.peak_active, worker_type.active_count)

        def emit_result(result: dict) -> None:
            print(
                f"[lifecycle] {self.kind}:{self.request_id} result emitted",
                flush=True,
            )
            self.finished.emit(self.request_id, result)

        try:
            self.status_changed.emit(self.request_id, f"{self.kind} running")
            path_name = Path(self.file_path).stem.casefold()
            ignore_cancel = "stale" in path_name
            if "shutdown_timeout" in path_name:
                delay_ms = 1700
            elif any(token in path_name for token in ("slow", "stale")):
                delay_ms = 140
            else:
                delay_ms = 12
            deadline = time.monotonic() + delay_ms / 1000.0
            while time.monotonic() < deadline:
                if self.is_cancelled() and not ignore_cancel:
                    emit_result(self.result("cancelled", False))
                    return
                QThread.msleep(2)

            if self.is_cancelled() and not ignore_cancel:
                emit_result(self.result("cancelled", False))
            elif "fail" in path_name:
                emit_result(self.result("error", False))
            elif "timeout" in path_name:
                emit_result(self.result("timeout", False))
            elif "early" in path_name:
                emit_result(self.result("empty", False))
            elif "cache" in path_name:
                emit_result(self.result("cache", True))
            else:
                emit_result(self.result("fixture", True))
        finally:
            worker_type.active_count -= 1


class ControlledCoverWorker(ControlledMediaWorker):
    kind = "cover"
    created_count = 0
    active_count = 0
    peak_active = 0


class ControlledLyricsWorker(ControlledMediaWorker):
    kind = "lyrics"
    created_count = 0
    active_count = 0
    peak_active = 0


def process_events(app: QApplication, rounds: int = 5) -> None:
    for _ in range(rounds):
        app.processEvents()


def wait_until(
    app: QApplication,
    predicate,
    timeout_ms: int = 4000,
) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QThread.msleep(2)
    app.processEvents()
    return bool(predicate())


def media_idle(window: MainWindow, kind: str) -> bool:
    if kind == "cover":
        return (
            not window.cover_workers
            and not window.cover_threads
            and not window.retiring_cover_workers
            and not window.retiring_cover_threads
            and window._pending_cover_request is None
            and window._running_cover_request is None
            and not any(
                record.get("kind") == "cover"
                for record in window._media_lifecycle_records.values()
            )
        )
    return (
        not window.lyrics_workers
        and not window.lyrics_threads
        and not window.retiring_lyrics_workers
        and not window.retiring_lyrics_threads
        and window._pending_lyrics_request is None
        and window._running_lyrics_request is None
        and not any(
            record.get("kind") == "lyrics"
            for record in window._media_lifecycle_records.values()
        )
    )


def prepare_isolated_storage(root: Path) -> None:
    data_dir = root / "appdata" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "ignored_imports.json": [],
        "library.json": [],
        "pending_imports.json": [],
        "playback_session.json": {},
        "playlists.json": {},
        "play_queue.json": [],
        "remote_tracks.json": {"version": 1, "tracks": {}},
        "settings.json": {},
        "stats.json": {},
        "lyrics_bindings.json": {},
    }
    for filename, value in defaults.items():
        (data_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "metadata_cache.json").write_text("{}", encoding="utf-8")
    registry = root / "appdata" / "source_runtime" / "source_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps({"version": 1, "sources": []}, ensure_ascii=False),
        encoding="utf-8",
    )


def start_cover(window: MainWindow, path: str) -> None:
    window.current_song_path = window.normalize_song_path(path)
    window.start_cover_worker(path, Path(path).stem, "Fixture Artist", "Fixture Album")


def start_lyrics(window: MainWindow, path: str) -> None:
    window.current_song_path = window.normalize_song_path(path)
    window.start_lyrics_worker(path, Path(path).stem, "Fixture Artist", "Fixture Album")


def active_thread_count(window: MainWindow) -> int:
    return sum(1 for thread in window.findChildren(QThread) if thread.isRunning())


def active_process_count(window: MainWindow) -> int:
    return sum(
        1
        for process in window.findChildren(QProcess)
        if process.state() != QProcess.ProcessState.NotRunning
    )


def run_lifecycle_scenarios(
    window: MainWindow,
    app: QApplication,
    root: Path,
    metrics: dict,
) -> None:
    applied_covers: list[str] = []
    lifecycle_events: list[tuple[str, str]] = []

    def trace_lifecycle(stage: str, token: str) -> None:
        lifecycle_events.append((stage, token))
        if token.startswith("cover:"):
            active = len(window.cover_workers)
            retiring = len(window.retiring_cover_workers)
        else:
            active = len(window.lyrics_workers)
            retiring = len(window.retiring_lyrics_workers)
        print(
            f"[lifecycle] {token} {stage} active={active} retiring={retiring}",
            flush=True,
        )

    def record_cover(path: Path) -> bool:
        applied_covers.append(str(path))
        print(f"[lifecycle] cover result applied: {path}", flush=True)
        return True

    window._media_lifecycle_trace = trace_lifecycle
    window.show_cover_from_file = record_cover
    window.parse_lrc_file = lambda path: [(0, str(path))]
    window.sync_full_lyrics_from_current = lambda: None

    cover_success = str(root / "cover_success.mp3")
    print("[lifecycle] cover success: started", flush=True)
    start_cover(window, cover_success)
    assert wait_until(app, lambda: media_idle(window, "cover"))
    print("[lifecycle] cover success: collections empty", flush=True)
    metrics["single_cover_success_workers"] = len(window.cover_workers)
    assert metrics["single_cover_success_workers"] == 0
    assert applied_covers[-1].endswith("cover_success.jpg")
    cover_success_events = {
        stage for stage, token in lifecycle_events if token == "cover:1"
    }
    assert {
        "worker destroyed",
        "thread finished",
        "thread destroyed",
    }.issubset(cover_success_events)

    lyrics_success = str(root / "lyrics_success.mp3")
    print("[lifecycle] lyrics success: started", flush=True)
    start_lyrics(window, lyrics_success)
    assert wait_until(app, lambda: media_idle(window, "lyrics"))
    print("[lifecycle] lyrics success: collections empty", flush=True)
    metrics["single_lyrics_success_workers"] = len(window.lyrics_workers)
    assert metrics["single_lyrics_success_workers"] == 0
    assert window.current_lyrics[-1][1].endswith("lyrics_success.lrc")

    start_cover(window, str(root / "cover_fail.mp3"))
    start_lyrics(window, str(root / "lyrics_fail.mp3"))
    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )
    metrics["failure_workers"] = [len(window.cover_workers), len(window.lyrics_workers)]
    assert metrics["failure_workers"] == [0, 0]

    start_cover(window, str(root / "cover_timeout.mp3"))
    start_lyrics(window, str(root / "lyrics_timeout.mp3"))
    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )
    metrics["timeout_workers"] = [len(window.cover_workers), len(window.lyrics_workers)]
    assert metrics["timeout_workers"] == [0, 0]

    start_cover(window, str(root / "cover_cache.mp3"))
    start_lyrics(window, str(root / "lyrics_early.mp3"))
    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )
    assert not window.cover_workers and not window.lyrics_workers

    duplicate_cover = str(root / "duplicate_slow.mp3")
    start_cover(window, duplicate_cover)
    duplicate_cover_count = ControlledCoverWorker.created_count
    start_cover(window, duplicate_cover)
    assert ControlledCoverWorker.created_count == duplicate_cover_count

    duplicate_lyrics = str(root / "duplicate_lyrics_slow.mp3")
    start_lyrics(window, duplicate_lyrics)
    duplicate_lyrics_count = ControlledLyricsWorker.created_count
    start_lyrics(window, duplicate_lyrics)
    assert ControlledLyricsWorker.created_count == duplicate_lyrics_count
    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )

    stale_cover = str(root / "stale_cover_slow.mp3")
    stale_lyrics = str(root / "stale_lyrics_slow.mp3")
    start_cover(window, stale_cover)
    start_lyrics(window, stale_lyrics)
    assert wait_until(
        app,
        lambda: bool(window.cover_threads) and bool(window.lyrics_threads),
        timeout_ms=1000,
    )
    process_events(app, 3)
    cover_result_start = len(applied_covers)
    current_lyrics_before = list(window.current_lyrics)
    current_path = str(root / "current_after_stale.mp3")
    start_cover(window, current_path)
    start_lyrics(window, current_path)
    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )
    new_cover_results = applied_covers[cover_result_start:]
    assert new_cover_results and new_cover_results[-1].endswith("current_after_stale.jpg")
    assert not any(path.endswith("stale_cover_slow.jpg") for path in new_cover_results)
    assert window.current_lyrics != current_lyrics_before
    assert window.current_lyrics[-1][1].endswith("current_after_stale.lrc")
    metrics["stale_result_overwrite"] = False

    first_return_path = str(root / "switch_back_first_slow.mp3")
    middle_return_path = str(root / "switch_back_middle.mp3")
    start_cover(window, first_return_path)
    start_lyrics(window, first_return_path)
    start_cover(window, middle_return_path)
    start_lyrics(window, middle_return_path)
    start_cover(window, first_return_path)
    start_lyrics(window, first_return_path)
    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )
    assert applied_covers[-1].endswith("switch_back_first_slow.jpg")
    assert window.current_lyrics[-1][1].endswith("switch_back_first_slow.lrc")

    rapid_paths = [str(root / f"rapid_track_{index:02d}.mp3") for index in range(30)]
    collection_cover_peak = 0
    collection_lyrics_peak = 0
    created_cover_before = ControlledCoverWorker.created_count
    created_lyrics_before = ControlledLyricsWorker.created_count
    for path in rapid_paths:
        start_cover(window, path)
        start_lyrics(window, path)
        collection_cover_peak = max(collection_cover_peak, len(window.cover_workers))
        collection_lyrics_peak = max(collection_lyrics_peak, len(window.lyrics_workers))
        assert all(token.startswith("cover:") for token in window.cover_workers)
        assert all(token.startswith("lyrics:") for token in window.lyrics_workers)
        assert all(
            window._media_lifecycle_records[token].get("kind") == "cover"
            for token in window.cover_workers
        )
        assert all(
            window._media_lifecycle_records[token].get("kind") == "lyrics"
            for token in window.lyrics_workers
        )

    assert wait_until(
        app,
        lambda: media_idle(window, "cover") and media_idle(window, "lyrics"),
    )
    metrics["rapid_cover_collection_peak"] = collection_cover_peak
    metrics["rapid_lyrics_collection_peak"] = collection_lyrics_peak
    metrics["rapid_cover_created"] = ControlledCoverWorker.created_count - created_cover_before
    metrics["rapid_lyrics_created"] = ControlledLyricsWorker.created_count - created_lyrics_before
    metrics["all_tasks_finished_workers"] = [
        len(window.cover_workers),
        len(window.lyrics_workers),
    ]
    assert collection_cover_peak <= 1 and collection_lyrics_peak <= 1
    assert metrics["rapid_cover_created"] <= 2
    assert metrics["rapid_lyrics_created"] <= 2
    assert metrics["all_tasks_finished_workers"] == [0, 0]
    assert applied_covers[-1].endswith("rapid_track_29.jpg")
    assert window.current_lyrics[-1][1].endswith("rapid_track_29.lrc")

    window._on_media_worker_destroyed_notice("cover:already-finalized")
    window._on_media_worker_destroyed_notice("cover:already-finalized")
    window._on_media_thread_finished_notice("cover:already-finalized")
    window._on_media_thread_destroyed_notice("cover:already-finalized")
    assert media_idle(window, "cover")


def run_test(app: QApplication) -> None:
    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    original_auto_scan = MainWindow.auto_scan_music_folders_on_startup
    original_cover_worker = main_window_module.CoverSearchWorker
    original_lyrics_worker = main_window_module.LyricsSearchWorker
    original_timeout = MainWindow.MEDIA_WORKER_SHUTDOWN_TIMEOUT_MS
    original_env = {
        name: os.environ.get(name)
        for name in (
            "HUSHPLAYER_APP_DATA_DIR",
            "HUSHPLAYER_CACHE_DIR",
            "HUSHPLAYER_LOG_DIR",
        )
    }
    qt_messages: list[str] = []

    def collect_qt_message(_mode, _context, message: str) -> None:
        qt_messages.append(str(message))

    previous_message_handler = qInstallMessageHandler(collect_qt_message)
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    MainWindow.auto_scan_music_folders_on_startup = lambda self: None
    MainWindow.MEDIA_WORKER_SHUTDOWN_TIMEOUT_MS = 1500
    main_window_module.CoverSearchWorker = ControlledCoverWorker
    main_window_module.LyricsSearchWorker = ControlledLyricsWorker
    ControlledCoverWorker.reset_metrics()
    ControlledLyricsWorker.reset_metrics()
    window = None
    metrics: dict = {}
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_media_lifecycle_") as temp_dir:
            root = Path(temp_dir)
            prepare_isolated_storage(root)
            os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(root / "appdata")
            os.environ["HUSHPLAYER_CACHE_DIR"] = str(root / "cache")
            os.environ["HUSHPLAYER_LOG_DIR"] = str(root / "logs")
            window = MainWindow()
            window.resize(1000, 700)
            window.show()
            process_events(app)

            run_lifecycle_scenarios(window, app, root, metrics)

            close_cover = str(root / "stale_shutdown_timeout_cover.mp3")
            close_lyrics = str(root / "stale_shutdown_timeout_lyrics.mp3")
            start_cover(window, close_cover)
            start_lyrics(window, close_lyrics)
            assert wait_until(
                app,
                lambda: any(
                    thread.isRunning()
                    for thread in (
                        tuple(window.cover_threads.values())
                        + tuple(window.lyrics_threads.values())
                    )
                ),
                timeout_ms=1000,
            )
            metrics["active_qthreads_before_close"] = active_thread_count(window)
            metrics["active_qprocess_before_close"] = active_process_count(window)
            metrics["node_runners_before_close"] = int(
                window.online_source_client.process.state()
                != QProcess.ProcessState.NotRunning
            )
            close_started = time.monotonic()
            initial_close_accepted = window.close()
            metrics["initial_close_wait_ms"] = round(
                (time.monotonic() - close_started) * 1000,
                1,
            )
            assert not initial_close_accepted
            assert wait_until(
                app,
                lambda: (
                    not window.isVisible()
                    and media_idle(window, "cover")
                    and media_idle(window, "lyrics")
                ),
                timeout_ms=3500,
            )
            metrics["window_close_ms"] = round(
                (time.monotonic() - close_started) * 1000,
                1,
            )
            process_events(app, 10)
            metrics["active_qthreads_after_close"] = active_thread_count(window)
            metrics["active_qprocess_after_close"] = active_process_count(window)
            metrics["node_runners_after_close"] = int(
                window.online_source_client.process.state()
                != QProcess.ProcessState.NotRunning
            )
            metrics["visible_test_windows_after_close"] = int(window.isVisible())
            metrics["cover_worker_peak_active"] = ControlledCoverWorker.peak_active
            metrics["lyrics_worker_peak_active"] = ControlledLyricsWorker.peak_active
            metrics["qt_lifecycle_warning"] = any(
                "QThread: Destroyed while thread is still running" in message
                for message in qt_messages
            )
            assert not window.cover_workers and not window.lyrics_workers
            assert not window.cover_threads and not window.lyrics_threads
            assert metrics["active_qthreads_after_close"] == 0
            assert metrics["active_qprocess_after_close"] == 0
            assert metrics["node_runners_after_close"] == 0
            assert metrics["visible_test_windows_after_close"] == 0
            assert metrics["cover_worker_peak_active"] <= 1
            assert metrics["lyrics_worker_peak_active"] <= 1
            assert not metrics["qt_lifecycle_warning"]
            assert ControlledCoverWorker.active_count == 0
            assert ControlledLyricsWorker.active_count == 0
            print(
                "media worker lifecycle smoke: OK",
                json.dumps(metrics, ensure_ascii=False, sort_keys=True),
            )
    finally:
        if window is not None:
            window.shutdown_media_workers(timeout_ms=1500)
            drained = wait_until(
                app,
                lambda: (
                    media_idle(window, "cover")
                    and media_idle(window, "lyrics")
                ),
                timeout_ms=4000,
            )
            window.hide()
            if drained:
                window.deleteLater()
                process_events(app, 10)
            else:
                print(
                    "[lifecycle] teardown retained window: media objects not drained",
                    flush=True,
                )
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan
        MainWindow.MEDIA_WORKER_SHUTDOWN_TIMEOUT_MS = original_timeout
        main_window_module.CoverSearchWorker = original_cover_worker
        main_window_module.LyricsSearchWorker = original_lyrics_worker
        qInstallMessageHandler(previous_message_handler)
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    run_test(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
