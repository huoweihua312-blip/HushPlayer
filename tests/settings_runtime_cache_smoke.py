from __future__ import annotations

import contextlib
import io
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

from PySide6.QtCore import QCoreApplication, QEvent, QProcess, QThread, SIGNAL
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.app_paths import AppPaths
from app.ui.main_window import MainWindow


RESULT_PREFIX = "SETTINGS_RUNTIME_RESULT="


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path):
    with io.open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def prepare_storage(
    root: Path,
    settings: dict | None = None,
    *,
    include_settings: bool = True,
) -> Path:
    data_dir = root / "appdata" / "data"
    defaults = {
        "ignored_imports.json": [],
        "library.json": [],
        "lyrics_bindings.json": {},
        "pending_imports.json": [],
        "playback_session.json": {},
        "playlists.json": {},
        "play_queue.json": [],
        "remote_tracks.json": {"version": 1, "tracks": {}},
        "stats.json": {},
    }
    if include_settings:
        defaults["settings.json"] = (
            settings
            if settings is not None
            else {
                "volume": 37,
                "play_mode": "list_loop",
                "auto_scan_music_folders_on_startup": False,
                "legacy_extension": {"kept": True},
            }
        )
    for filename, value in defaults.items():
        write_json(data_dir / filename, value)

    write_json(root / "cache" / "metadata_cache.json", {})
    write_json(
        root / "appdata" / "source_runtime" / "source_registry.json",
        {"version": 1, "sources": []},
    )
    return data_dir / "settings.json"


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


