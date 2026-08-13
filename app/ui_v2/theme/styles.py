"""Shared QSS built exclusively from the UI V2 semantic token set."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from app.ui_v2.theme.tokens import Theme, font_family_qss


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
        QPalette.ColorRole.Highlight: colors.surface_selected,
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
        QWidget, QMenu, QToolTip {{
            font-family: {font_family_qss()};
            font-size: {theme.fonts.body}px;
            font-weight: 500;
        }}
        QWidget#uiV2Root {{
            background: {c.app_background};
            color: {c.text_primary};
        }}
        QWidget#uiV2Body {{
            background: {c.app_background};
        }}
        QWidget#uiV2ContentContainer, QStackedWidget#uiV2ContentRouter,
        QWidget#libraryPage, QWidget#trackListPage, QWidget#onlineSearchPage, QWidget#onlineSourcePage {{
            background: {c.content_background};
        }}
        QWidget#libraryWorkSurface, QWidget#trackListWorkSurface {{
            background: {c.surface_primary};
            border: 1px solid {c.border};
            border-radius: {m.radius_lg}px;
        }}
        QWidget#collectionActionRow, QWidget#sectionToolbar {{
            background: {c.surface_primary};
            border: 1px solid {c.border};
            border-radius: {m.radius_md}px;
        }}
        QWidget#libraryWorkSurface QTableView#trackTable,
        QWidget#trackListWorkSurface QTableView#trackTable {{
            background: transparent;
        }}
        QLineEdit#searchInput, QLineEdit#titleBarSearchInput {{
            min-height: {m.control_height}px;
            padding: 0 {m.spacing_md}px;
            border: 1px solid {c.divider};
            border-radius: {m.radius_md}px;
            background: {c.surface_secondary};
            color: {c.text_primary};
            selection-background-color: {c.accent};
            selection-color: {c.text_primary};
        }}
        QLineEdit#searchInput:focus, QLineEdit#titleBarSearchInput:focus {{ border-color: {c.focus_ring}; }}
        /* Tool buttons own their focus treatment so mouse clicks do not leave
           a second, unexpected outline around compact navigation/actions. */
        QPushButton:focus, QComboBox:focus, QSlider:focus,
        QLineEdit:focus {{ outline: 1px solid {c.focus_ring}; outline-offset: 1px; }}
        QToolTip {{
            padding: {m.spacing_xs}px {m.spacing_sm}px;
            border: 1px solid {c.divider};
            border-radius: {m.radius_sm}px;
            background: {c.surface_elevated};
            color: {c.text_primary};
        }}
        QPushButton {{
            min-height: {m.control_height}px;
            padding: 0 {m.spacing_md}px;
            border: 1px solid transparent;
            border-radius: {m.radius_sm}px;
            background: transparent;
            color: {c.text_secondary};
        }}
        QPushButton:hover {{
            background: {c.hover_background};
            color: {c.text_primary};
        }}
        QPushButton:pressed {{ background: {c.surface_pressed}; }}
        QPushButton:disabled {{
            background: transparent;
            color: {c.text_disabled};
        }}
        QCheckBox, QRadioButton {{ color: {c.text_secondary}; spacing: {m.spacing_sm}px; }}
        QCheckBox:hover, QRadioButton:hover {{ color: {c.text_primary}; }}
        QComboBox {{
            min-height: {m.control_height}px;
            padding: 0 {m.spacing_md}px;
            border: 1px solid {c.divider};
            border-radius: {m.radius_md}px;
            background: {c.input_background};
            color: {c.text_primary};
        }}
        QComboBox:hover {{ border-color: {c.border_strong}; }}
        QComboBox QAbstractItemView {{
            padding: {m.spacing_xs}px;
            border: 1px solid {c.divider};
            background: {c.surface_elevated};
            color: {c.text_primary};
            selection-background-color: {c.surface_selected};
            selection-color: {c.text_primary};
        }}
        QTableView#trackTable {{
            border: 0;
            background: {c.surface_primary};
            gridline-color: transparent;
            outline: 0;
            selection-background-color: transparent;
            selection-color: {c.text_primary};
        }}
        QHeaderView::section {{
            padding: 0 {m.spacing_sm}px;
            border: 0;
            border-bottom: 1px solid {c.divider};
            background: {c.surface_primary};
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
        QMenu, QDialog {{
            padding: {m.spacing_xs}px;
            border: 1px solid {c.divider};
            border-radius: {m.radius_sm}px;
            background: {c.surface_elevated};
            color: {c.text_primary};
        }}
        QMenu::item {{ padding: {m.spacing_sm}px {m.spacing_lg}px; border-radius: {m.radius_sm}px; }}
        QMenu::item:selected {{ background: {c.surface_hover}; color: {c.text_primary}; }}
        QScrollBar:horizontal {{
            height: 8px;
            border: 0;
            background: transparent;
            margin: 2px 4px;
        }}
        QScrollBar::handle:horizontal {{ min-width: 32px; border-radius: 4px; background: {c.divider}; }}
        QScrollBar::handle:horizontal:hover {{ background: {c.text_tertiary}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


def build_dialog_stylesheet(theme: Theme) -> str:
    """Return the complete themed control surface used by V2 dialogs.

    Page styling intentionally stays lightweight, but a modal dialog must not
    fall back to the native palette for its buttons and list rows.  Keeping
    this sheet separate lets small custom dialog rules extend it without
    accidentally changing normal page controls.
    """

    c = theme.colors
    m = theme.metrics
    return f"""
        QDialog {{
            background: {c.surface_elevated};
            color: {c.primary_text};
            font-family: {font_family_qss()};
        }}
        QDialog QLabel {{ color: {c.primary_text}; background: transparent; }}
        QDialog QLabel#settingsDialogTitle {{
            color: {c.primary_text};
            font-size: {theme.fonts.page_title}px;
            font-weight: 600;
        }}
        QDialog QLabel#settingsDialogSubtitle {{
            color: {c.secondary_text};
            font-size: {theme.fonts.secondary}px;
        }}
        QDialog QLabel#settingsCardTitle {{
            color: {c.primary_text};
            font-size: {theme.fonts.section_title}px;
            font-weight: 600;
        }}
        QDialog QLabel#settingsHint {{
            color: {c.secondary_text};
            font-size: {theme.fonts.secondary}px;
        }}
        QDialog QFrame#settingsCard {{
            background: {c.surface_secondary};
            border: 1px solid {c.border};
            border-radius: {m.radius_md}px;
        }}
        QDialog QLineEdit, QDialog QPlainTextEdit {{
            min-height: {m.control_height}px;
            padding: 0 {m.spacing_sm}px;
            border: 1px solid {c.border};
            border-radius: {m.radius_sm}px;
            background: {c.input_background};
            color: {c.primary_text};
            selection-background-color: {c.accent};
            selection-color: {c.content_background};
        }}
        QDialog QLineEdit:focus, QDialog QPlainTextEdit:focus {{
            border-color: {c.focus_ring};
        }}
        QDialog QLineEdit:disabled, QDialog QPlainTextEdit:disabled {{
            background: {c.surface_pressed};
            color: {c.disabled_text};
            border-color: {c.border};
        }}
        QDialog QListWidget {{
            padding: {m.spacing_xs}px;
            border: 1px solid {c.border};
            border-radius: {m.radius_sm}px;
            background: {c.input_background};
            color: {c.primary_text};
            outline: 0;
            selection-background-color: {c.selected_background};
            selection-color: {c.primary_text};
        }}
        QDialog QListWidget::item {{
            min-height: 52px;
            padding: {m.spacing_sm}px {m.spacing_md}px;
            border-radius: {m.radius_sm}px;
            color: {c.primary_text};
        }}
        QDialog QListWidget::item:hover {{ background: {c.hover_background}; }}
        QDialog QListWidget::item:selected {{
            background: {c.selected_background};
            color: {c.primary_text};
        }}
        QDialog QListWidget#onlineRecoveryCandidateList::item:hover {{
            background: {c.surface_secondary};
            color: {c.primary_text};
        }}
        QDialog QListWidget#onlineRecoveryCandidateList::item:selected:hover {{
            background: {c.selected_background};
            color: {c.primary_text};
        }}
        QDialog QPushButton, QDialog QToolButton {{
            min-height: {m.control_height}px;
            min-width: 80px;
            padding: 0 {m.spacing_md}px;
            border: 1px solid {c.border};
            border-radius: {m.radius_sm}px;
            background: {c.surface_secondary};
            color: {c.primary_text};
        }}
        QDialog QPushButton:hover, QDialog QToolButton:hover {{
            background: {c.hover_background};
            border-color: {c.border_strong};
        }}
        QDialog QPushButton:pressed, QDialog QToolButton:pressed {{
            background: {c.surface_pressed};
        }}
        QDialog QPushButton:focus, QDialog QToolButton:focus {{
            outline: 0;
            border-color: {c.focus_ring};
        }}
        QDialog QPushButton:disabled, QDialog QToolButton:disabled {{
            background: {c.surface_pressed};
            color: {c.disabled_text};
            border-color: {c.border};
        }}
        QDialog QPushButton[role="primary"], QDialog QToolButton[role="primary"] {{
            border-color: transparent;
            background: {c.accent};
            color: {c.content_background};
            font-weight: 600;
        }}
        QDialog QPushButton[role="primary"]:hover, QDialog QToolButton[role="primary"]:hover {{
            background: {c.accent_hover};
            color: {c.content_background};
        }}
        QDialog QPushButton[role="primary"]:disabled, QDialog QToolButton[role="primary"]:disabled {{
            background: {c.surface_pressed};
            color: {c.disabled_text};
        }}
        QDialog QProgressBar {{
            min-height: 16px;
            max-height: 16px;
            border: 0;
            border-radius: 8px;
            background: {c.progress_track};
            color: {c.primary_text};
            text-align: center;
        }}
        QDialog QProgressBar::chunk {{
            border-radius: 8px;
            background: {c.accent};
        }}
        QDialog QScrollBar:vertical {{
            width: 8px;
            border: 0;
            background: transparent;
            margin: 4px 2px;
        }}
        QDialog QScrollBar::handle:vertical {{
            min-height: 28px;
            border-radius: 4px;
            background: {c.border_strong};
        }}
        QDialog QScrollBar::handle:vertical:hover {{ background: {c.text_tertiary}; }}
        QDialog QScrollBar::add-line:vertical, QDialog QScrollBar::sub-line:vertical {{ height: 0; }}
    """
