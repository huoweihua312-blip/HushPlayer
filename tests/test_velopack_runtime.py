from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.services.velopack_runtime import (
    is_velopack_enabled,
    is_velopack_install,
)


class VelopackRuntimeTests(unittest.TestCase):
    def test_detects_velopack_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "HushPlayer.exe"
            executable.touch()
            (root / "Update.exe").touch()
            (root / "sq.version").write_text("1", encoding="utf-8")

            self.assertTrue(is_velopack_install(executable))


    def test_regular_directory_is_not_velopack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "HushPlayer.exe"
            executable.touch()

            self.assertFalse(is_velopack_install(executable))


    def test_explicit_enable_and_disable_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "HushPlayer.exe"
            executable.touch()
            previous_enable = os.environ.get("HUSHPLAYER_ENABLE_VELOPACK")
            previous_disable = os.environ.get("HUSHPLAYER_DISABLE_VELOPACK")
            try:
                os.environ["HUSHPLAYER_ENABLE_VELOPACK"] = "1"
                os.environ.pop("HUSHPLAYER_DISABLE_VELOPACK", None)
                self.assertTrue(is_velopack_enabled(executable))

                os.environ["HUSHPLAYER_DISABLE_VELOPACK"] = "true"
                self.assertFalse(is_velopack_enabled(executable))
            finally:
                if previous_enable is None:
                    os.environ.pop("HUSHPLAYER_ENABLE_VELOPACK", None)
                else:
                    os.environ["HUSHPLAYER_ENABLE_VELOPACK"] = previous_enable
                if previous_disable is None:
                    os.environ.pop("HUSHPLAYER_DISABLE_VELOPACK", None)
                else:
                    os.environ["HUSHPLAYER_DISABLE_VELOPACK"] = previous_disable