def normalized_path(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


class SettingsIoCounter:
    def __init__(self, settings_path: Path, stats_path: Path | None = None) -> None:
        self.settings_path = normalized_path(settings_path)
        self.stats_path = normalized_path(stats_path) if stats_path else ""
        self.settings_reads = 0
        self.settings_writes = 0
        self.stats_writes = 0
        self._path_open = Path.open
        self._path_replace = Path.replace

    def __enter__(self):
        counter = self

        def counted_open(path_self: Path, *args, **kwargs):
            mode = str(args[0] if args else kwargs.get("mode", "r"))
            path_key = normalized_path(path_self)
            if path_key == counter.settings_path:
                if "r" in mode:
                    counter.settings_reads += 1
                if any(flag in mode for flag in ("w", "a", "+", "x")):
                    counter.settings_writes += 1
            if path_key == counter.stats_path and any(
                flag in mode for flag in ("w", "a", "+", "x")
            ):
                counter.stats_writes += 1
            return counter._path_open(path_self, *args, **kwargs)

        def counted_replace(path_self: Path, target: Path | str):
            if normalized_path(target) == counter.settings_path:
                counter.settings_writes += 1
            return counter._path_replace(path_self, target)

        Path.open = counted_open
        Path.replace = counted_replace
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        Path.open = self._path_open
        Path.replace = self._path_replace


def create_window() -> MainWindow:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        return MainWindow()


def dispose_window(app: QApplication, window: MainWindow | None) -> dict:
    if window is None:
        return {"threads": 0, "processes": 0, "settings_timer_active": False}
    running_threads = sum(
        1 for thread in window.findChildren(QThread) if thread.isRunning()
    )
    running_processes = sum(
        1
        for process in window.findChildren(QProcess)
        if process.state() != QProcess.ProcessState.NotRunning
    )
    settings_timer = getattr(window, "settings_save_timer", None)
    settings_timer_active = bool(settings_timer and settings_timer.isActive())
    window.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return {
        "threads": running_threads,
        "processes": running_processes,
        "settings_timer_active": settings_timer_active,
    }


def volume_values(start: int = 37, count: int = 100) -> list[int]:
    return [(start + index + 1) % 101 for index in range(count)]


def assert_load_compatibility(window: MainWindow, root: Path) -> None:
    original_path = window.settings_file
    cases_dir = root / "settings_cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    try:
        missing_path = cases_dir / "missing.json"
        window.settings_file = missing_path
        assert window.load_settings() == {"volume": 65, "play_mode": "list_loop"}

        for name, text in (("empty", ""), ("damaged", "{broken")):
            path = cases_dir / f"{name}.json"
            path.write_text(text, encoding="utf-8")
            window.settings_file = path
            assert window.load_settings() == {"volume": 65, "play_mode": "list_loop"}
            assert path.read_text(encoding="utf-8") == text

        non_object_path = cases_dir / "non_object.json"
        write_json(non_object_path, ["not", "an", "object"])
        window.settings_file = non_object_path
        assert window.load_settings() == {"volume": 65, "play_mode": "list_loop"}

        missing_fields_path = cases_dir / "missing_fields.json"
        write_json(missing_fields_path, {"old_field": "保留"})
        window.settings_file = missing_fields_path
        loaded = window.load_settings()
        assert loaded["volume"] == 65
        assert loaded["play_mode"] == "list_loop"
        assert loaded["old_field"] == "保留"

        invalid_types_path = cases_dir / "invalid_types.json"
        write_json(
            invalid_types_path,
            {
                "volume": {"bad": True},
                "play_mode": ["shuffle"],
                "immersive_background_alpha": {"bad": True},
                "floating_lyrics_opacity": [],
                "floating_lyrics_font_size": None,
                "floating_lyrics_width": {"bad": True},
                "floating_lyrics_height": [],
                "music_scan_folders": None,
                "unknown_future_field": {"nested": [1, 2, 3]},
            },
        )
        window.settings_file = invalid_types_path
        loaded = window.load_settings()
        assert loaded["volume"] == 65
        assert loaded["play_mode"] == "list_loop"
        assert loaded["immersive_background_alpha"] == 68
        assert loaded["immersive_background_mode"] == "cover"
        assert loaded["immersive_background_blur"] == 40
        assert loaded["immersive_background_darkness"] == 68
        assert loaded["immersive_background_image_opacity"] == 100
        assert loaded["immersive_background_fill_mode"] == "cover"
        assert loaded["immersive_lyrics_font_scale"] == 100
        assert loaded["floating_lyrics_opacity"] == 100
        assert loaded["floating_lyrics_font_size"] == 42
        assert loaded["floating_lyrics_width"] == 980
        assert loaded["floating_lyrics_height"] == 135
        assert loaded["music_scan_folders"] == []
        assert loaded["unknown_future_field"] == {"nested": [1, 2, 3]}

        appearance_path = cases_dir / "appearance.json"
        write_json(
            appearance_path,
            {
                "volume": 65,
                "play_mode": "list_loop",
                "immersive_background_mode": "custom",
                "immersive_background_custom_path": "C:/missing/background.webp",
                "immersive_background_blur": 99,
                "immersive_background_darkness": -5,
                "immersive_background_image_opacity": 500,
                "immersive_background_fill_mode": "contain",
                "immersive_lyrics_font_scale": 113,
                "immersive_cover_background_enabled": True,
                "immersive_background_alpha": 88,
                "appearance_future_field": "保留",
            },
        )
        window.settings_file = appearance_path
        loaded = window.load_settings()
        assert loaded["immersive_background_mode"] == "custom"
        assert loaded["immersive_background_custom_path"] == "C:/missing/background.webp"
        assert loaded["immersive_background_blur"] == 40
        assert loaded["immersive_background_darkness"] == 0
        assert loaded["immersive_background_image_opacity"] == 100
        assert loaded["immersive_background_fill_mode"] == "contain"
        assert loaded["immersive_lyrics_font_scale"] == 115
        assert loaded["immersive_cover_background_enabled"] is False
        assert loaded["immersive_background_alpha"] == 0
        assert loaded["appearance_future_field"] == "保留"

        old_version_path = cases_dir / "old_version.json"
        write_json(
            old_version_path,
            {"volume": "88", "play_mode": "shuffle", "legacy_toggle": True},
        )
        window.settings_file = old_version_path
        loaded = window.load_settings()
        assert loaded == {
            "volume": 88,
            "play_mode": "shuffle",
            "legacy_toggle": True,
        }
    finally:
        window.settings_file = original_path


def assert_missing_settings_startup(app: QApplication) -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_settings_missing_") as temp_dir:
        root = Path(temp_dir)
        settings_path = prepare_storage(root, include_settings=False)
        previous_env = install_storage_environment(root)
        original_migration = AppPaths._migrate_legacy_data_files
        window = None
        try:
            AppPaths._migrate_legacy_data_files = lambda _self: None
            with SettingsIoCounter(settings_path) as counter:
                window = create_window()
                assert counter.settings_reads == 0
                assert window.current_volume == 65
                assert window.play_mode == "list_loop"
                assert not window._settings_dirty
                window.close()
                assert counter.settings_writes == 0
            residue = dispose_window(app, window)
            assert residue["threads"] == 0
            assert residue["processes"] == 0
            assert not residue["settings_timer_active"]
        finally:
            AppPaths._migrate_legacy_data_files = original_migration
            restore_storage_environment(previous_env)


def run_close_case(app: QApplication, mode: str) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"hushplayer_settings_close_{mode}_") as temp_dir:
        root = Path(temp_dir)
        settings_path = prepare_storage(root)
        stats_path = root / "appdata" / "data" / "stats.json"
        previous_env = install_storage_environment(root)
        window = None
        try:
            with SettingsIoCounter(settings_path, stats_path) as counter:
                window = create_window()
                reads_after_startup = counter.settings_reads
                if mode == "dirty":
                    window.save_hush_settings({"close_marker": "dirty"})
                elif mode == "pending_volume":
                    window.volume_slider.setValue(91)
                    assert window.settings_save_timer.isActive()
                elif mode == "pending_stats":
                    song_path = root / "music" / "stats-track.mp3"
                    song_path.parent.mkdir(parents=True, exist_ok=True)
                    song_path.touch()
                    window.current_song_path = str(song_path)
                    window.pending_listen_ms = 1_500
                    assert window.get_song_stats(str(song_path)) is not None

                writes_before_close = counter.settings_writes
                stats_writes_before_close = counter.stats_writes
                close_started_at = time.perf_counter()
                window.close()
                close_ms = (time.perf_counter() - close_started_at) * 1000
                settings_writes = counter.settings_writes - writes_before_close
                stats_writes = counter.stats_writes - stats_writes_before_close
                settings_timer_active = window.settings_save_timer.isActive()
                writes_after_first_close = counter.settings_writes
                window.close()
                second_close_settings_writes = (
                    counter.settings_writes - writes_after_first_close
                )
                final_content = read_json(settings_path)
                final_size = settings_path.stat().st_size
            residue = dispose_window(app, window)
            visible_windows = sum(
                1 for widget in app.topLevelWidgets() if widget.isVisible()
            )
        finally:
            restore_storage_environment(previous_env)
    return {
        "startup_reads": reads_after_startup,
        "settings_writes": settings_writes,
        "stats_writes": stats_writes,
        "settings_timer_active": settings_timer_active,
        "second_close_settings_writes": second_close_settings_writes,
        "final_content": final_content,
        "final_size": final_size,
        "close_ms": round(close_ms, 3),
        "threads": residue["threads"],
        "processes": residue["processes"],
        "timer_residue": residue["settings_timer_active"],
        "visible_windows": visible_windows,
    }


