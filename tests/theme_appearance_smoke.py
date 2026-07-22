from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _smoke_storage import activate_isolated_app_storage


ISOLATED_STORAGE = activate_isolated_app_storage("hushplayer-theme-")

from PySide6.QtWidgets import QApplication

from app.services.app_update_service import UpdateManifest
from app.ui.design_system import DARK_THEME_TOKENS, LIGHT_THEME_TOKENS
from app.ui.main_window import MainWindow, SettingsDialog
from app.ui.theme_manager import (
    ThemeManager,
    normalize_appearance_mode,
    resolve_appearance_mode,
)
from app.ui.update_dialog import UpdateDialog


_COLOR_PATTERN = re.compile(r"^(#[0-9a-fA-F]{6}|rgba\([^)]*\))$")


def _manifest() -> UpdateManifest:
    return UpdateManifest(
        schema_version=1,
        channel="beta",
        version="0.5.0-beta.999",
        numeric_version=(0, 5, 0, 999),
        numeric_version_text="0.5.0.999",
        architecture="win-x64",
        mandatory=False,
        setup_url="https://example.invalid/HushPlayer-test.exe",
        setup_size=1,
        sha256="0" * 64,
        release_notes=("浅色主题更新说明",),
        release_history=(),
    )


def _snapshot_file(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def run_test(app: QApplication) -> None:
    assert normalize_appearance_mode(None) == "dark"
    assert normalize_appearance_mode("dark") == "dark"
    assert normalize_appearance_mode("light") == "light"
    assert normalize_appearance_mode("system") == "system"
    assert normalize_appearance_mode("invalid") == "dark"
    assert resolve_appearance_mode("system", system_resolver=lambda: "light") == "light"
    assert resolve_appearance_mode("system", system_resolver=lambda: "dark") == "dark"
    assert resolve_appearance_mode("system", system_resolver=lambda: "unknown") == "dark"

    assert set(DARK_THEME_TOKENS) == set(LIGHT_THEME_TOKENS)
    for tokens in (DARK_THEME_TOKENS, LIGHT_THEME_TOKENS):
        assert all(_COLOR_PATTERN.match(value) for value in tokens.values())
        assert tokens["text_primary"] != tokens["window_background"]
    assert LIGHT_THEME_TOKENS["text_primary"] != LIGHT_THEME_TOKENS["surface"]

    manager = ThemeManager(app, system_resolver=lambda: "light")
    manager.set_appearance_mode("dark", force=True)
    before = int(app.property("hushApplicationThemeApplyCount") or 0)
    assert manager.set_appearance_mode("system") is True
    assert manager.resolved_mode == "light"
    assert manager.set_appearance_mode("system") is False
    assert int(app.property("hushApplicationThemeApplyCount") or 0) == before + 1
    manager.deleteLater()

    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        assert window.appearance_mode() == "dark"
        assert "appearance_mode" not in window.get_hush_settings()

        original_settings_file = window.settings_file
        invalid_settings_file = ISOLATED_STORAGE.root / "invalid-appearance.json"
        invalid_settings_file.write_text(
            json.dumps({"volume": 65, "play_mode": "list_loop", "appearance_mode": "unexpected"}),
            encoding="utf-8",
        )
        window.settings_file = invalid_settings_file
        assert window.load_settings()["appearance_mode"] == "dark"
        window.settings_file = original_settings_file

        original_files = {
            "library": _snapshot_file(window.library_file),
            "playlists": _snapshot_file(window.playlists_file),
            "stats": _snapshot_file(window.stats_file),
        }
        playback_snapshot = {
            "path": window.current_song_path,
            "position": window.media_player.position(),
            "queue": copy.deepcopy(window.play_queue),
            "playlists": copy.deepcopy(window.playlists),
        }
        window.set_appearance_mode("light", persist=False)
        app.processEvents()
        assert window.theme_manager.resolved_mode == "light"
        assert window.get_dark_theme_tokens()["window_background"] == LIGHT_THEME_TOKENS["window_background"]
        assert window.theme_quick_button.objectName() == "themeQuickButton"
        assert not window.theme_quick_button.icon().isNull()
        assert "单击在浅色和深色之间切换" in window.theme_quick_button.toolTip()
        theme_menu = window.create_theme_quick_menu()
        try:
            assert [action.data() for action in theme_menu.actions()] == [
                "system",
                "light",
                "dark",
            ]
            assert theme_menu.actions()[1].isChecked()
        finally:
            theme_menu.close()
            theme_menu.deleteLater()

        window.toggle_quick_appearance_mode()
        app.processEvents()
        assert window.appearance_mode() == "dark"
        assert window.theme_manager.resolved_mode == "dark"
        window.toggle_quick_appearance_mode()
        app.processEvents()
        assert window.appearance_mode() == "light"

        qss = window.styleSheet()
        assert f"color: {LIGHT_THEME_TOKENS['selection_text']}" in qss
        assert "QPushButton#themeQuickButton" in qss
        assert "QListWidget#pendingImportsList::item:selected" in qss
        assert "QPushButton#likeButton[liked=\"true\"]" in qss
        cover_image = window.cover_label.grab().toImage()
        cover_border = cover_image.pixelColor(
            max(2, cover_image.width() // 2),
            2,
        )
        assert max(cover_border.red(), cover_border.green(), cover_border.blue()) > 80
        assert window.current_song_path == playback_snapshot["path"]
        assert window.media_player.position() == playback_snapshot["position"]
        assert window.play_queue == playback_snapshot["queue"]
        assert window.playlists == playback_snapshot["playlists"]
        assert {name: _snapshot_file(path) for name, path in (
            ("library", window.library_file),
            ("playlists", window.playlists_file),
            ("stats", window.stats_file),
        )} == original_files

        window.set_appearance_mode("dark", persist=False)
        window.set_appearance_mode("light", persist=True)
        assert window.flush_settings() is True
        persisted = json.loads(window.settings_file.read_text(encoding="utf-8"))
        assert persisted["appearance_mode"] == "light"
        assert window.load_settings()["appearance_mode"] == "light"

        settings_dialog = SettingsDialog(window)
        try:
            assert settings_dialog.appearance_mode_combo.findData("system") >= 0
            assert settings_dialog.appearance_mode_combo.findData("light") >= 0
            assert settings_dialog.appearance_mode_combo.findData("dark") >= 0
            settings_dialog.appearance_mode_combo.setCurrentIndex(
                settings_dialog.appearance_mode_combo.findData("dark")
            )
            app.processEvents()
            assert window.theme_manager.resolved_mode == "dark"
        finally:
            settings_dialog.close()
            settings_dialog.deleteLater()

        update_dialog = UpdateDialog(window.update_service, _manifest(), window)
        try:
            window.set_appearance_mode("light", persist=False)
            app.processEvents()
            assert "浅色主题更新说明" in update_dialog.notes.toPlainText()
            assert update_dialog.palette().color(update_dialog.foregroundRole()).isValid()
        finally:
            update_dialog.close()
            update_dialog.deleteLater()
    finally:
        window.close()
        window.deleteLater()
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
        run_test(app)
        print("theme appearance smoke: OK")
        return 0
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore
        MainWindow.auto_scan_music_folders_on_startup = original_auto_scan


if __name__ == "__main__":
    raise SystemExit(main())
