"""Named existing thresholds, in Qt logical pixels; no global breakpoint merge."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LayoutWidths:
    """Widths measured by the owner, never inferred by subtracting a sidebar."""
    window_width: int
    content_width: int
    viewport_width: int


@dataclass(frozen=True, slots=True)
class ResponsiveThresholds:
    table_medium: int = 950
    browse_compact_max: int = 960
    settings_medium: int = 1000
    shell_compact_max: int = 1080
    immersive_medium: int = 1100
    browse_four_columns_max: int = 1200
    table_wide: int = 1220
    immersive_wide: int = 1400
    browse_five_columns_max: int = 1440
    information_rail_wide: int = 1450
    browse_extra_wide: int = 1600
    immersive_extra_wide: int = 1700


BREAKPOINTS = ResponsiveThresholds()
