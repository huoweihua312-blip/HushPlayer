"""Single semantic token system for the approved Quiet Orbit shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ThemeMode = Literal["light", "dark"]


FONT_FALLBACKS = (
    "MiSans",
    "MiSans VF",
    "HarmonyOS Sans SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Microsoft YaHei UI",
    "Segoe UI Variable Text",
    "Segoe UI",
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
    radius_sm: int = 6
    radius_md: int = 8
    radius_lg: int = 12
    page_margin: int = 30
    control_height: int = 38
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
    caption: int = 12
    body_small: int = 13
    body: int = 15
    control: int = 14
    section_title: int = 22
    page_title: int = 32
    track_title: int = 15
    metadata: int = 12
    numeric: int = 12
    secondary: int = 14
    card_title: int = 14
    card_meta: int = 12
    player_title: int = 14
    player_meta: int = 12
    family: str = "Segoe UI"


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
        app="#f7f6f1", sidebar="#e8eee9", content="#fbfaf6", player="#eef2ed",
        surface="#fbfaf6", surface_secondary="#f1f3ee", elevated="#ffffff",
        hover="#e7eee9", selected="#dce9e1", playing="#eee4cd", pressed="#d0e0d6", divider="#d7e1da",
        primary="#1d2925", secondary="#4f625a", tertiary="#74857d", disabled="#a0ada6",
        icon="#52665d", active="#b18d48", progress_track="#b7c5bc", accent="#b18d48",
        accent_hover="#c09d58", accent_pressed="#9d7b3c", danger="#b7665f",
        warning="#9a7228", success="#3e805e", shadow="rgba(31, 48, 41, .16)",
        overlay="rgba(31, 48, 41, .24)",
    ),
    fonts=ThemeFonts(),
)


DARK_THEME = Theme(
    mode="dark",
    colors=_colors(
        app="#101516", sidebar="#0c1012", content="#101516", player="#151c1e",
        surface="#151a1c", surface_secondary="#151c1e", elevated="#1d2527",
        hover="#222c2e", selected="#1a211f", playing="#28271f", pressed="#293536", divider="#222c2e",
        primary="#f1f5f2", secondary="#c7d2ce", tertiary="#899792", disabled="#5e6c68",
        icon="#d3ded9", active="#d6b879", progress_track="#5e6c68", accent="#d6b879",
        accent_hover="#e7ca8c", accent_pressed="#b89a5c", danger="#e08f86",
        warning="#d0a85e", success="#8dc6a2", shadow="rgba(0, 0, 0, .48)",
        overlay="rgba(0, 0, 0, .42)",
    ),
    fonts=ThemeFonts(),
)


def get_theme(mode: str) -> Theme:
    """Resolve one complete immutable Quiet Orbit theme."""

    return LIGHT_THEME if str(mode).casefold() == "light" else DARK_THEME
