"""Shared visual tokens for HushPlayer.

The semantic names in this module are the single colour vocabulary used by
the UI.  The legacy aliases near the end of each set intentionally remain so
small, already-stable widgets can migrate without a risky rewrite.
"""

from __future__ import annotations


def _with_legacy_aliases(tokens: dict[str, str]) -> dict[str, str]:
    """Keep established widgets compatible while they use semantic colours."""
    aliases = {
        "app_bg": "window_background",
        "shell_bg": "surface_secondary",
        "sidebar_bg": "surface",
        "panel_bg": "surface",
        "card_bg": "surface",
        "card_bg_alt": "surface_secondary",
        "card_bg_high": "surface_hover",
        "hover": "surface_hover",
        "active": "surface_pressed",
        "selected_bg": "selection_background",
        "selected_border": "selection_border",
        "playing_bg": "current_track_background",
        "text": "text_primary",
        "text_weak": "text_muted",
        "text_disabled": "text_disabled",
        "placeholder": "text_muted",
        "accent_soft": "selection_background",
        "favorite": "danger",
        "favorite_soft": "danger_soft",
        "error": "danger",
    }
    combined = dict(tokens)
    combined.update({alias: tokens[target] for alias, target in aliases.items()})
    return combined


# These are deliberately designed independently.  The light mode is not an
# inverted dark palette: it uses cool off-white window surfaces and readable
# charcoal text, matching Windows 11's calm Fluent hierarchy.
DARK_THEME_TOKENS = _with_legacy_aliases(
    {
        "window_background": "#0d0f14",
        "surface": "#151922",
        "surface_secondary": "#10131a",
        "surface_tertiary": "#1a1f2b",
        "surface_hover": "#202631",
        "surface_pressed": "#252c3a",
        "border": "#2a303b",
        "border_strong": "#3a4352",
        "player_surface": "#151922",
        "player_border": "#2a303b",
        "player_surface_separator": "#2a303b",
        "text_primary": "#f3f4f6",
        "text_secondary": "#b5bbc7",
        "text_muted": "#8a92a3",
        "text_disabled": "#8994a6",
        "navigation_text": "#d7dde8",
        "navigation_text_hover": "#f3f4f6",
        "navigation_text_selected": "#f8fbff",
        "navigation_text_disabled": "#8f9aab",
        "icon_default": "#b8c1d0",
        "icon_selected": "#8fb8ff",
        "icon_disabled": "#8792a3",
        "accent": "#4c8dff",
        "accent_hover": "#65a0ff",
        "accent_pressed": "#3978dd",
        "on_accent": "#ffffff",
        "selection_background": "rgba(76, 141, 255, 0.18)",
        "selection_border": "rgba(76, 141, 255, 0.42)",
        "selection_text": "#f8fbff",
        "current_track_background": "rgba(76, 141, 255, 0.11)",
        "current_track_text": "#8fb8ff",
        "input_background": "#11131a",
        "scrollbar_background": "rgba(255, 255, 255, 0.055)",
        "scrollbar_handle": "rgba(255, 255, 255, 0.22)",
        "control_overlay": "rgba(255, 255, 255, 0.055)",
        "control_overlay_hover": "rgba(255, 255, 255, 0.105)",
        "control_overlay_pressed": "rgba(255, 255, 255, 0.145)",
        "player_secondary_background": "rgba(255, 255, 255, 0.055)",
        "player_secondary_border": "#2a303b",
        "player_secondary_icon": "#b5bbc7",
        "player_secondary_hover_background": "rgba(255, 255, 255, 0.105)",
        "player_secondary_hover_border": "#3a4352",
        "player_secondary_hover_icon": "#f3f4f6",
        "player_secondary_pressed_background": "rgba(255, 255, 255, 0.145)",
        "player_secondary_pressed_border": "#3a4352",
        "player_secondary_disabled_background": "rgba(255, 255, 255, 0.035)",
        "player_secondary_disabled_icon": "#8994a6",
        "slider_groove": "rgba(255, 255, 255, 0.14)",
        "slider_fill": "#4c8dff",
        "slider_handle": "#f8fbff",
        "slider_handle_border": "#3a4352",
        "slider_handle_hover": "#ffffff",
        "slider_disabled": "#596372",
        "overlay_background": "rgba(8, 10, 15, 150)",
        "overlay_background_soft": "rgba(8, 10, 15, 92)",
        "immersive_button_surface": "rgba(15, 20, 30, 148)",
        "immersive_button_border": "rgba(222, 231, 245, 0.24)",
        "immersive_button_text": "#e4eaf3",
        "immersive_button_hover_surface": "rgba(46, 94, 166, 174)",
        "immersive_button_pressed_surface": "rgba(35, 76, 136, 198)",
        "immersive_player_surface": "rgba(10, 14, 22, 104)",
        "immersive_player_border": "rgba(222, 231, 245, 14)",
        "immersive_player_text": "#f4f7fb",
        "immersive_player_secondary_text": "#c8d2e1",
        "danger": "#e15b64",
        "danger_soft": "rgba(225, 91, 100, 0.15)",
        "warning": "#e8ad52",
        "success": "#8fd5a6",
    }
)

