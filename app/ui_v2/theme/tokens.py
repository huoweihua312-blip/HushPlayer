"""Single semantic token system for the approved Quiet Orbit shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ThemeMode = Literal["light", "dark"]


FONT_FALLBACKS = (
    # Windows UI fonts stay ahead of the optional cross-platform families so
    # Chinese glyphs keep stable proportions and hinting on high-DPI screens.
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI Variable Text",
    "Segoe UI",
    "DengXian",
    "MiSans",
    "MiSans VF",
    "HarmonyOS Sans SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "sans-serif",
)


def resolve_font_family() -> str:
    """Return the first approved family installed on this machine."""

    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        if QGuiApplication.instance() is None:
            return "Segoe UI"
        installed = set(QFontDatabase.families())
    except Exception:
        installed = set()
    for family in FONT_FALLBACKS:
        if family == "sans-serif" or family in installed:
            return family
    return "sans-serif"


def font_family_qss() -> str:
    """Return the approved ordered stack without requiring a QApplication."""

    return ", ".join(f'"{family}"' for family in FONT_FALLBACKS)


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Semantic colors shared by every Q1 shell surface and control."""

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
    radius_sm: int = 8
    radius_md: int = 10
    radius_lg: int = 16
    page_margin: int = 32
    control_height: int = 40
    icon_sm: int = 16
    icon_md: int = 20
    icon_lg: int = 24
    title_bar_height: int = 59
    sidebar_width: int = 220
    compact_sidebar_width: int = 76
    player_bar_height: int = 102
    content_safe_bottom: int = 18


@dataclass(frozen=True, slots=True)
class ThemeFonts:
    caption: int = 13
    body_small: int = 13
    body: int = 15
    control: int = 14
    section_title: int = 22
    page_title: int = 32
    track_title: int = 15
    metadata: int = 13
    numeric: int = 13
    secondary: int = 14
    card_title: int = 14
    card_meta: int = 13
    player_title: int = 14
    player_meta: int = 13
    family: str = "Microsoft YaHei UI"


@dataclass(frozen=True, slots=True)
class Theme:
    mode: ThemeMode
    colors: ThemeColors
    metrics: ThemeMetrics = ThemeMetrics()
    fonts: ThemeFonts = ThemeFonts()


def _colors(
    *,
    app: str,
    sidebar: str,
    content: str,
    player: str,
    surface: str,
    surface_secondary: str,
    elevated: str,
    hover: str,
    selected: str,
    playing: str,
    pressed: str,
    divider: str,
    primary: str,
    secondary: str,
    tertiary: str,
    disabled: str,
    icon: str,
    active: str,
    progress_track: str,
    accent: str,
    accent_hover: str,
    accent_pressed: str,
    danger: str,
    warning: str,
    success: str,
    shadow: str,
    overlay: str,
) -> ThemeColors:
    return ThemeColors(
        app_background=app,
        window_background=app,
        content_background=content,
        sidebar_background=sidebar,
        titlebar_background=app,
        playerbar_background=player,
        surface_primary=surface,
        surface_secondary=surface_secondary,
        surface_elevated=elevated,
        surface_hover=hover,
        surface_selected=selected,
        surface_pressed=pressed,
        divider=divider,
        text_primary=primary,
        text_secondary=secondary,
        text_tertiary=tertiary,
        text_disabled=disabled,
        icon_default=icon,
        icon_hover=primary,
        icon_active=active,
        progress_track=progress_track,
        progress_fill=primary,
        accent=accent,
        accent_hover=accent_hover,
        accent_pressed=accent_pressed,
        focus_ring=accent,
        danger=danger,
        shadow=shadow,
        overlay=overlay,
        navigation_background=sidebar,
        elevated_background=elevated,
        player_background=player,
        input_background=elevated,
        primary_text=primary,
        secondary_text=secondary,
        subtle_text=tertiary,
        disabled_text=disabled,
        border=divider,
        border_strong=progress_track,
        selected_background=selected,
        playing_background=playing,
        hover_background=hover,
        warning=warning,
        success=success,
    )


LIGHT_THEME = Theme(
    mode="light",
    colors=_colors(
        app="#f2f5f1", sidebar="#e8eeea", content="#f6f8f4", player="#edf2ee",
        surface="#fbfdf9", surface_secondary="#eef2ed", elevated="#ffffff",
        hover="#e5ece7", selected="#dfe9e2", playing="#f0e7d3", pressed="#d3e0d7", divider="#d5ded7",
        primary="#172521", secondary="#40544b", tertiary="#63756d", disabled="#9aa8a0",
        icon="#50665d", active="#af8e4f", progress_track="#adbbb3", accent="#af8e4f",
        accent_hover="#c09f61", accent_pressed="#92743e", danger="#b5645d",
        warning="#92702e", success="#3d805e", shadow="rgba(31, 48, 41, .16)",
        overlay="rgba(31, 48, 41, .26)",
    ),
    fonts=ThemeFonts(),
)


DARK_THEME = Theme(
    mode="dark",
    colors=_colors(
        app="#0b1112", sidebar="#0d1516", content="#10191a", player="#121d1e",
        surface="#152123", surface_secondary="#182527", elevated="#1d2a2c",
        hover="#213032", selected="#1b2928", playing="#292719", pressed="#2a3839", divider="#283638",
        primary="#f0f4f0", secondary="#bdcac3", tertiary="#85958e", disabled="#65736e",
        icon="#cbd6d0", active="#c8a667", progress_track="#52625d", accent="#c8a667",
        accent_hover="#d8b877", accent_pressed="#a78950", danger="#e1887f",
        warning="#d4ad63", success="#86c49f", shadow="rgba(0, 0, 0, .52)",
        overlay="rgba(0, 0, 0, .46)",
    ),
    fonts=ThemeFonts(),
)


def get_theme(mode: str) -> Theme:
    """Resolve one complete immutable Quiet Orbit theme."""

    return LIGHT_THEME if str(mode).casefold() == "light" else DARK_THEME
