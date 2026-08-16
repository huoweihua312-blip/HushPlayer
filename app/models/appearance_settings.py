"""Persistent appearance settings shared by the active UI and migrations."""

from __future__ import annotations

from dataclasses import dataclass


APPEARANCE_MODES = ("dark", "light", "system")
DEFAULT_APPEARANCE_MODE = "dark"

BACKGROUND_MODES = {"default", "cover", "translucent", "custom"}
BACKGROUND_FILL_MODES = {"cover", "contain"}
APPEARANCE_SETTING_KEYS = {
    "immersive_background_mode",
    "immersive_background_custom_path",
    "immersive_background_blur",
    "immersive_background_darkness",
    "immersive_background_image_opacity",
    "immersive_background_transparency",
    "immersive_background_fill_mode",
    "immersive_lyrics_font_scale",
    "immersive_cover_background_enabled",
    "immersive_background_alpha",
}


def normalize_appearance_mode(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in APPEARANCE_MODES else DEFAULT_APPEARANCE_MODE


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return int(default)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(int(minimum), min(int(maximum), number))


@dataclass(frozen=True, slots=True)
class ImmersiveAppearanceConfig:
    """Backward-compatible immersive visual settings value object."""

    background_mode: str = "cover"
    custom_image_path: str = ""
    blur_radius: int = 40
    darkness: int = 68
    image_opacity: int = 100
    background_transparency: int = 38
    fill_mode: str = "cover"
    lyrics_font_scale: int = 100

    @classmethod
    def defaults(cls) -> "ImmersiveAppearanceConfig":
        return cls()

    @classmethod
    def from_settings(cls, settings: dict | None) -> "ImmersiveAppearanceConfig":
        document = settings if isinstance(settings, dict) else {}
        defaults = cls.defaults()

        raw_mode = document.get("immersive_background_mode")
        if isinstance(raw_mode, str) and raw_mode.strip().casefold() in BACKGROUND_MODES:
            mode = raw_mode.strip().casefold()
        else:
            legacy_cover = document.get("immersive_cover_background_enabled", True)
            if not isinstance(legacy_cover, bool):
                legacy_cover = True
            mode = "cover" if legacy_cover else "default"

        raw_path = document.get("immersive_background_custom_path", "")
        custom_path = raw_path.strip() if isinstance(raw_path, str) else ""

        darkness_source = document.get(
            "immersive_background_darkness",
            document.get("immersive_background_alpha", defaults.darkness),
        )
        fill_mode = document.get("immersive_background_fill_mode", defaults.fill_mode)
        if (
            not isinstance(fill_mode, str)
            or fill_mode.strip().casefold() not in BACKGROUND_FILL_MODES
        ):
            fill_mode = defaults.fill_mode
        else:
            fill_mode = fill_mode.strip().casefold()

        font_scale = _bounded_int(
            document.get("immersive_lyrics_font_scale", defaults.lyrics_font_scale),
            defaults.lyrics_font_scale,
            70,
            160,
        )
        font_scale = max(70, min(160, int(round(font_scale / 5.0) * 5)))

        return cls(
            background_mode=mode,
            custom_image_path=custom_path,
            blur_radius=_bounded_int(
                document.get("immersive_background_blur", defaults.blur_radius),
                defaults.blur_radius,
                0,
                40,
            ),
            darkness=_bounded_int(darkness_source, defaults.darkness, 0, 90),
            image_opacity=_bounded_int(
                document.get(
                    "immersive_background_image_opacity",
                    defaults.image_opacity,
                ),
                defaults.image_opacity,
                20,
                100,
            ),
            background_transparency=_bounded_int(
                document.get(
                    "immersive_background_transparency",
                    defaults.background_transparency,
                ),
                defaults.background_transparency,
                0,
                85,
            ),
            fill_mode=fill_mode,
            lyrics_font_scale=font_scale,
        )

    def to_settings(self) -> dict:
        return {
            "immersive_background_mode": self.background_mode,
            "immersive_background_custom_path": self.custom_image_path,
            "immersive_background_blur": int(self.blur_radius),
            "immersive_background_darkness": int(self.darkness),
            "immersive_background_image_opacity": int(self.image_opacity),
            "immersive_background_transparency": int(self.background_transparency),
            "immersive_background_fill_mode": self.fill_mode,
            "immersive_lyrics_font_scale": int(self.lyrics_font_scale),
            # Keep old keys readable by older installations.
            "immersive_cover_background_enabled": self.background_mode == "cover",
            "immersive_background_alpha": int(self.darkness),
        }

    def background_render_signature(self) -> tuple:
        return (
            self.background_mode,
            self.custom_image_path,
            int(self.blur_radius),
            self.fill_mode,
        )
