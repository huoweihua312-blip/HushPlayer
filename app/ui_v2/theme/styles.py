"""QSS construction from UI V2 semantic tokens."""

from __future__ import annotations

from app.ui_v2.theme.tokens import Theme


def build_stylesheet(theme: Theme) -> str:
    """Return a small shared stylesheet; delegates paint table rows directly."""
    c = theme.colors
    m = theme.metrics
    return f"""
        QWidget#uiV2Root {{
            background: {c.window_background};
            color: {c.primary_text};
        }}
        QWidget#libraryPage {{
            background: {c.content_background};
        }}
        QLineEdit#searchInput {{
            min-height: {m.control_height}px;
            padding: 0 {m.spacing_md}px;
            border: 1px solid {c.border};
            border-radius: {m.radius_md}px;
            background: {c.input_background};
            color: {c.primary_text};
        }}
        QLineEdit#searchInput:focus {{ border-color: {c.accent}; }}
        QToolButton#searchIcon, QToolButton#themeToggle, QToolButton#stateToggle {{
            border: 0;
            border-radius: {m.radius_sm}px;
            background: transparent;
            color: {c.secondary_text};
            padding: {m.spacing_xs}px {m.spacing_sm}px;
        }}
        QToolButton#themeToggle:hover, QToolButton#stateToggle:hover {{
            background: {c.hover_background};
            color: {c.primary_text};
        }}
        QTableView#trackTable {{
            border: 0;
            background: {c.content_background};
            gridline-color: transparent;
            outline: 0;
            selection-background-color: transparent;
            selection-color: {c.primary_text};
        }}
        QHeaderView::section {{
            padding: 0 {m.spacing_sm}px;
            border: 0;
            border-bottom: 1px solid {c.border_strong};
            background: {c.content_background};
            color: {c.subtle_text};
            font-size: {theme.fonts.caption}px;
        }}
        QScrollBar:vertical {{
            width: 10px;
            border: 0;
            background: transparent;
            margin: 4px 2px;
        }}
        QScrollBar::handle:vertical {{
            min-height: 32px;
            border-radius: 4px;
            background: {c.border_strong};
        }}
        QScrollBar::handle:vertical:hover {{ background: {c.secondary_text}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QMenu {{
            padding: {m.spacing_xs}px;
            border: 1px solid {c.border};
            border-radius: {m.radius_sm}px;
            background: {c.elevated_background};
            color: {c.primary_text};
        }}
        QMenu::item {{ padding: {m.spacing_sm}px {m.spacing_lg}px; border-radius: {m.radius_sm}px; }}
        QMenu::item:selected {{ background: {c.hover_background}; }}
    """
