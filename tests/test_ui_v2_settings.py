from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from app.core.version import APP_NAME, APP_VERSION
from app.ui_v2.adapters.legacy_settings_bridge import (
    DEFAULT_SETTINGS,
    LegacySettingsBridge,
    SettingsBridgeError,
)
from app.ui_v2.models.settings_category import SETTINGS_CATEGORIES
from app.ui_v2.models.settings_edit_session import SettingsEditSession
from app.ui_v2.models.settings_snapshot import SettingsSnapshot
from app.ui_v2.shell.main_window import MainWindow
from app.ui_v2.theme.icons import FLUENT_SETTINGS_ASSETS


class SettingsContractTests(unittest.TestCase):
    def test_snapshot_and_edit_session_do_not_write_until_save(self) -> None:
        original = SettingsSnapshot.from_mapping(
            {**DEFAULT_SETTINGS, "unknown_legacy_key": {"keep": True}}
        )
        session = SettingsEditSession.open(original)
        session.set("appearance_mode", "light")
        self.assertTrue(session.is_dirty)
        self.assertEqual(original.get("appearance_mode"), "dark")
        self.assertTrue(session.get("unknown_legacy_key")["keep"])
        restored = session.cancel()
        self.assertEqual(restored.get("appearance_mode"), "dark")
        self.assertFalse(session.is_dirty)

    def test_bridge_uses_one_path_and_preserves_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps({"appearance_mode": "dark", "legacy_flag": 7}),
                encoding="utf-8",
            )
            applied: list[dict[str, object]] = []
            bridge = LegacySettingsBridge(path, apply_callback=applied.append)
            snapshot = bridge.read_snapshot()
            saved = bridge.save_snapshot(snapshot.with_updates({"appearance_mode": "light"}))
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved.get("appearance_mode"), "light")
            self.assertEqual(document["legacy_flag"], 7)
            self.assertEqual(len(applied), 1)
            self.assertEqual(path.parent.joinpath("settings.json"), bridge.settings_path)
            self.assertEqual(list(path.parent.glob("*.json")), [path])

    def test_bridge_save_failure_is_reported_without_second_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            bridge = LegacySettingsBridge(path)
            snapshot = bridge.read_snapshot().with_updates({"floating_lyrics_width": 1})
            with self.assertRaises(SettingsBridgeError):
                bridge.save_snapshot(snapshot)
            self.assertFalse(path.exists())


class SettingsOverlayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.tempdir.name) / "settings.json"
        self.previous_path = os.environ.get("HUSHPLAYER_UI_V2_SETTINGS_PATH")
        os.environ["HUSHPLAYER_UI_V2_SETTINGS_PATH"] = str(self.settings_path)
        self.window = MainWindow()
        self.window.playback_adapter._timer_enabled = False
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        if self.previous_path is None:
            os.environ.pop("HUSHPLAYER_UI_V2_SETTINGS_PATH", None)
        else:
            os.environ["HUSHPLAYER_UI_V2_SETTINGS_PATH"] = self.previous_path
        self.tempdir.cleanup()

    def open_overlay(self):
        self.window.open_settings_overlay()
        self.app.processEvents()
        return self.window.settings_overlay

    def test_settings_categories_use_distinct_local_fluent_regular_assets(self) -> None:
        overlay = self.open_overlay()
        expected_assets = {
            "general": "settings_20_regular.svg",
            "appearance": "paint_brush_20_regular.svg",
            "playback": "play_circle_20_regular.svg",
            "lyrics": "subtitles_20_regular.svg",
            "library": "library_20_regular.svg",
            "cache": "database_20_regular.svg",
            "updates": "arrow_sync_20_regular.svg",
            "about": "info_20_regular.svg",
        }
        category_names = [item.icon_name for item in SETTINGS_CATEGORIES]
        self.assertEqual(len(category_names), 8)
        self.assertEqual(len(set(category_names)), 8)
        self.assertEqual({name: FLUENT_SETTINGS_ASSETS[name] for name in category_names}, expected_assets)
        self.assertEqual(FLUENT_SETTINGS_ASSETS["dismiss"], "dismiss_20_regular.svg")
        self.assertTrue(all(name in FLUENT_SETTINGS_ASSETS for name in category_names))
        self.assertTrue(all(FLUENT_SETTINGS_ASSETS[name].endswith("_20_regular.svg") for name in category_names))
        asset_root = PROJECT_ROOT / "app" / "ui_v2" / "assets" / "icons" / "fluent_settings"
        manifest = json.loads((asset_root / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.1.334")
        self.assertEqual(manifest["render_size_px"], 18)
        self.assertTrue(all((asset_root / filename).is_file() for filename in FLUENT_SETTINGS_ASSETS.values()))
        self.assertEqual(overlay.sidebar._buttons["general"].iconSize(), QSize(18, 18))
        self.assertFalse(overlay.sidebar._buttons["general"].icon().isNull())

    def test_settings_selected_state_keeps_icon_file_and_size_hint_stable(self) -> None:
        overlay = self.open_overlay()
        button = overlay.sidebar._buttons["general"]
        before = (button.sizeHint(), button.iconSize())
        overlay.set_category("about")
        self.app.processEvents()
        after = (button.sizeHint(), button.iconSize())
        self.assertEqual(before, after)
        self.assertFalse(button.icon().isNull())
        self.assertFalse(overlay.close_button.icon().isNull())
        self.assertEqual(overlay.close_button.iconSize(), QSize(18, 18))

    def test_dismiss_hover_is_neutral_and_keeps_32px_geometry(self) -> None:
        overlay = self.open_overlay()
        button = overlay.close_button
        before = (button.sizeHint(), button.iconSize())
        stylesheet = button.styleSheet().lower().replace(" ", "")
        self.assertIn("rgba(255,255,255,18)", stylesheet)
        self.assertIn("rgba(255,255,255,28)", stylesheet)
        self.assertIn(
            f"border:1pxsolid{overlay._theme.colors.focus_ring.lower()}",
            stylesheet,
        )
        self.assertEqual(button.minimumSize(), QSize(32, 32))
        self.assertEqual(button.maximumSize(), QSize(32, 32))
        self.app.processEvents()
        self.assertEqual(before, (button.sizeHint(), button.iconSize()))

    def test_about_uses_formal_version_source_without_development_copy(self) -> None:
        overlay = self.open_overlay()
        overlay.set_category("about")
        self.app.processEvents()
        page = overlay._category_pages["about"]
        visible_text = "\n".join(label.text() for label in page.findChildren(type(overlay.title_label)))
        self.assertIn(APP_NAME, visible_text)
        self.assertIn(APP_VERSION, visible_text)
        for forbidden in ("HushPlayer UI V2", "设置 3A", "mock", "demo", "preview", "fixture"):
            self.assertNotIn(forbidden.casefold(), visible_text.casefold())

    def test_formal_eight_categories_and_settings_does_not_change_route(self) -> None:
        overlay = self.open_overlay()
        self.assertEqual(tuple(item.key for item in SETTINGS_CATEGORIES), (
            "general", "appearance", "playback", "lyrics",
            "library", "cache", "updates", "about",
        ))
        self.assertNotIn("immersive", overlay.sidebar._buttons)
        self.assertEqual(self.window.navigation_adapter.route, "browse")
        self.assertTrue(overlay.isVisible())
        self.window.sidebar._items["settings"].click()
        self.app.processEvents()
        self.assertEqual(self.window.navigation_adapter.route, "browse")
        self.assertTrue(overlay.isVisible())

    def test_overlay_is_single_instance_and_resize_keeps_it(self) -> None:
        overlay = self.open_overlay()
        overlay_id = id(overlay)
        self.window.resize(900, 600)
        self.app.processEvents()
        self.assertEqual(id(self.window.settings_overlay), overlay_id)
        self.assertEqual(overlay.sidebar.minimumWidth(), 156)
        self.window.resize(1600, 900)
        self.app.processEvents()
        overlay.close()
        self.window.open_settings_overlay()
        self.app.processEvents()
        self.assertEqual(id(self.window.settings_overlay), overlay_id)

    def test_save_cancel_and_dirty_state_use_existing_settings_file(self) -> None:
        overlay = self.open_overlay()
        self.assertFalse(overlay.is_dirty)
        control = overlay._controls["auto_scan_music_folders_on_startup"]
        control.setChecked(not control.isChecked())
        self.app.processEvents()
        self.assertTrue(overlay.is_dirty)
        self.assertTrue(overlay.footer.save_button.isEnabled())
        overlay.cancel_and_close()
        self.assertFalse(self.settings_path.exists())
        overlay.open()
        self.app.processEvents()
        self.assertTrue(overlay._controls["auto_scan_music_folders_on_startup"].isChecked())
        overlay._controls["auto_scan_music_folders_on_startup"].setChecked(False)
        overlay.save_and_close()
        self.app.processEvents()
        document = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertIs(document["auto_scan_music_folders_on_startup"], False)
        self.assertFalse(overlay.isVisible())

    def test_theme_preview_cancel_restores_runtime_without_persisting(self) -> None:
        overlay = self.open_overlay()
        combo = overlay._controls["appearance_mode"]
        combo.setCurrentIndex(combo.findData("light"))
        self.app.processEvents()
        self.assertEqual(self.window.theme.mode, "light")
        overlay.cancel_and_close()
        self.app.processEvents()
        self.assertEqual(self.window.theme.mode, "dark")
        self.assertFalse(self.settings_path.exists())

    def test_invalid_save_keeps_dirty_session(self) -> None:
        overlay = self.open_overlay()
        overlay._session.set("floating_lyrics_width", 1)
        overlay._refresh_state()
        self.assertFalse(overlay.footer.save_button.isEnabled())
        overlay.save_and_close()
        self.assertTrue(overlay.isVisible())
        self.assertTrue(overlay.is_dirty)

    def test_footer_save_keeps_overlay_open_and_clears_dirty_state(self) -> None:
        overlay = self.open_overlay()
        control = overlay._controls["auto_scan_music_folders_on_startup"]
        control.setChecked(not control.isChecked())
        self.app.processEvents()
        overlay.footer.save_button.click()
        self.app.processEvents()
        self.assertTrue(overlay.isVisible())
        self.assertFalse(overlay.is_dirty)
        self.assertEqual(overlay.footer.state, "success")
        self.assertFalse(overlay.footer.save_button.isEnabled())

    def test_dirty_close_uses_inline_confirmation_and_discard_rolls_back(self) -> None:
        overlay = self.open_overlay()
        control = overlay._controls["auto_scan_music_folders_on_startup"]
        control.setChecked(not control.isChecked())
        self.app.processEvents()
        overlay.request_close()
        self.assertTrue(overlay.isVisible())
        self.assertTrue(overlay.confirm_dialog.isVisible())
        self.assertFalse(overlay.confirm_dialog.confirm_button.isVisible())
        overlay.confirm_dialog.discard_button.click()
        self.app.processEvents()
        self.assertFalse(overlay.isVisible())
        self.assertFalse(self.settings_path.exists())

    def test_topbar_theme_toggle_joins_open_edit_session(self) -> None:
        overlay = self.open_overlay()
        original = self.window.theme.mode
        self.window.toggle_theme()
        self.app.processEvents()
        self.assertNotEqual(self.window.theme.mode, original)
        self.assertTrue(overlay.is_dirty)
        self.assertFalse(self.settings_path.exists())
        overlay.cancel_and_close()
        self.app.processEvents()
        self.assertEqual(self.window.theme.mode, original)

    def test_actions_are_not_dirty_and_unavailable_services_are_disabled(self) -> None:
        overlay = self.open_overlay()
        overlay.set_category("cache")
        self.app.processEvents()
        self.assertFalse(overlay.is_dirty)
        self.assertTrue(all(not button.isEnabled() for button in overlay.findChildren(type(overlay.footer.save_button)) if button.text() in {
            "清理封面 / 歌词失败缓存", "打开音频缓存目录", "清理未完成音频缓存", "清理全部音频缓存"
        }))


if __name__ == "__main__":
    unittest.main()
