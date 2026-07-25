"""Immutable semantic tokens used by every UI V2 component."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ThemeMode = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class ThemeColors:
    window_background: str
    navigation_background: str
    content_background: str
    elevated_background: str
    player_background: str
    input_background: str
    primary_text: str
    secondary_text: str
    subtle_text: str
    disabled_text: str
    border: str
    border_strong: str
    accent: str
    accent_hover: str
    accent_pressed: str
    selected_background: str
    playing_background: str
    hover_background: str
    danger: str
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
    radius_md: int = 8
    radius_lg: int = 12
    page_margin: int = 24
    control_height: int = 36
    icon_sm: int = 16
    icon_md: int = 20
    icon_lg: int = 24


@dataclass(frozen=True, slots=True)
class ThemeFonts:
    page_title: int = 22
    section_title: int = 16
    body: int = 14
    secondary: int = 13
    caption: int = 12


@dataclass(frozen=True, slots=True)
class Theme:
    mode: ThemeMode
    colors: ThemeColors
    metrics: ThemeMetrics = ThemeMetrics()
    fonts: ThemeFonts = ThemeFonts()


LIGHT_THEME = Theme(
    mode="light",
    colors=ThemeColors(
        window_background="#edf1f6",
        navigation_background="#e5eaf1",
        content_background="#f8fafc",
        elevated_background="#ffffff",
        player_background="#f4f7fa",
        input_background="#ffffff",
        primary_text="#1d2937",
        secondary_text="#4f6072",
        subtle_text="#718095",
        disabled_text="#9aa7b7",
        border="#d7dfe9",
        border_strong="#b7c4d2",
        accent="#2d73cf",
        accent_hover="#2165be",
        accent_pressed="#1955a5",
        selected_background="#e7eef5",
        playing_background="#eaf2f8",
        hover_background="#eef3f8",
        danger="#bd4050",
        warning="#a96a12",
        success="#277b50",
    ),
)

DARK_THEME = Theme(
    mode="dark",
    colors=ThemeColors(
        window_background="#171b22",
        navigation_background="#1c222b",
        content_background="#202730",
        elevated_background="#252e38",
        player_background="#1d242d",
        input_background="#202832",
        primary_text="#edf2f7",
        secondary_text="#bec8d4",
        subtle_text="#8996a6",
        disabled_text="#687585",
        border="#35414f",
        border_strong="#4a5868",
        accent="#78aef8",
        accent_hover="#91bdff",
        accent_pressed="#5c99eb",
        selected_background="#293946",
        playing_background="#253640",
        hover_background="#2a3440",
        danger="#ef7882",
        warning="#e6ae57",
        success="#74c89a",
    ),
)


def get_theme(mode: str) -> Theme:
    """Resolve one of the two complete V2 themes without mutable globals."""
    return LIGHT_THEME if mode == "light" else DARK_THEME
