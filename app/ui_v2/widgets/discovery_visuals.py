"""B2 presentation helpers for collection/discovery pages; no data ownership."""
from PySide6.QtCore import Qt
from app.ui_v2.theme.tokens import get_theme
from app.ui_v2.widgets.collection_visuals import apply_collection_actions


def style_collection_detail(page, hero, theme):
    visual = get_theme(theme.mode, profile='b2')
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    page.setStyleSheet(page.styleSheet() +
        f'QWidget#{page.objectName()} {{ background: {visual.colors.content_background}; }}'
        f'QWidget#{page.view_host.objectName()} {{ background: {visual.colors.content_background}; border: 0; }}')
    page.track_table.set_b2_theme(visual)
    page.empty_state.set_theme(visual)
    hero.set_theme(visual)
    apply_collection_actions(hero, visual)
    hero.layout().setContentsMargins(0, 16, 0, 20)
    hero.layout().setSpacing(28)
    if hasattr(hero, 'owner_label'):
        hero.owner_label.setStyleSheet(f'color: {visual.colors.secondary_text}; font-size: {visual.fonts.metadata}px;')
    else:
        hero.title_label.setWordWrap(True)
        hero.meta_label.setWordWrap(True)


def style_entity_header(page, theme):
    page.setObjectName('entityGridPage')
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    page.scroll_area.setObjectName('entityScrollArea')
    page.content.setObjectName('entityGridContent')
    page.setStyleSheet(page.styleSheet() +
        f'QWidget#entityGridPage, QWidget#entityGridContent, QScrollArea#entityScrollArea '
        f'{{ background: {theme.colors.content_background}; border: 0; }}')
    page.grid.setHorizontalSpacing(24)
    page.grid.setVerticalSpacing(24)
    header = page.header
    header.accent_rail.hide()
    header.context_label.hide()
    if header.title_row.layout().indexOf(header.count_label) >= 0:
        header.title_row.layout().removeWidget(header.count_label)
        header.identity.layout().addWidget(header.count_label)
    header.identity.layout().setSpacing(8)
    header.count_label.setStyleSheet(
        f'color: {theme.colors.secondary_text}; background: transparent; border: 0; padding: 0;')