def run_optimized_smoke(app: QApplication) -> dict:
    with tempfile.TemporaryDirectory(prefix="hushplayer_settings_cache_") as temp_dir:
        root = Path(temp_dir)
        settings_path = prepare_storage(root)
        previous_env = install_storage_environment(root)
        window = None
        try:
            with SettingsIoCounter(settings_path) as counter:
                window = create_window()
                assert counter.settings_reads == 1
                assert window.current_volume == 37
                assert window.volume_slider.value() == 37
                assert window.settings["legacy_extension"] == {"kept": True}
                assert not window._settings_dirty
                assert window.volume_slider.receivers(SIGNAL("valueChanged(int)")) == 2

                reads_before_queries = counter.settings_reads
                for _index in range(100):
                    snapshot = window.get_hush_settings()
                    assert snapshot["legacy_extension"] == {"kept": True}
                    assert window.get_user_setting("volume") == 37
                    snapshot["volume"] = -1
                    snapshot["legacy_extension"]["kept"] = False
                assert counter.settings_reads == reads_before_queries
                assert window.settings["volume"] == 37

                assert_load_compatibility(window, root)

                writes_before = counter.settings_writes
                window.save_hush_settings(
                    {
                        "ordinary_setting": "first",
                        "floating_lyrics_font_size": 54,
                        "floating_lyrics_x": 123,
                    }
                )
                window.save_hush_settings(
                    {
                        "online_search_local_only": True,
                        "auto_scan_music_folders_on_startup": True,
                    }
                )
                assert window._settings_dirty
                assert counter.settings_writes == writes_before
                assert window.settings["legacy_extension"] == {"kept": True}
                assert window.flush_settings()
                ordinary_setting_writes = counter.settings_writes - writes_before
                assert ordinary_setting_writes == 1
                assert not window._settings_dirty
                assert not window.flush_settings()
                assert counter.settings_writes - writes_before == 1
                saved_settings = read_json(settings_path)
                assert saved_settings["floating_lyrics_font_size"] == 54
                assert saved_settings["floating_lyrics_x"] == 123
                assert saved_settings["online_search_local_only"] is True
                assert saved_settings["auto_scan_music_folders_on_startup"] is True

                writes_before = counter.settings_writes
                window.save_hush_settings({"ordinary_setting": "first"})
                assert not window._settings_dirty
                assert not window.settings_save_timer.isActive()
                assert counter.settings_writes == writes_before

                original_writer = window._write_settings_file
                original_warning = QMessageBox.warning
                warnings = []
                disk_before_failed_write = read_json(settings_path)
                try:
                    window._write_settings_file = lambda _settings: (_ for _ in ()).throw(
                        OSError("fixture write failure")
                    )
                    QMessageBox.warning = lambda *args, **kwargs: warnings.append(args)
                    window.save_hush_settings({"survives_failed_write": "yes"})
                    assert not window.flush_settings()
                    assert window._settings_dirty
                    assert window.settings["survives_failed_write"] == "yes"
                    assert read_json(settings_path) == disk_before_failed_write
                    assert warnings
                finally:
                    window._write_settings_file = original_writer
                    QMessageBox.warning = original_warning
                assert window.flush_settings()
                assert not window._settings_dirty

                writes_before = counter.settings_writes
                window.play_mode = "shuffle"
                window.save_settings()
                assert window.settings["play_mode"] == "shuffle"
                assert window._settings_dirty
                assert window.flush_settings()
                assert counter.settings_writes - writes_before == 1
                assert read_json(settings_path)["play_mode"] == "shuffle"

                writes_before = counter.settings_writes
                observed_values = []
                window.volume_slider.valueChanged.connect(observed_values.append)
                with contextlib.redirect_stdout(io.StringIO()):
                    for value in volume_values():
                        window.volume_slider.setValue(value)
                        assert abs(window.audio_output.volume() - value / 100) < 0.02
                assert len(observed_values) == 100
                assert counter.settings_writes == writes_before
                assert window._settings_dirty
                assert window.settings_save_timer.isActive()
                assert window.flush_settings()
                volume_100_writes = counter.settings_writes - writes_before
                assert volume_100_writes == 1
                assert window.settings["volume"] == volume_values()[-1]
                assert read_json(settings_path)["volume"] == volume_values()[-1]

                writes_before = counter.settings_writes
                window.volume_slider.setValue(70)
                QTest.qWait(180)
                window.volume_slider.setValue(71)
                QTest.qWait(180)
                assert counter.settings_writes == writes_before
                QTest.qWait(window.settings_save_timer.interval())
                assert counter.settings_writes - writes_before == 1
                assert read_json(settings_path)["volume"] == 71

                writes_before = counter.settings_writes
                window.volume_slider.setValue(72)
                QTest.qWait(window.settings_save_timer.interval() + 100)
                assert counter.settings_writes - writes_before == 1
                assert not window._settings_dirty
                assert counter.settings_reads == reads_before_queries

                window.close()
                assert not window.settings_save_timer.isActive()
            residue = dispose_window(app, window)
        finally:
            restore_storage_environment(previous_env)

    unchanged = run_close_case(app, "unchanged")
    dirty = run_close_case(app, "dirty")
    pending_volume = run_close_case(app, "pending_volume")
    pending_stats = run_close_case(app, "pending_stats")
    assert_missing_settings_startup(app)

    assert unchanged["startup_reads"] == 1
    assert unchanged["settings_writes"] == 0
    assert dirty["settings_writes"] == 1
    assert dirty["final_content"]["close_marker"] == "dirty"
    assert pending_volume["settings_writes"] == 1
    assert pending_volume["final_content"]["volume"] == 91
    assert pending_stats["stats_writes"] == 1
    for result in (unchanged, dirty, pending_volume, pending_stats):
        assert not result["settings_timer_active"]
        assert result["second_close_settings_writes"] == 0
        assert result["threads"] == 0
        assert result["processes"] == 0
        assert not result["timer_residue"]
        assert result["visible_windows"] == 0

    return {
        "startup_settings_reads": 1,
        "repeated_100_query_reads": 0,
        "ordinary_setting_writes": ordinary_setting_writes,
        "volume_100_writes": volume_100_writes,
        "unchanged_close_writes": unchanged["settings_writes"],
        "dirty_close_writes": dirty["settings_writes"],
        "pending_volume_close_writes": pending_volume["settings_writes"],
        "pending_stats_close_writes": pending_stats["stats_writes"],
        "final_settings_size": pending_volume["final_size"],
        "final_settings_content": pending_volume["final_content"],
        "close_ms": {
            "unchanged": unchanged["close_ms"],
            "dirty": dirty["close_ms"],
            "pending_volume": pending_volume["close_ms"],
        },
        "qt_threads_running": residue["threads"],
        "qt_processes_running": residue["processes"],
        "settings_timer_residue": residue["settings_timer_active"],
        "visible_windows": unchanged["visible_windows"],
    }


def main() -> int:
    app = QApplication.instance() or QApplication([])
    result = run_optimized_smoke(app)
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
