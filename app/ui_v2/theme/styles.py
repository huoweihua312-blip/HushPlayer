"""Shared QSS built exclusively from the UI V2 semantic token set."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from app.ui_v2.theme.tokens import Theme


def build_application_palette(theme: Theme) -> QPalette:
    """Build the V2 palette used by native Qt controls and popup surfaces."""

    colors = theme.colors
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: colors.window_background,
        QPalette.ColorRole.WindowText: colors.text_primary,
        QPalette.ColorRole.Base: colors.input_background,
        QPalette.ColorRole.AlternateBase: colors.surface_secondary,
        QPalette.ColorRole.Text: colors.text_primary,
        QPalette.ColorRole.Button: colors.surface_secondary,
        QPalette.ColorRole.ButtonText: colors.text_secondary,
        QPalette.ColorRole.Highlight: colors.accent,
        QPalette.ColorRole.HighlightedText: colors.text_primary,
        QPalette.ColorRole.ToolTipBase: colors.surface_elevated,
        QPalette.ColorRole.ToolTipText: colors.text_primary,
        QPalette.ColorRole.PlaceholderText: colors.text_tertiary,
        QPalette.ColorRole.Link: colors.accent,
    }
    for role, value in roles.items():
        palette.setColor(QPalette.ColorGroup.All, role, QColor(value))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors.text_disabled))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Button,
        QColor(colors.surface_pressed),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Base,
        QColor(colors.window_background),
    )
    return palette


def build_stylesheet(theme: Theme) -> str:
    """Return low-emphasis shared styling for normal V2 pages and controls."""

    c = theme.colors
    m = theme.metrics
    return f"""
        QWidget#uiV2Root {{
            background: {c.app_background};
            color: {c.text_primary};
            font-family: "Segoe UI Variable", "Segoe UI";
        }}
        QWidget#uiV2Body, QWidget#uiV2ContentContainer,
        QStackedWidget#uiV2ContentRouter, QWidget#libraryPage {{
            background: {c.app_background};
        }}
        QLineEdit#searchInput {{
            min-height: {m.control_height}px;
            padding: 0 {m.spacing_md}px;
            border: 1px solid {c.divider};
            border-radius: {m.radius_md}px;
            background: {c.surface_secondary};
            color: {c.text_primary};
        }}
        QLineEdit#searchInput:focus {{ border-color: {c.focus_ring}; selection-background-color: {c.accent}; }}
        QTableView#trackTable {{
            border: 0;
            background: {c.app_background};
            gridline-color: transparent;
            outline: 0;
            selection-background-color: transparent;
            selection-color: {c.text_primary};
        }}
        QHeaderView::section {{
            padding: 0 {m.spacing_sm}px;
            border: 0;
            border-bottom: 1px solid {c.divider};
            background: {c.app_background};
            color: {c.text_tertiary};
            font-size: {theme.fonts.card_meta}px;
        }}
        QScrollBar:vertical {{
            width: 8px;
            border: 0;
            background: transparent;
            margin: 4px 2px;
        }}
        QScrollBar::handle:vertical {{
            min-height: 32px;
            border-radius: 4px;
            background: {c.divider};
        }}
        QScrollBar::handle:vertical:hover {{ background: {c.text_tertiary}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QMenu {{
            padding: {m.spacing_xs}px;
            border: 1px solid {c.divider};
            border-radius: {m.radius_sm}px;
            background: {c.surface_elevated};
            color: {c.text_primary};
        }}
        QMenu::item {{ padding: {m.spacing_sm}px {m.spacing_lg}px; border-radius: {m.radius_sm}px; }}
        QMenu::item:selected {{ background: {c.surface_hover}; }}
    """
