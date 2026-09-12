"""B2 presentation scoped to the formal settings overlay, without state ownership."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QSizePolicy

from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_control_factory import (
    SettingSlider, SettingsDangerAction, SettingsToggle, ThemedComboBox,
)


def _action(button, theme: Theme, *, primary: bool = False) -> None:
    c = theme.colors
    danger = isinstance(button, SettingsDangerAction)
    warning = button.property("settingsTone") == "warning"
    foreground = c.text_on_accent if primary else c.warning if warning else c.danger if danger else c.secondary_text
    fill = c.primary_button_fill if primary else c.input_background
    border = c.danger if danger and not warning else "transparent"
    button.setStyleSheet(
        f"QPushButton {{ min-height: 35px; padding: 0 15px; border: 1px solid {border};"
        f"border-radius: 4px; background: {fill}; color: {foreground}; font-size: 13px; font-weight: 400; }}"
        f"QPushButton:hover {{ background: {c.hover_background}; color: {c.primary_text}; }}"
        f"QPushButton:disabled {{ background: {c.surface_secondary}; color: {c.disabled_text}; border-color: transparent; }}"
        f'QPushButton[hushKeyboardFocus="true"]:focus {{ border: 1px solid {c.focus_ring}; }}'
    )


def arrange_rows(overlay, window_width: int) -> None:
    """Keep the established 1000px stacking contract; compact controls independently."""
    compact = window_width < 1000
    control_width = 190 if window_width <= 1080 else 220
    sidebar_width = 160 if window_width <= 1080 else 202
    overlay.sidebar.setFixedWidth(sidebar_width)
    for page in overlay._category_scrolls:
        inset = 24 if window_width <= 1080 else 32
        overlay._category_pages[page].layout().setContentsMargins(inset, 18, inset, 30)
    for key in ("online_sources", "pending_imports"):
        page = overlay._category_pages.get(key)
        if page is not None:
            page.layout().setContentsMargins(24 if window_width <= 1080 else 32, 18, 24 if window_width <= 1080 else 32, 24)
    for row in overlay._rows:
        control = row.control
        stacked = compact and not isinstance(control, SettingsToggle)
        row._row_layout.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        row._row_layout.setContentsMargins(0, 20, 0, 20)
        row._row_layout.setSpacing(12 if stacked else 26)
        row._row_layout.setAlignment(control, Qt.AlignmentFlag.AlignLeft if stacked else Qt.AlignmentFlag.AlignRight)
        row.title_label.setWordWrap(True)
        row.setMinimumHeight(89)
        if isinstance(control, (ThemedComboBox, SettingSlider)):
            # Long option labels still have the native popup and full tooltip.
            minimum = 250 if row.path == "music_scan_import_mode" else control_width
            control.setFixedWidth(minimum)
        if row.path in overlay._path_controls:
            picker = overlay._path_controls[row.path].picker
            picker.setMinimumWidth(0)
            picker.setMaximumWidth(430)
            picker.path_label.setMinimumWidth(64)
            picker.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            control.setFixedWidth(min(430, max(310, overlay.content_stack.width() - 70)) if stacked else 400)


def style_overlay(overlay, theme: Theme) -> None:
    """Apply visual roles after native controls receive their normal theme update."""
    c = theme.colors
    background = c.surface_elevated
    overlay.dialog.setStyleSheet(
        f"QFrame#settingsDialog {{ background: {background}; border: 0; border-radius: 11px; }}"
        f"QFrame#settingsConfirmationBar {{ background: {c.selected_background}; }}"
    )
    overlay.title_label.setStyleSheet(f"background: transparent; color: {c.primary_text}; font-size: 25px; font-weight: 600;")
    overlay.subtitle_label.setStyleSheet(f"background: transparent; color: {c.text_tertiary}; font-size: 12px;")
    sidebar = overlay.sidebar
    sidebar.setStyleSheet(
        f"SettingsSidebar {{ background: {c.surface_primary}; border: 0; }}"
        "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }"
        f"QScrollBar:vertical {{ width: 4px; background: transparent; }} QScrollBar::handle:vertical {{ background: {c.divider}; min-height: 24px; }}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    )
    sidebar.scroll.widget().layout().setContentsMargins(14, 8, 14, 8)
    sidebar.scroll.widget().layout().setSpacing(3)
    for button in sidebar._buttons.values():
        button.setFixedHeight(43)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setStyleSheet(
            f"QToolButton {{ min-height: 43px; text-align: left; padding: 0 10px; border: 0; border-left: 2px solid transparent;"
            f"border-radius: 4px; color: {c.secondary_text}; font-size: 13px; font-weight: 400; background: transparent; }}"
            f"QToolButton:hover {{ background: {c.hover_background}; }}"
            f"QToolButton:checked {{ background: {c.selected_background}; color: {c.primary_text}; border-left-color: {c.accent}; }}"
            f'QToolButton[hushKeyboardFocus="true"]:focus {{ border: 1px solid {c.focus_ring}; border-left-width: 2px; }}'
        )
    for key, scroll in overlay._category_scrolls.items():
        page = overlay._category_pages[key]
        page.setStyleSheet(f"background: {background}; color: {c.secondary_text};")
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 0; background: {background}; }}"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            f"QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 3px; background: {c.divider}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
    for section in overlay._sections:
        section.rows_layout.setSpacing(0)
        section.title.setStyleSheet(f"background: transparent; color: {c.primary_text}; font-size: 19px; font-weight: 600;")
        section.description.setStyleSheet(f"background: transparent; color: {c.text_tertiary}; font-size: 12px;")
    for row in overlay._rows:
        fill = c.selected_background if row._highlighted else "transparent"
        row.setStyleSheet(f"SettingsRow {{ background: {fill}; border: 0; border-bottom: 1px solid {c.divider}; border-radius: 0; }}")
        row.title_label.setStyleSheet(f"background: transparent; color: {c.primary_text}; font-size: 14px; font-weight: 400;")
        row.description_label.setStyleSheet(f"background: transparent; color: {c.secondary_text}; font-size: 12px; font-weight: 400;")
    for control in overlay._controls.values():
        if isinstance(control, SettingSlider):
            control.slider.set_handle_radius(4)
            control.value_label.setStyleSheet(f"background: transparent; color: {c.secondary_text}; font-size: 12px;")
        elif isinstance(control, ThemedComboBox):
            control.setStyleSheet(control.styleSheet() + f"QComboBox {{ font-size: 12px; border: 1px solid transparent; border-radius: 4px; background: {c.input_background}; }}")
    for path in overlay._path_controls.values():
        path.picker.setStyleSheet(
            f"QLabel#settingsPathValue {{ min-height: 35px; padding: 0 4px; background: transparent; border: 0; color: {c.secondary_text}; font-size: 12px; }}"
            f"QLabel#settingsPathStatus {{ background: transparent; color: {c.warning}; font-size: 11px; }}"
            f"QToolButton {{ min-height: 35px; padding: 0 8px; border: 1px solid transparent; border-radius: 4px; background: {c.input_background}; color: {c.secondary_text}; font-size: 12px; }}"
            f"QToolButton:hover {{ background: {c.hover_background}; }} QToolButton:disabled {{ color: {c.disabled_text}; }}"
            f'QToolButton[hushKeyboardFocus="true"]:focus {{ border-color: {c.focus_ring}; }}'
        )
    for button in overlay._aux_controls:
        _action(button, theme)
    footer = overlay.footer
    footer.setMinimumHeight(66)
    footer.layout().setContentsMargins(26, 12, 26, 12)
    footer.layout().setStretch(0, 1)
    footer.layout().setStretch(1, 0)
    footer.status_label.setWordWrap(True)
    footer.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    footer.setStyleSheet(f"SettingsFooter {{ background: {c.surface_primary}; border-top: 1px solid {c.divider}; border-bottom-left-radius: 11px; border-bottom-right-radius: 11px; }}")
    footer.status_label.setStyleSheet(f"background: transparent; font-size: 12px; color: {c.secondary_text};")
    _action(footer.cancel_button, theme)
    _action(footer.save_button, theme, primary=True)
    overlay.folder_list.setStyleSheet(
        f"QListWidget {{ background: transparent; border: 0; color: {c.primary_text}; font-size: 13px; }}"
        f"QListWidget::item {{ padding: 14px 0; border-bottom: 1px solid {c.divider}; }}"
        f"QListWidget::item:selected {{ background: {c.selected_background}; }}"
    )
    overlay.about_changelog.setStyleSheet(f"QPlainTextEdit {{ background: transparent; border: 0; color: {c.secondary_text}; font-size: 12px; selection-background-color: {c.selected_background}; }}")
    overlay._category_pages["about"].setStyleSheet(
        f"QWidget {{ background: {background}; color: {c.secondary_text}; font-size: 13px; }}"
        + f"QLabel#settingsAboutAppName {{ font-size: 24px; font-weight: 600; color: {c.primary_text}; }}"
        + f"QLabel#settingsAboutVersion {{ font-size: 12px; color: {c.secondary_text}; }}"
    )
    for key in ("online_sources", "pending_imports"):
        page = overlay._category_pages.get(key)
        if page is None:
            continue
        marker = "/* B2 settings embedding */"
        page.setStyleSheet(page.styleSheet().split(marker)[0] + marker +
            f"QWidget#settingsCategory_online_sources, QWidget#onlineSourceContent, QWidget#pendingImportsPage, QListWidget#pendingImportsList {{ background: {background}; }}"
            f"QLabel#settingsImmediateNote {{ background: transparent; color: {c.text_tertiary}; font-size: 11px; }}"
        )
        if hasattr(page, "title_label"):
            page.title_label.setStyleSheet(f"background: transparent; color: {c.primary_text}; font-size: 22px; font-weight: 600;")
        if hasattr(page, "header"):
            page.header.title_label.setStyleSheet(f"background: transparent; color: {c.primary_text}; font-size: 22px; font-weight: 600;")
    for button in (overlay.confirm_dialog.confirm_button, overlay.confirm_dialog.discard_button, overlay.confirm_dialog.cancel_button):
        _action(button, theme)
    arrange_rows(overlay, getattr(overlay, "_presentation_window_width", overlay.window().width()))
