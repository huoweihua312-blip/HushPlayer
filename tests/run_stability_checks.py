"""Run the focused desktop regression suite with isolated application data."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULES = (
    "tests.test_stability_optimizations",
    "tests.test_library_repository",
    "tests.test_ui_v2_real_library_adapter",
    "tests.test_ui_v2_track_model",
    "tests.test_ui_v2_library_family",
    "tests.test_ui_v2_settings",
    "tests.test_ui_v2_close_behavior",
    "tests.test_ui_v2_real_playback",
    "tests.test_ui_v2_real_actions",
    "tests.test_playback_session_store",
    "tests.test_library_removal_service",
    "tests.test_online_track_recovery",
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hushplayer-regression-") as directory:
        root = Path(directory)
        overrides = {
            "QT_QPA_PLATFORM": "offscreen",
            "HUSHPLAYER_APP_DATA_DIR": str(root / "appdata"),
            "HUSHPLAYER_CACHE_DIR": str(root / "cache"),
            "HUSHPLAYER_UI_V2_SETTINGS_PATH": str(root / "settings.json"),
            "HUSHPLAYER_UI_V2_DATA_MODE": "mock",
        }
        previous = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        try:
            # Import tests only after directing all default services away
            # from the user's music library and settings.
            suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    sys.exit(main())