LIGHT_THEME_TOKENS = _with_legacy_aliases(
    {
        "window_background": "#f3f5f8",
        "surface": "#fbfcfe",
        "surface_secondary": "#f6f8fb",
        "surface_tertiary": "#edf1f6",
        "surface_hover": "#e6ebf3",
        "surface_pressed": "#dce4ef",
        "border": "#d5dce6",
        "border_strong": "#b7c3d1",
        "player_surface": "#f6f8fb",
        "player_border": "#d5dee8",
        "player_surface_separator": "#d5dee8",
        "text_primary": "#1c2530",
        "text_secondary": "#465466",
        "text_muted": "#68778a",
        "text_disabled": "#77879a",
        "navigation_text": "#344256",
        "navigation_text_hover": "#1c2530",
        "navigation_text_selected": "#173b73",
        "navigation_text_disabled": "#68798c",
        "icon_default": "#4b5d72",
        "icon_selected": "#286ed6",
        "icon_disabled": "#74869a",
        "accent": "#286ed6",
        "accent_hover": "#1d62c8",
        "accent_pressed": "#1655ae",
        "on_accent": "#ffffff",
        "selection_background": "rgba(40, 110, 214, 0.16)",
        "selection_border": "rgba(40, 110, 214, 0.46)",
        "selection_text": "#173b73",
        "current_track_background": "rgba(40, 110, 214, 0.13)",
        "current_track_text": "#1d62c8",
        "input_background": "#ffffff",
        "scrollbar_background": "rgba(64, 82, 104, 0.08)",
        "scrollbar_handle": "rgba(64, 82, 104, 0.34)",
        "control_overlay": "rgba(64, 82, 104, 0.07)",
        "control_overlay_hover": "rgba(64, 82, 104, 0.13)",
        "control_overlay_pressed": "rgba(64, 82, 104, 0.19)",
        "player_secondary_background": "#edf2f7",
        "player_secondary_border": "#bcc9d6",
        "player_secondary_icon": "#405168",
        "player_secondary_hover_background": "#e3ecf6",
        "player_secondary_hover_border": "#96abc1",
        "player_secondary_hover_icon": "#245eaa",
        "player_secondary_pressed_background": "#d7e3f0",
        "player_secondary_pressed_border": "#7f99b6",
        "player_secondary_disabled_background": "#f1f4f7",
        "player_secondary_disabled_icon": "#728399",
        "slider_groove": "#b8c5d3",
        "slider_fill": "#286ed6",
        "slider_handle": "#ffffff",
        "slider_handle_border": "#72849a",
        "slider_handle_hover": "#f8fbff",
        "slider_disabled": "#a7b4c3",
        "overlay_background": "rgba(247, 249, 252, 235)",
        "overlay_background_soft": "rgba(247, 249, 252, 215)",
        "immersive_button_surface": "rgba(248, 250, 253, 150)",
        "immersive_button_border": "rgba(66, 83, 106, 0.27)",
        "immersive_button_text": "#243447",
        "immersive_button_hover_surface": "rgba(229, 239, 251, 190)",
        "immersive_button_pressed_surface": "rgba(212, 229, 247, 205)",
        "immersive_player_surface": "rgba(242, 246, 251, 96)",
        "immersive_player_border": "rgba(72, 91, 115, 14)",
        "immersive_player_text": "#1c2939",
        "immersive_player_secondary_text": "#4a5b70",
        "danger": "#bf3e4c",
        "danger_soft": "rgba(191, 62, 76, 0.12)",
        "warning": "#a96300",
        "success": "#287a4c",
    }
)


