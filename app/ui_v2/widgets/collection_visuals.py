"""Scoped B2 presentation for the three P2 collection pages.

Only existing widgets are styled/repositioned. Adapters, state and signal
connections remain owned by the pages; other collection pages do not opt in.
"""
from PySide6.QtCore import Qt

from app.ui_v2.theme.button_styles import button_qss
from app.ui_v2.theme.styles import input_qss
from app.ui_v2.theme.tokens import get_theme


def apply_collection_actions(actions, theme):
    visual = get_theme(theme.mode, profile='b2')
    actions.setStyleSheet(f'QWidget#{actions.objectName()} {{ background: transparent; border: 0; }}')
    if actions.layout() is not None:
        actions.layout().setContentsMargins(0, 8, 0, 8)
    play = getattr(actions, 'play_button', None) or getattr(actions, 'play_all_button', None)
    if play is not None:
        play.setStyleSheet(button_qss(visual, role='primary'))
    actions.shuffle_button.setStyleSheet(button_qss(visual, role='ghost'))


def apply_collection_page(page, theme):
    theme = theme or page.theme
    visual = get_theme(theme.mode, profile='b2')
    c = visual.colors
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    page.setStyleSheet(page.styleSheet() +
        f'QWidget#{page.objectName()} {{ background: {c.content_background}; }}'
        f'QWidget#{page.view_host.objectName()} {{ background: {c.content_background}; border: 0; border-radius: 0; }}')
    page.track_table.set_b2_theme(visual)
    page.empty_state.set_theme(visual)
    header = page.header
    header.set_theme(visual)
    header.accent_rail.hide()
    header.context_label.hide()
    # Keep the count label itself: duration updates and translations still
    # reach the original handle. Reapplying a theme never adds layout items.
    if header.title_row.layout().indexOf(header.count_label) >= 0:
        header.title_row.layout().removeWidget(header.count_label)
        header.identity.layout().addWidget(header.count_label)
    header.identity.layout().setSpacing(8)
    header.setMinimumHeight(110)
    header.count_label.setStyleSheet(
        f'color: {c.secondary_text}; background: transparent; border: 0; padding: 0; '
        f'font-size: {visual.fonts.metadata}px;')
    if getattr(page, 'search_box', None) is not None:
        page.search_box.set_theme(visual)
        page.search_box.line_edit.setStyleSheet(input_qss(visual, selector='QLineEdit#searchInput'))
    if getattr(page, 'toolbar', None) is not None:
        apply_collection_actions(page.toolbar, visual)
    if getattr(page, 'collection_actions', None) is not None:
        apply_collection_actions(page.collection_actions, visual)
    hero = getattr(page, 'collection_hero', None)
    if hero is not None:
        hero.set_theme(visual)
        hero.setStyleSheet('QWidget#trackCollectionHero { background: transparent; border: 0; }')
        hero.layout().setContentsMargins(0, 12, 0, 12)
        hero.play_button.setStyleSheet(button_qss(visual, role='primary'))
        hero.shuffle_button.setStyleSheet(button_qss(visual, role='ghost'))
