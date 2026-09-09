"""Font-engine selection must happen before the formal Qt startup."""

import os
import unittest
from unittest.mock import patch

from app.startup import configure_qt_runtime


class FontRuntimeTests(unittest.TestCase):
    def test_windows_default_is_selected_before_application_creation(self):
        with patch.dict(os.environ, {}, clear=True), patch("app.startup.sys.platform", "win32"), \
             patch("app.startup.QGuiApplication.instance", return_value=None):
            configure_qt_runtime()
            self.assertEqual(os.environ["QT_QPA_PLATFORM"], "windows:fontengine=freetype")

    def test_explicit_platforms_are_preserved(self):
        for platform in ("offscreen", "windows", "windows:fontengine=directwrite"):
            with self.subTest(platform=platform), patch.dict(os.environ, {"QT_QPA_PLATFORM": platform}), \
                 patch("app.startup.sys.platform", "win32"), \
                 patch("app.startup.QGuiApplication.instance", return_value=None):
                configure_qt_runtime()
                self.assertEqual(os.environ["QT_QPA_PLATFORM"], platform)

    def test_existing_application_does_not_change_platform_environment(self):
        with patch.dict(os.environ, {}, clear=True), patch("app.startup.sys.platform", "win32"), \
             patch("app.startup.QGuiApplication.instance", return_value=object()):
            configure_qt_runtime()
            self.assertNotIn("QT_QPA_PLATFORM", os.environ)


if __name__ == "__main__":
    unittest.main()
