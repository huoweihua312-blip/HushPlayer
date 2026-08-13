"""Immutable semantic tokens for the approved UI V2 design system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ThemeMode = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Palette names are semantic so pages never invent a parallel surface system."""

    app_background: str
    window_background: str
    content_background: str
    sidebar_background: str
    titlebar_background: str
    playerbar_background: str
    surface_primary: str
    surface_secondary: str
    surface_elevated: str
    surface_hover: str
    surface_selected: str
    surface_pressed: str
    divider: str
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str
    icon_default: str
    icon_hover: str
    icon_active: str
    progress_track: str
    progress_fill: str
    accent: str
    accent_hover: str
    accent_pressed: str
    focus_ring: str
    danger: str
    shadow: str
    overlay: str
    # Compatibility names used by protected, not-yet-migrated V2 pages.
    navigation_background: str
    elevated_background: str
    player_background: str
    input_background: str
    primary_text: str
    secondary_text: str
    subtle_text: str
    disabled_text: str
    border: str
    border_strong: str
    selected_background: str
    playing_background: str
    hover_background: str
    warning: str
    success: str


@dataclass(frozen=True, slots=True)
class ThemeMetrics:
    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 16
    spacing_xl: int = 24
    radius_sm: int = 5
    radius_md: int = 7
    radius_lg: int = 10
    page_margin: int = 30
    control_height: int = 38
    icon_sm: int = 16
    icon_md: int = 20
    icon_lg: int = 24
    title_bar_height: int = 59
    sidebar_width: int = 220
    compact_sidebar_width: int = 188
    player_bar_height: int = 102
    content_safe_bottom: int = 18


@dataclass(frozen=True, slots=True)
class ThemeFonts:
    # The V2 baseline is intentionally one step above Qt's Windows default.
    # This keeps Chinese glyphs readable at 100% display scaling without
    # making the layout feel oversized on a 900px-wide window.
    page_title: int = 38
    section_title: int = 23
    body: int = 16
    secondary: int = 15
    caption: int = 13
    card_title: int = 15
    card_meta: int = 13
    player_title: int = 15
    player_meta: int = 13


@dataclass(frozen=True, slots=True)
class Theme:
    mode: ThemeMode
    colors: ThemeColors
    metrics: ThemeMetrics = ThemeMetrics()
    fonts: ThemeFonts = ThemeFonts()


LIGHT_THEME = Theme(
    mode="light",
    colors=ThemeColors(
        app_background="#f1f1ef", sidebar_background="#e4e4e2",
        window_background="#f1f1ef", content_background="#fafaf8",
        titlebar_background="#f1f1ef", playerbar_background="#efefed",
        surface_primary="#fafaf8", surface_secondary="#f0f0ee", surface_elevated="#ffffff",
        surface_hover="#e8e8e6", surface_selected="#dcdcd9", surface_pressed="#d2d2cf",
        divider="#d6d6d3", text_primary="#1f2021", text_secondary="#555759",
        text_tertiary="#747677", text_disabled="#a1a2a0", icon_default="#424345",
        icon_hover="#1f2021", icon_active="#7970d7", progress_track="#bdbebb", progress_fill="#1f2021", accent="#7970d7",
        accent_hover="#6d65c7", accent_pressed="#5d55af", focus_ring="#7970d7",
        danger="#a64e55", shadow="rgba(0, 0, 0, .18)", overlay="rgba(0, 0, 0, .38)",
        navigation_background="#e4e4e2",
        elevated_background="#ffffff", player_background="#efefed",
        input_background="#ffffff", primary_text="#1f2021", secondary_text="#555759",
        subtle_text="#747677", disabled_text="#a1a2a0", border="#d6d6d3",
        border_strong="#bdbebb", selected_background="#dcdcd9", playing_background="#e5e3f6",
        hover_background="#e8e8e6", warning="#9a6918", success="#277b50",
    ),
)


DARK_THEME = Theme(
    mode="dark",
    colors=ThemeColors(
        app_background="#111214", sidebar_background="#151618",
        window_background="#111214", content_background="#111214",
        titlebar_background="#111214", playerbar_background="#1a1c1e",
        surface_primary="#17191b", surface_secondary="#1d1f21", surface_elevated="#252729",
        surface_hover="#2d2f32", surface_selected="#2b2d30", surface_pressed="#35373a",
        divider="#292b2e", text_primary="#f4f3f2", text_secondary="#b0afb0",
        text_tertiary="#858689", text_disabled="#606166", icon_default="#c2c1c2",
        icon_hover="#f4f3f2", icon_active="#a995e8", progress_track="#43464a", progress_fill="#f4f3f2", accent="#a995e8",
        accent_hover="#b9a8f1", accent_pressed="#8e7bd1", focus_ring="#b9a8f1",
        danger="#9e575a", shadow="rgba(0, 0, 0, .55)", overlay="rgba(0, 0, 0, .48)",
        navigation_background="#151618",
        elevated_background="#252729", player_background="#1a1c1e",
        input_background="#252729", primary_text="#f4f3f2", secondary_text="#b0afb0",
        subtle_text="#858689", disabled_text="#606166", border="#292b2e",
        border_strong="#43464a", selected_background="#2b2d30", playing_background="#252238",
        hover_background="#2d2f32", warning="#b38437", success="#74a888",
    ),
)


def get_theme(mode: str) -> Theme:
    """Resolve one complete V2 theme without mutable globals."""

    return LIGHT_THEME if mode == "light" else DARK_THEME
