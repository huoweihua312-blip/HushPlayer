"""Shared visual tokens for controls drawn over the immersive artwork surface."""

from __future__ import annotations

from dataclasses import dataclass

from app.ui_v2.theme.tokens import Theme


@dataclass(frozen=True, slots=True)
class ImmersiveGlassTokens:
    """Low-opacity surfaces that let the artwork atmosphere remain visible."""

    default: str = "rgba(255, 255, 255, 0.07)"
    hover: str = "rgba(255, 255, 255, 0.11)"
    pressed: str = "rgba(255, 255, 255, 0.15)"
    border: str = "rgba(255, 255, 255, 0.10)"
    border_hover: str = "rgba(255, 255, 255, 0.16)"
    primary_text: str = "rgba(255, 255, 255, 0.94)"
    secondary_text: str = "rgba(255, 255, 255, 0.68)"


IMMERSIVE_GLASS = ImmersiveGlassTokens()


def _accent_focus_color(theme: Theme) -> str:
    """Use the approved accent as a restrained, non-filling focus ring."""

    value = theme.colors.focus_ring.strip()
    if value.startswith("#") and len(value) == 7:
        try:
            red, green, blue = (int(value[index : index + 2], 16) for index in (1, 3, 5))
        except ValueError:
            return value
        return f"rgba({red}, {green}, {blue}, 0.55)"
    return value


def immersive_mode_button_qss(theme: Theme) -> str:
    """Return the shared glass treatment for the Header mode segment."""

    glass = IMMERSIVE_GLASS
    return (
        "QToolButton#immersiveModeButton {"
        f"border: 1px solid transparent; border-radius: 18px; background: transparent; "
        f"padding: 0 10px; color: {glass.secondary_text};"
        "}"
        "QToolButton#immersiveModeButton:hover {"
        f"background: {glass.default}; border-color: transparent; color: {glass.primary_text};"
        "}"
        "QToolButton#immersiveModeButton:checked {"
        f"background: {glass.hover}; border: 1px solid {glass.border}; color: {glass.primary_text};"
        "}"
        "QToolButton#immersiveModeButton:pressed {"
        f"background: {glass.pressed}; border-color: {glass.border_hover};"
        "}"
        "QToolButton#immersiveModeButton:focus {"
        f"border: 1px solid {_accent_focus_color(theme)};"
        "}"
    )


def immersive_glass_button_qss(theme: Theme) -> str:
    """Return the shared glass pill treatment for an immersive utility button."""

    glass = IMMERSIVE_GLASS
    return (
        "QToolButton#returnToCurrentLyrics {"
        f"border: 1px solid {glass.border}; border-radius: 19px; "
        f"padding: 8px 14px; min-height: 36px; background: {glass.default}; "
        f"color: {glass.primary_text};"
        "}"
        "QToolButton#returnToCurrentLyrics:hover {"
        f"background: {glass.hover}; border-color: {glass.border_hover}; "
        f"color: {glass.primary_text};"
        "}"
        "QToolButton#returnToCurrentLyrics:pressed {"
        f"background: {glass.pressed}; border-color: {glass.border_hover};"
        "}"
        "QToolButton#returnToCurrentLyrics:focus {"
        f"border: 1px solid {_accent_focus_color(theme)};"
        "}"
    )


__all__ = [
    "IMMERSIVE_GLASS",
    "ImmersiveGlassTokens",
    "immersive_glass_button_qss",
    "immersive_mode_button_qss",
]
