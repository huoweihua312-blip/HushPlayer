"""Collection button treatments; values match the approved existing controls."""

from app.ui_v2.theme.styles import focus_qss


def button_qss(theme, *, role: str, selector: str = "QToolButton") -> str:
    """Opt-in variants sharing Theme roles; existing action_button_qss is unchanged.

    A permanent transparent border reserves the focus-ring space. This helper
    only paints: it does not install event filters or change click/hit testing.
    """
    c, m = theme.colors, theme.metrics
    variants = {
        "primary": (c.primary_button_fill, c.text_on_accent, "transparent"),
        "secondary": (c.surface_secondary, c.primary_text, c.divider),
        "ghost": ("transparent", c.secondary_text, "transparent"),
        "icon": ("transparent", c.secondary_text, "transparent"),
        "destructive": ("transparent", c.danger, c.danger),
    }
    background, foreground, border = variants[role]
    hover = background if role == "primary" else c.hover_background
    pressed = background if role == "primary" else c.selected_background
    return (
        f'{selector} {{ min-height: {m.control_height}px; padding: 0 {m.spacing_md}px; '
        f'border: 2px solid {border}; border-radius: {m.radius_control}px; '
        f'color: {foreground}; background: {background}; }}'
        f'{selector}:hover {{ background: {hover}; }}'
        f'{selector}:pressed {{ background: {pressed}; }}'
        + focus_qss(theme, selector)
        + f'{selector}:disabled {{ color: {c.disabled_text}; background: {c.surface_secondary}; '
        f'border-color: transparent; }}'
    )


def action_button_qss(theme, *, primary: bool) -> str:
    metrics, colors = theme.metrics, theme.colors
    base = f'QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; '
    focus = f'QToolButton[hushKeyboardFocus="true"]:focus {{ border-color: {colors.focus_ring}; }}'
    if primary:
        return (
            base + f'border: 1px solid transparent; border-radius: {metrics.radius_sm}px; color: {colors.content_background}; '
            f'background: {colors.accent}; font-weight: 600; }}'
            f'QToolButton:hover {{ background: {colors.accent_hover}; }}'
            f'QToolButton:pressed {{ background: {colors.accent_pressed}; }}' + focus +
            f'QToolButton:disabled {{ color: {colors.disabled_text}; background: {colors.surface_secondary}; }}'
        )
    return (
        base + f'border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.primary_text}; '
        f'background: {colors.surface_secondary}; }}'
        f'QToolButton:hover {{ background: {colors.hover_background}; border-color: {colors.border_strong}; }}'
        f'QToolButton:pressed {{ background: {colors.selected_background}; }}' + focus +
        f'QToolButton:disabled {{ color: {colors.disabled_text}; background: transparent; border-color: {colors.border}; }}'
    )
