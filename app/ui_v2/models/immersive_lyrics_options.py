"""In-memory visual preferences for the formal immersive lyrics page."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ImmersiveLyricsOptions:
    """Keeps accepted immersive visual settings without touching user settings."""

    theme: str = "dark"
    background_mode: str = "artwork"
    background_opacity: int = 55
    overlay_strength: int = 45
    control_surface_opacity: int = 35
    lyrics_protection_enabled: bool = True
    protection_strength: int = 58
    global_font_scale: int = 100
    active_font_size: int = 46
    normal_font_size: int = 30
    translation_font_size: int = 14
    romanization_font_size: int = 15
    font_weight: str = "Semibold"
    inactive_lyric_opacity: int = 68
    text_protection_mode: str = "轻微阴影"
    artwork_size: int = 100
    lyrics_max_width: int = 780
    controls_auto_hide: bool = True
    background_blur: int = 40
    background_darkness: int = 68
    background_image_opacity: int = 100
    background_transparency: int = 38
    background_custom_path: str = ""

    def update(self, **values: object) -> None:
        """Apply known values only; the model intentionally has no persistence."""
        for name, value in values.items():
            if hasattr(self, name):
                setattr(self, name, value)
