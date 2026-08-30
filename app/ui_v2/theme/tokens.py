"""Single semantic token system for the approved Quiet Orbit shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ThemeMode = Literal["light", "dark"]


OPEN_FONT_FAMILIES = (
    "Source Han Sans SC",
    "Noto Sans SC",
)


FONT_FALLBACKS = (
    # Source Han Sans SC is bundled under SIL OFL 1.1.  Its static Medium and
    # Bold faces remain visibly distinct on Windows instead of relying on a
    # platform's variable-font weight synthesis.
    "Source Han Sans SC",
    # Keep the previous bundled font as a safe fallback for older packaged
    # layouts and environments that reject one of the static OTF faces.
    "Noto Sans SC",
    "MiSans",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI Variable Text",
    "Segoe UI",
    "DengXian",
    "HarmonyOS Sans SC",
    "Noto Sans CJK SC",
    "sans-serif",
)


_BUNDLED_FONT_PATHS = (
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "SourceHanSansSC-Regular.otf",
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "SourceHanSansSC-Medium.otf",
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "SourceHanSansSC-Bold.otf",
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-VF.ttf",
)
_BUNDLED_FONT_IDS: tuple[int, ...] = ()
_BUNDLED_FONT_ATTEMPTED = False


def _ensure_bundled_font_loaded() -> None:
    """Load the redistributable UI font once the Qt application exists."""

    global _BUNDLED_FONT_ATTEMPTED, _BUNDLED_FONT_IDS
    if _BUNDLED_FONT_IDS or _BUNDLED_FONT_ATTEMPTED:
        return
    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        if QGuiApplication.instance() is None:
            return
        _BUNDLED_FONT_ATTEMPTED = True
        loaded: list[int] = []
        for font_path in _BUNDLED_FONT_PATHS:
            if not font_path.is_file():
                continue
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                loaded.append(font_id)
        _BUNDLED_FONT_IDS = tuple(loaded)
    except Exception:
        # A system fallback is preferable to making startup dependent on an
        # optional font resource or a platform-specific font loader.
        _BUNDLED_FONT_ATTEMPTED = True


def resolve_font_family() -> str:
    """Return the first approved family installed on this machine."""

    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        if QGuiApplication.instance() is None:
            return "Segoe UI"
        _ensure_bundled_font_loaded()
        installed = set(QFontDatabase.families())
    except Exception:
        installed = set()
    for family in FONT_FALLBACKS:
        if family == "sans-serif" or family in installed:
            return family
    return "sans-serif"


def font_family_qss() -> str:
    """Return the approved ordered stack without requiring a QApplication."""

    _ensure_bundled_font_loaded()
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
    # Keep the Chinese UI one readable step above Qt's Windows default while
    # preserving the compact Quiet Orbit rhythm at 900px-wide windows.
    caption: int = 13
    body_small: int = 14
    body: int = 15
    control: int = 15
    section_title: int = 21
    page_title: int = 32
    hero_title: int = 36
    track_title: int = 16
    metadata: int = 14
    numeric: int = 14
    secondary: int = 15
    card_title: int = 15
    card_meta: int = 14
    player_title: int = 15
    player_meta: int = 14
    family: str = "Source Han Sans SC"


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
        app="#f4f4f2", sidebar="#ededeb", content="#f8f8f6", player="#f0f0ee",
        surface="#ffffff", surface_secondary="#f2f2f0", elevated="#ffffff",
        hover="#e9e9e7", selected="#e5e5e3", playing="#f3eadb", pressed="#dddddb", divider="#d8d8d6",
        primary="#1d1d1f", secondary="#505055", tertiary="#77777c", disabled="#a1a1a6",
        icon="#5b5b60", active="#a3844b", progress_track="#b2b2b1", accent="#a3844b",
        accent_hover="#b8955a", accent_pressed="#896b3d", danger="#bd625c",
        warning="#96732e", success="#3f8060", shadow="rgba(24, 24, 27, .16)",
        overlay="rgba(24, 24, 27, .26)",
    ),
    fonts=ThemeFonts(),
)


DARK_THEME = Theme(
    mode="dark",
    colors=_colors(
        app="#111111", sidebar="#161616", content="#1b1b1b", player="#171717",
        surface="#202020", surface_secondary="#242424", elevated="#2b2b2b",
        hover="#333333", selected="#303030", playing="#322c24", pressed="#393939", divider="#383838",
        primary="#f2f1ee", secondary="#c8c7c3", tertiary="#929292", disabled="#6b6b6b",
        icon="#d1d1ce", active="#c9a86a", progress_track="#616161", accent="#c9a86a",
        accent_hover="#dab97b", accent_pressed="#a78950", danger="#e18c83",
        warning="#d9b873", success="#8bc2a0", shadow="rgba(0, 0, 0, .56)",
        overlay="rgba(0, 0, 0, .52)",
    ),
    fonts=ThemeFonts(),
)


def get_theme(mode: str) -> Theme:
    """Resolve one complete immutable Quiet Orbit theme."""

    return LIGHT_THEME if str(mode).casefold() == "light" else DARK_THEME
