"""Shared visual tokens for HushPlayer's current dark-first UI.

Keep this module data-only so lightweight widgets can reuse the same design
language without importing the main window or creating another theme engine.
"""

from __future__ import annotations


DARK_THEME_TOKENS = {
    "app_bg": "#0d0f14",
    "shell_bg": "#141821",
    "sidebar_bg": "#10131a",
    "panel_bg": "#151922",
    "card_bg": "#151922",
    "card_bg_alt": "#1a1f2b",
    "card_bg_high": "#202631",
    "hover": "#202631",
    "active": "#252c3a",
    "selected_bg": "rgba(76, 141, 255, 0.18)",
    "selected_border": "rgba(76, 141, 255, 0.42)",
    "playing_bg": "rgba(76, 141, 255, 0.11)",
    "text": "#f3f4f6",
    "text_secondary": "#b5bbc7",
    "text_muted": "#8a92a3",
    "text_weak": "#8a92a3",
    "text_disabled": "#737d8f",
    "placeholder": "#7f8898",
    "border": "#2a303b",
    "border_strong": "#3a4352",
    "accent": "#4c8dff",
    "accent_hover": "#65a0ff",
    "accent_pressed": "#3978dd",
    "accent_soft": "rgba(76, 141, 255, 0.18)",
    "favorite": "#e15b64",
    "favorite_soft": "rgba(225, 91, 100, 0.16)",
    "warning": "#e8ad52",
    "error": "#e15b64",
    "danger": "#e15b64",
}


UI_RADII = {
    "small": 6,
    "control": 8,
    "button": 10,
    "card": 12,
    "panel": 16,
    "shell": 22,
}


UI_SPACING = {
    "xxs": 4,
    "xs": 8,
    "sm": 12,
    "md": 16,
    "lg": 20,
    "xl": 24,
}


UI_TYPOGRAPHY = {
    "page_title": 24,
    "section_title": 18,
    "body": 14,
    "secondary": 13,
    "caption": 12,
    "micro": 11,
}


UI_CONTROL_SIZES = {
    "navigation_height": 40,
    "navigation_icon": 18,
    "compact_button_height": 34,
    "icon_button": 36,
    "track_row_height": 58,
    "track_like_width": 28,
    "scrollbar_width": 10,
}
