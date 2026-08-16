from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.appearance_settings import (
    DEFAULT_APPEARANCE_MODE,
    ImmersiveAppearanceConfig,
    normalize_appearance_mode,
)


class AppearanceSettingsTests(unittest.TestCase):
    def test_defaults_and_round_trip_preserve_shared_shape(self) -> None:
        config = ImmersiveAppearanceConfig.defaults()

        self.assertEqual(config.background_mode, "cover")
        self.assertEqual(config.lyrics_font_scale, 100)
        self.assertEqual(
            ImmersiveAppearanceConfig.from_settings(config.to_settings()),
            config,
        )

    def test_legacy_keys_and_values_are_migrated_safely(self) -> None:
        config = ImmersiveAppearanceConfig.from_settings(
            {
                "immersive_cover_background_enabled": False,
                "immersive_background_alpha": 120,
                "immersive_lyrics_font_scale": 163,
                "immersive_background_blur": -5,
            }
        )

        self.assertEqual(config.background_mode, "default")
        self.assertEqual(config.darkness, 90)
        self.assertEqual(config.lyrics_font_scale, 160)
        self.assertEqual(config.blur_radius, 0)

    def test_appearance_mode_normalization_has_safe_default(self) -> None:
        self.assertEqual(normalize_appearance_mode(" LIGHT "), "light")
        self.assertEqual(normalize_appearance_mode("unknown"), DEFAULT_APPEARANCE_MODE)
        self.assertEqual(normalize_appearance_mode(None), DEFAULT_APPEARANCE_MODE)


if __name__ == "__main__":
    unittest.main()
