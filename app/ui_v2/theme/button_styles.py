"""Collection button treatments; values match the approved existing controls."""


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
