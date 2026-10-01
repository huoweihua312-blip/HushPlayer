from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.velopack_runtime import (
    VELOPACK_DEFAULT_UPDATE_SOURCE,
    create_update_manager,
    is_velopack_enabled,
    is_velopack_install,
    velopack_update_source,
)


class VelopackRuntimeTests(unittest.TestCase):
    def test_default_source_is_available_for_packaged_builds(self) -> None:
        previous = os.environ.pop("HUSHPLAYER_VELOPACK_UPDATE_SOURCE", None)
        try:
            self.assertEqual(velopack_update_source(), VELOPACK_DEFAULT_UPDATE_SOURCE)
        finally:
            if previous is not None:
                os.environ["HUSHPLAYER_VELOPACK_UPDATE_SOURCE"] = previous

    def test_environment_source_overrides_default(self) -> None:
        previous = os.environ.get("HUSHPLAYER_VELOPACK_UPDATE_SOURCE")
        try:
            os.environ["HUSHPLAYER_VELOPACK_UPDATE_SOURCE"] = "http://127.0.0.1:8765"
            self.assertEqual(velopack_update_source(), "http://127.0.0.1:8765")
        finally:
            if previous is None:
                os.environ.pop("HUSHPLAYER_VELOPACK_UPDATE_SOURCE", None)
            else:
                os.environ["HUSHPLAYER_VELOPACK_UPDATE_SOURCE"] = previous

    def test_github_source_uses_prerelease_channel(self) -> None:
        with patch("velopack.GithubSource", return_value="github-source") as source:
            with patch("velopack.UpdateManager", return_value="manager") as manager:
                self.assertEqual(
                    create_update_manager(VELOPACK_DEFAULT_UPDATE_SOURCE),
                    "manager",
                )
        source.assert_called_once_with(VELOPACK_DEFAULT_UPDATE_SOURCE, prerelease=True)
        manager.assert_called_once_with("github-source")

    def test_detects_current_directory_with_updater_in_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current"
            current.mkdir()
            executable = current / "HushPlayer.exe"
            executable.touch()
            (root / "Update.exe").touch()
            (current / "sq.version").write_text("1", encoding="utf-8")
            self.assertTrue(is_velopack_install(executable))

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