# A stable mutable mapping lets delegate painters use the active palette at
# paint time without rebuilding any music-list model or playback object.
ACTIVE_THEME_TOKENS: dict[str, str] = dict(DARK_THEME_TOKENS)


def get_theme_tokens(resolved_mode: str = "dark") -> dict[str, str]:
    """Return a defensive copy of one resolved palette."""
    return dict(LIGHT_THEME_TOKENS if resolved_mode == "light" else DARK_THEME_TOKENS)


def set_active_theme_tokens(resolved_mode: str) -> dict[str, str]:
    """Update the shared painter palette in place and return it."""
    ACTIVE_THEME_TOKENS.clear()
    ACTIVE_THEME_TOKENS.update(get_theme_tokens(resolved_mode))
    return ACTIVE_THEME_TOKENS


UI_RADII = {
    # Semantic names are the preferred vocabulary for new UI work.  The
    # established aliases remain below so existing widgets do not need a
    # broad, risky migration.
    "radius_sm": 6,
    "radius_md": 10,
    "radius_lg": 16,
    "small": 6,
    "control": 8,
    "button": 10,
    "card": 12,
    "panel": 16,
    "shell": 22,
}


UI_SPACING = {
    "spacing_xs": 4,
    "spacing_sm": 8,
    "spacing_md": 12,
    "spacing_lg": 16,
    "spacing_xl": 24,
    "spacing_xxl": 32,
    "xxs": 4,
    "xs": 8,
    "sm": 12,
    "md": 16,
    "lg": 20,
    "xl": 24,
}


UI_TYPOGRAPHY = {
    "font_caption": 12,
    "font_secondary": 13,
    "font_body": 14,
    "font_body_emphasis": 14,
    "font_section": 17,
    "font_page_title": 23,
    "font_track_title": 14,
    "font_player_title": 15,
    "font_player_artist": 13,
    "page_title": 24,
    "section_title": 18,
    "body": 14,
    "secondary": 13,
    "caption": 12,
    "micro": 11,
}


UI_CONTROL_SIZES = {
    "icon_small": 16,
    "icon_normal": 18,
    "icon_large": 22,
    "control_height_small": 32,
    "control_height_normal": 36,
    "navigation_item_height": 40,
    "table_row_height": 46,
    "table_header_height": 36,
    "player_height": 102,
    "player_height_narrow": 96,
    "player_height_compact": 102,
    "player_height_full": 110,
    "player_vertical_padding_narrow": 8,
    "player_vertical_padding_compact": 10,
    "player_vertical_padding_full": 12,
    "player_cover_size": 68,
    "player_cover_size_compact": 56,
    "player_cover_size_full": 72,
    "now_playing_cover_size": 228,
    "now_playing_cover_size_compact": 184,
    "play_button_size": 44,
    "transport_button_size": 36,
    "player_mode_button_height": 36,
    "player_mode_button_min_width": 76,
    "player_mode_button_max_width": 96,
    "player_control_group_width": 124,
    "player_slider_groove_height": 4,
    "player_slider_handle_size": 14,
    "theme_quick_button_size": 32,
    "navigation_height": 40,
    "navigation_icon": 18,
    "search_height": 38,
    "compact_button_height": 34,
    "icon_button": 36,
    "track_row_height": 46,
    "track_like_width": 28,
    "player_cover": 68,
    "player_center_max_width": 800,
    "scrollbar_width": 10,
}
