"""Shared desktop-lyrics setting values without UI-layer imports."""

from __future__ import annotations

from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES


DESKTOP_LYRICS_COLORS: dict[str, str] = {
    "white": "#F7F7F3",
    "black": "#101114",
    "yellow": "#F7D774",
    "blue": "#8CC8FF",
    "green": "#8ED9A5",
    "pink": "#F3A6C7",
    "purple": "#C7A7FF",
}

DESKTOP_LYRICS_QUICK_SETTING_KEYS = (
    "floating_lyrics_color",
    "floating_lyrics_font_family",
    "floating_lyrics_font_size",
    "floating_lyrics_opacity",
    "floating_lyrics_width",
    "floating_lyrics_passthrough",
)


def normalize_desktop_lyrics_font(value: object) -> str:
    """Return only one of the bundled open-font families."""

    candidate = str(value or "").strip()
    return candidate if candidate in OPEN_FONT_FAMILIES else OPEN_FONT_FAMILIES[0]
