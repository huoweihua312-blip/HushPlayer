"""Formal Settings controls retain their transaction contract after B2 presentation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui_v2.adapters.legacy_settings_bridge import LegacySettingsBridge, SettingsBridgeError
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.settings_overlay import SettingsOverlay


class B2SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "settings.json"
        self.path.write_text(json.dumps({"appearance_mode": "dark", "unknown_key": 7}), encoding="utf8")
        self.original = self.path.read_bytes()
        self.calls = []
        self.host = QWidget()
        self.host.resize(1450, 740)
        self.bridge = LegacySettingsBridge(self.path, action_callbacks={"clear_all_audio_cache": lambda: self.calls.append("clear")})
        self.preview = []
        def preview(snapshot):
            self.preview.append(snapshot)
            self.overlay.set_theme(get_theme(snapshot["appearance_mode"]))
        self.overlay = SettingsOverlay(self.bridge, get_theme("dark"), preview_callback=preview, parent=self.host)
        self.host.show()
        self.overlay.open()
        self.app.processEvents()

    def tearDown(self):
        self.host.hide()
        self.host.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_preview_cancel_restores_original_without_write(self):
        self.overlay.set_category("appearance")
        self.overlay.set_appearance_mode("light")
        self.assertEqual(self.overlay._theme.mode, "light")
        self.assertTrue(self.overlay.is_dirty)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.overlay.request_close()
        self.assertTrue(self.overlay.confirm_dialog.isVisible())
        self.overlay.confirm_dialog.discard_button.click()
        self.assertEqual(self.preview[-1]["appearance_mode"], "dark")
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_failed_save_keeps_draft_and_retry_preserves_unknown_fields(self):
        self.overlay._controls["reduce_motion"].click()
        draft = self.overlay.session.working_snapshot.to_dict()
        with patch.object(self.bridge, "save_snapshot", side_effect=SettingsBridgeError("磁盘写入失败")):
            self.assertFalse(self.overlay.save())
        self.assertEqual(self.overlay.session.working_snapshot.to_dict(), draft)
        self.assertTrue(self.overlay.footer.save_button.isEnabled())
        self.assertEqual(self.overlay.footer.state, "failed")
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(self.overlay.save())
        self.assertEqual(json.loads(self.path.read_text())["unknown_key"], 7)
        self.assertFalse(self.overlay.is_dirty)

    def test_destructive_confirmation_and_cancel_do_not_execute_action(self):
        self.overlay.set_category("cache")
        self.overlay._run_action("clear_all_audio_cache")
        self.assertTrue(self.overlay.confirm_dialog.isVisible())
        self.assertEqual(self.calls, [])
        self.overlay.confirm_dialog.cancel_button.click()
        self.assertEqual(self.calls, [])
        self.overlay._run_action("clear_all_audio_cache")
        self.overlay.confirm_dialog.confirm_button.click()
        self.assertEqual(self.calls, ["clear"])
        self.assertFalse(self.overlay.is_dirty)

    def test_invalid_path_reset_and_cancel_preserve_saved_path(self):
        self.overlay.set_category("cache")
        picker = self.overlay._path_controls["cache_directory"].picker
        picker.set_path("relative/cache")
        self.assertFalse(self.overlay.save())
        self.assertTrue(self.overlay.is_dirty)
        picker.clear_button.click()
        self.assertEqual(picker.path(), "")
        self.overlay.cancel_and_close()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_all_toggle_hit_regions_and_keyboard_remain_operable(self):
        toggle = self.overlay._controls["remember_close_choice"]
        for x in (3, 20, 37):
            before = toggle.isChecked()
            QTest.mouseClick(toggle, Qt.MouseButton.LeftButton, pos=QPoint(x, 12))
            self.assertNotEqual(toggle.isChecked(), before)
        toggle.setFocus()
        before = toggle.isChecked()
        QTest.keyClick(toggle, Qt.Key.Key_Space)
        self.assertNotEqual(toggle.isChecked(), before)

    def test_dark_light_geometry_and_1000_breakpoint_keep_controls_inside_dialog(self):
        for width in (1450, 1080, 1000, 999, 900):
            shapes = []
            for mode in ("dark", "light"):
                self.host.resize(width, 740)
                self.overlay.sync_geometry(self.host.rect())
                self.overlay.set_theme(get_theme(mode))
                self.overlay.set_responsive_reference_width(width)
                self.overlay.set_category("lyrics")
                self.app.processEvents()
                shapes.append((self.overlay.dialog.geometry(), self.overlay.sidebar.width(), self.overlay.footer.height()))
                self.assertTrue(self.overlay.rect().contains(self.overlay.dialog.geometry()))
                self.assertTrue(self.overlay.dialog.rect().contains(self.overlay.footer.geometry()))
                for row in self.overlay._rows:
                    if row.isVisibleTo(self.overlay):
                        self.assertGreater(row.control.width(), 0)
                        self.assertLessEqual(row.control.mapTo(self.overlay.dialog, QPoint(row.control.width(), 0)).x(), self.overlay.dialog.width())
                self.assertEqual(self.overlay.sidebar._compact, width < 1000)
            self.assertEqual(shapes[0], shapes[1])


if __name__ == "__main__":
    unittest.main()
