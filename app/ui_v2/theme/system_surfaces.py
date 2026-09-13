"""B2 presentation for system surfaces; no action or window lifecycle policy."""
from __future__ import annotations

from app.ui_v2.theme.tokens import Theme, font_family_qss, get_theme


def button_stylesheet(theme: Theme, role: str = "secondary") -> str:
    c = get_theme(theme.mode, profile="b2").colors
    bg = c.primary_button_fill if role == "primary" else c.surface_secondary
    fg = c.text_on_accent if role == "primary" else c.primary_text
    border = c.danger if role == "danger" else "transparent"
    if role == "danger":
        bg, fg = "transparent", c.danger
    hover = c.primary_button_fill if role == "primary" else c.hover_background
    return f"""
        QPushButton {{ min-height: 33px; padding: 0 15px; border: 1px solid {border};
            border-radius: 4px; background: {bg}; color: {fg}; font-size: 13px; font-weight: 400; }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:focus {{ border-color: {c.focus_ring}; }}
        QPushButton:disabled {{ color: {c.disabled_text}; background: {c.surface_secondary}; border-color: transparent; }}
    """


def dialog_stylesheet(theme: Theme) -> str:
    c = get_theme(theme.mode, profile="b2").colors
    return f"""
        QDialog {{ background: {c.surface_elevated}; color: {c.primary_text};
            border: 1px solid {c.divider}; border-radius: 10px; font-family: {font_family_qss()}; }}
        QLabel {{ color: {c.secondary_text}; font-size: 13px; background: transparent; border: 0; }}
        QLabel#playlistDialogTitle, QLabel#trackInfoTitle, QLabel#settingsDialogTitle {{
            color: {c.primary_text}; font-size: 21px; font-weight: 600; }}
        QLabel#systemBrand {{ color: {c.primary_text}; font-size: 25px; font-weight: 600; }}
        QLabel#settingsCardTitle {{ color: {c.primary_text}; font-size: 14px; font-weight: 600; }}
        QLabel#playlistDialogError {{ color: {c.danger}; font-size: 12px; }}
        QLineEdit {{ min-height: 44px; padding: 0 12px; background: {c.input_background};
            color: {c.primary_text}; border: 1px solid transparent; border-radius: 4px;
            selection-background-color: {c.selected_background}; font-size: 14px; }}
        QLineEdit:focus {{ border-color: {c.focus_ring}; }}
        QListWidget {{ min-height: 170px; background: transparent; color: {c.primary_text};
            border: 1px solid transparent; border-radius: 4px; outline: 0; font-size: 14px; }}
        QListWidget:focus {{ border-color: {c.focus_ring}; }}
        QListWidget::item {{ padding: 11px 12px; border-radius: 3px; }}
        QListWidget::item:hover {{ background: {c.hover_background}; }}
        QListWidget::item:selected {{ background: {c.selected_background}; color: {c.primary_text}; }}
        QFrame#settingsCard {{ border: 0; background: transparent; }}
        QPlainTextEdit {{ background: transparent; color: {c.secondary_text}; border: 1px solid transparent;
            font-size: 13px; padding: 0; selection-background-color: {c.selected_background}; }}
        QPlainTextEdit:focus {{ border-color: {c.divider}; }}
        QProgressBar {{ background: {c.divider}; border: 0; border-radius: 1px; }}
        QProgressBar::chunk {{ background: {c.accent}; border-radius: 1px; }}
    """


def menu_stylesheet(theme: Theme, selector: str = "QMenu") -> str:
    c = get_theme(theme.mode, profile="b2").colors
    return f"""
        {selector} {{ background: {c.surface_elevated}; color: {c.primary_text}; padding: 7px;
            border: 1px solid {c.divider}; border-radius: 6px; font-family: {font_family_qss()}; font-size: 13px; }}
        {selector}::item {{ min-height: 18px; padding: 8px 24px 8px 12px; border-radius: 3px; color: {c.primary_text}; }}
        {selector}::item:selected {{ background: {c.hover_background}; color: {c.primary_text}; }}
        {selector}::item:disabled {{ color: {c.disabled_text}; }}
        {selector}::separator {{ height: 1px; margin: 6px 5px; background: {c.divider}; }}
    """


def global_system_stylesheet(theme: Theme) -> str:
    """Only popup selectors: never restyle a page, overlay, or player control."""
    c = get_theme(theme.mode, profile="b2").colors
    buttons = button_stylesheet(theme).replace("QPushButton", "QMessageBox QPushButton")
    return menu_stylesheet(theme) + buttons + f"""
        QToolTip {{ padding: 7px 10px; border: 1px solid {c.divider}; border-radius: 4px;
            background: {c.surface_elevated}; color: {c.primary_text}; font-size: 12px; }}
        QMessageBox {{ background: {c.surface_elevated}; color: {c.primary_text}; padding: 14px; }}
        QMessageBox QLabel {{ background: transparent; color: {c.secondary_text}; font-size: 13px; }}
        QMessageBox QLabel#qt_msgbox_label {{ color: {c.primary_text}; font-size: 19px; font-weight: 600; }}
        QMessageBox QLabel#qt_msgbox_informativelabel {{ min-width: 350px; padding: 10px 0 18px 0; }}
        QMessageBox QCheckBox {{ color: {c.secondary_text}; spacing: 8px; font-size: 13px; padding: 8px 0; }}
        QMessageBox QCheckBox::indicator {{ width: 16px; height: 16px; }}
    """
