from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

import main
import main_v2
from app.core.app_paths import AppPaths
from app.services.library_repository import LibraryRepository
from app.services.remote_track_store import RemoteTrackStore
from app.startup import apply_ui_theme, create_application_context
from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.startup import (
    UiV2RuntimeServices,
    build_ui_v2_runtime_services,
    create_ui_v2_main_window,
)
from app.ui_v2.theme.tokens import get_theme


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_state(paths: tuple[Path, ...]) -> dict[Path, tuple[str, int, int]]:
    return {
        path: (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in paths
    }


class CountingRepository(LibraryRepository):
    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.load_count = 0

    def load_snapshot(self):  # noqa: ANN201 - same dynamic return as base class
        self.load_count += 1
        return super().load_snapshot()


class StartupArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_no_arguments_keep_legacy_ui_as_default(self) -> None:
        with patch.object(main, "run_legacy_application", return_value=0) as legacy, patch.object(
            main, "run_ui_v2_from_main", return_value=0
        ) as ui_v2:
            self.assertEqual(main.main(["main.py"]), 0)
        legacy.assert_called_once()
        ui_v2.assert_not_called()

    def test_ui_v2_argument_uses_opt_in_v2_entry(self) -> None:
        with patch.object(main, "run_legacy_application", return_value=0) as legacy, patch.object(
            main, "run_ui_v2_from_main", return_value=0
        ) as ui_v2:
            self.assertEqual(main.main(["main.py", "--ui-v2"]), 0)
        legacy.assert_not_called()
        ui_v2.assert_called_once()

    def test_ui_v2_mock_argument_selects_the_isolated_mock_factory(self) -> None:
        with patch.object(main, "run_ui_v2_from_main", return_value=0) as ui_v2:
            self.assertEqual(main.main(["main.py", "--ui-v2", "--mock"]), 0)
        ui_v2.assert_called_once_with(
            ["main.py", "--ui-v2", "--mock"], data_mode="mock"
        )

    def test_invalid_argument_has_clear_startup_error(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main.parse_startup_arguments(["main.py", "--not-a-real-option"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unrecognized arguments", stderr.getvalue())

    def test_main_v2_reuses_shared_ui_v2_runner(self) -> None:
        with patch.object(main_v2, "ui_v2_data_mode", return_value="mock") as mode, patch.object(
            main_v2, "run_ui_v2_application", return_value=11
        ) as runner:
            self.assertEqual(main_v2.main(), 11)
        mode.assert_called_once()
        runner.assert_called_once()

    def test_application_context_reuses_the_existing_qapplication(self) -> None:
        first = create_application_context(["main.py"])
        second = create_application_context(["main.py", "--ui-v2"])
        self.assertIs(first.app, self.app)
        self.assertIs(second.app, self.app)
        self.assertFalse(first.created_application)
        self.assertFalse(second.created_application)

    def test_v2_theme_is_installed_by_flavor_before_window_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = str(Path(temporary) / "settings.json")
            apply_ui_theme(self.app, "ui-v2", settings_path=settings_path)
        self.assertEqual(self.app.property("hushUiFlavor"), "ui-v2")
        self.assertEqual(self.app.property("hushUiV2ThemeMode"), "dark")
        self.assertIn(get_theme("dark").colors.app_background, self.app.styleSheet())
        apply_ui_theme(self.app, "legacy")
        self.assertEqual(self.app.property("hushUiFlavor"), "legacy")
        self.assertNotIn(get_theme("dark").colors.app_background, self.app.styleSheet())

    def test_ui_v2_startup_failure_returns_clear_error(self) -> None:
        stderr = io.StringIO()
        with patch(
            "app.ui_v2.startup.create_ui_v2_main_window",
            side_effect=RuntimeError("fixture failure"),
        ), redirect_stderr(stderr):
            self.assertEqual(main.run_ui_v2_from_main(["main.py", "--ui-v2"]), 1)
        self.assertIn("UI V2 启动失败", stderr.getvalue())
        self.assertIn("fixture failure", stderr.getvalue())


class ProductionRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.app_data = self.root / "app-data"
        self.data_dir = self.app_data / "data"
        self.cache_dir = self.root / "cache"
        self.log_dir = self.root / "logs"
        self.data_dir.mkdir(parents=True)
        self.alpha = self.root / "music" / "alpha.mp3"
        self.alpha.parent.mkdir(parents=True)
        self.alpha.write_bytes(b"audio fixture")
        self.paths = AppPaths(
            bundled_resource_dir=PROJECT_ROOT,
            application_data_dir=self.app_data,
            cache_dir=self.cache_dir,
            log_dir=self.log_dir,
            frozen=False,
            legacy_project_dir=PROJECT_ROOT,
        )
        self.library_file = self.data_dir / "library.json"
        self.playlists_file = self.data_dir / "playlists.json"
        self.stats_file = self.data_dir / "stats.json"
        self.remote_file = self.data_dir / "remote_tracks.json"
        self.settings_file = self.data_dir / "settings.json"
        self._write_documents()
        self.document_paths = (
            self.library_file,
            self.playlists_file,
            self.stats_file,
            self.remote_file,
            self.settings_file,
        )
        self.before_state = _file_state(self.document_paths)
        self.repository = CountingRepository(
            self.library_file,
            self.playlists_file,
            self.stats_file,
        )
        self.services = UiV2RuntimeServices(
            paths=self.paths,
            settings_path=self.settings_file,
            repository=self.repository,
            remote_tracks=RemoteTrackStore(self.remote_file),
            playback_adapter=PlaybackAdapter(timer_enabled=False),
            lyrics_adapter=LyricsAdapter(),
        )
        self.window = create_ui_v2_main_window(
            data_mode="real",
            services=self.services,
            initialize_storage=False,
        )
        self.window.show()
        self.assertTrue(
            self._wait_for(
                lambda: self.window.real_library_adapter is not None
                and self.window.real_library_adapter.state in {"loaded", "empty", "error"}
            )
        )

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temporary_directory.cleanup()

    def _write_documents(self) -> None:
        _write_json(
            self.library_file,
            [
                {
                    "path": str(self.alpha),
                    "title": "Alpha",
                    "artist": "Artist A",
                    "album": "Album A",
                    "duration": 181,
                    "added_at": 100,
                }
            ],
        )
        _write_json(
            self.playlists_file,
            {
                "liked": {
                    "name": "我喜欢",
                    "members": [{"kind": "local", "id": str(self.alpha), "added_at": 200}],
                },
                "road": {
                    "name": "Road",
                    "members": [{"kind": "local", "id": str(self.alpha), "added_at": 100}],
                },
            },
        )
        _write_json(self.stats_file, {str(self.alpha): {"play_count": 1, "last_played": 500}})
        _write_json(self.remote_file, {"version": 1, "tracks": {}})
        _write_json(self.settings_file, {"appearance_mode": "dark", "volume": 42})

    def _wait_for(self, predicate, *, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return bool(predicate())

    def test_production_v2_uses_injected_repository_settings_and_adapters(self) -> None:
        self.assertEqual(self.window.data_mode, "real")
        self.assertIs(self.window.real_library_adapter.repository, self.services.repository)
        self.assertEqual(self.window.settings_bridge.settings_path, self.settings_file)
        self.assertIs(self.window.playback_adapter, self.services.playback_adapter)
        self.assertIs(self.window.lyrics_adapter, self.services.lyrics_adapter)
        self.assertFalse(self.window.playback_adapter._timer_enabled)
        self.assertTrue(self.window.library_collection.read_only)
        self.assertTrue(self.window.playlist_adapter.read_only)
        self.assertEqual(self.window.settings_bridge.value(self.window._settings_snapshot, "volume"), 42)

    def test_production_v2_uses_persisted_light_appearance(self) -> None:
        self.window.close()
        self.app.processEvents()
        _write_json(self.settings_file, {"appearance_mode": "light", "volume": 42})
        self.window = create_ui_v2_main_window(
            data_mode="real",
            services=self.services,
            initialize_storage=False,
        )
        self.assertEqual(self.window.theme.mode, "light")
        self.assertEqual(self.window.immersive_lyrics_options.theme, "light")

    def test_real_read_only_player_keeps_navigation_entry_points_enabled(self) -> None:
        bar = self.window.player_bar
        self.assertTrue(bar.lyrics_button.isEnabled())
        self.assertTrue(bar.queue_button.isEnabled())
        self.assertFalse(bar.play_button.isEnabled())
        self.assertFalse(bar.previous_button.isEnabled())
        self.assertFalse(bar.next_button.isEnabled())
        self.assertFalse(bar.shuffle_button.isEnabled())
        self.assertFalse(bar.repeat_button.isEnabled())

        bar.track_open_requested.emit()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "immersive_now_playing")
        self.window.navigation_adapter.set_route("browse")
        bar.lyrics_button.click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "immersive_lyrics")

    def test_real_routes_and_settings_cancel_do_not_write_user_documents(self) -> None:
        self.assertEqual(self.window.real_library_adapter.state, "loaded")
        self.window.router.page_for_route("browse")
        self.window.router.page_for_route("library")
        self.window.router.page_for_route("liked")
        self.window.router.page_for_route("artists")
        self.window.router.page_for_route("albums")
        self.window.router.page_for_route("playlist:road")
        self.window.navigation_adapter.set_route("immersive_now_playing")
        self.app.processEvents()
        self.assertEqual(self.window.presentation_mode.value, "immersive")
        self.window.navigation_adapter.set_route("immersive_lyrics")
        self.app.processEvents()
        self.assertEqual(self.window.presentation_mode.value, "immersive")
        self.window.navigation_adapter.set_route("browse")
        self.app.processEvents()
        self.assertEqual(self.window.presentation_mode.value, "normal")
        self.window.open_settings_overlay()
        self.app.processEvents()
        self.window.settings_overlay.cancel_and_close()
        self.app.processEvents()
        self.assertEqual(self.before_state, _file_state(self.document_paths))

    def test_page_switches_do_not_reload_repository(self) -> None:
        self.assertEqual(self.repository.load_count, 1)
        for route in ("library", "liked", "artists", "albums", "playlist:road", "browse"):
            self.window.navigation_adapter.set_route(route)
            self.app.processEvents()
        self.assertEqual(self.repository.load_count, 1)

    def test_real_read_only_mode_disables_write_and_network_surfaces(self) -> None:
        self.assertIn("online_search", self.window.sidebar._items)
        self.assertFalse(self.window.sidebar.new_playlist_button.isHidden())
        self.assertFalse(self.window.library_collection.set_favorite("missing", True))
        created = self.window.playlist_adapter.create_playlist("生产歌单")
        self.assertIsNotNone(created)
        assert created is not None
        self.assertTrue(self.window.playlist_adapter.rename_playlist(created.id, "生产歌单已重命名"))
        self.assertTrue(self.window.playlist_adapter.delete_playlist(created.id))
        self.assertEqual(
            {path: self.before_state[path] for path in (self.library_file, self.stats_file, self.remote_file, self.settings_file)},
            {path: _file_state(self.document_paths)[path] for path in (self.library_file, self.stats_file, self.remote_file, self.settings_file)},
        )

    def test_empty_real_library_starts_with_formal_empty_state(self) -> None:
        self.window.close()
        self.app.processEvents()
        _write_json(self.library_file, [])
        self.repository = CountingRepository(
            self.library_file,
            self.playlists_file,
            self.stats_file,
        )
        self.services = UiV2RuntimeServices(
            paths=self.paths,
            settings_path=self.settings_file,
            repository=self.repository,
            remote_tracks=RemoteTrackStore(self.remote_file),
            playback_adapter=PlaybackAdapter(timer_enabled=False),
            lyrics_adapter=LyricsAdapter(),
        )
        self.window = create_ui_v2_main_window(
            data_mode="real",
            services=self.services,
            initialize_storage=False,
        )
        self.window.show()
        self.assertTrue(self._wait_for(lambda: self.window.real_library_adapter.state == "empty"))
        self.assertEqual(self.window.library_page.current_view_state, "empty")

    def test_mock_v2_startup_still_uses_shared_factory_without_real_repository(self) -> None:
        self.window.close()
        self.app.processEvents()
        self.window = create_ui_v2_main_window(data_mode="mock", initialize_storage=False)
        self.window.show()
        self.app.processEvents()
        self.assertEqual(self.window.data_mode, "mock")
        self.assertIsNone(self.window.real_library_adapter)
        self.assertGreater(len(self.window.library_collection.tracks()), 0)
        self.assertIn("HushPlayer-ui-v2", str(self.window.settings_bridge.settings_path))
        self.assertNotIn(str(self.app_data), str(self.window.settings_bridge.settings_path))

    def test_factory_builds_formal_services_from_one_app_paths_source(self) -> None:
        services = build_ui_v2_runtime_services(self.paths)
        self.assertEqual(services.settings_path, self.settings_file)
        self.assertEqual(services.repository.library_file, self.library_file)
        self.assertEqual(services.repository.playlists_file, self.playlists_file)
        self.assertEqual(services.repository.stats_file, self.stats_file)
        self.assertFalse(services.playback_adapter._timer_enabled)

    def test_packaging_default_entry_remains_main_py(self) -> None:
        debug_spec = (PROJECT_ROOT / "packaging" / "HushPlayer.debug.spec").read_text(encoding="utf-8")
        release_spec = (PROJECT_ROOT / "packaging" / "HushPlayer.release.spec").read_text(encoding="utf-8")
        installer = (PROJECT_ROOT / "packaging" / "installer" / "HushPlayer.iss").read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT / "main.py"', debug_spec)
        self.assertIn('PROJECT_ROOT / "main.py"', release_spec)
        self.assertNotIn("main_v2.py", debug_spec)
        self.assertNotIn("main_v2.py", release_spec)
        self.assertIn(r'Filename: "{app}\{#MyAppExeName}"', installer)
        self.assertNotIn("--ui-v2", installer)


if __name__ == "__main__":
    unittest.main()
