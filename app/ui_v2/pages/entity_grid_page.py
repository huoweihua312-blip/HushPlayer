"""Reusable responsive entity grid that reflows existing cards without rebuilding them."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QScrollArea, QVBoxLayout, QWidget

from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.empty_state import EmptyState
from app.ui_v2.widgets.page_header import PageHeader
from app.ui_v2.widgets.search_box import SearchBox
from app.ui_v2.widgets.view_toggle import ViewToggle


class EntityGridPage(QWidget):
    """Maintains one card instance per aggregate entity while changing layout density."""

    entity_requested = Signal(str)

    def __init__(
        self,
        title: str,
        count_label: str,
        theme: Theme,
        *,
        search_callback: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._count_label = count_label
        self._cards: dict[str, QWidget] = {}
        self._entities: tuple[object, ...] = ()
        self._card_factory: Callable[[object], QWidget] | None = None
        self._card_updater: Callable[[QWidget, object], None] | None = None
        self._compact = False
        self._reflowing = False
        self._reflow_pending = False
        self.header = PageHeader(title, self)
        self.search_box = SearchBox(self)
        self.search_box.setMinimumWidth(220)
        self.view_toggle = ViewToggle(theme, self)
        self.header.trailing_layout.addWidget(self.search_box)
        self.header.trailing_layout.addWidget(self.view_toggle)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget(self.scroll_area)
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(theme.metrics.spacing_md)
        self.grid.setVerticalSpacing(theme.metrics.spacing_sm)
        self.grid.setRowStretch(999, 1)
        self.scroll_area.setWidget(self.content)
        self.empty_state = EmptyState(self)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(metrics.page_margin, metrics.spacing_lg, metrics.page_margin, metrics.page_margin)
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.header)
        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(self.empty_state, 1)
        self.empty_state.hide()
        self.search_box.text_changed.connect(search_callback)
        self.view_toggle.mode_changed.connect(lambda _mode: self._schedule_reflow())
        self.set_theme(theme)

    def configure_cards(
        self,
        card_factory: Callable[[object], QWidget],
        card_updater: Callable[[QWidget, object], None],
    ) -> None:
        self._card_factory = card_factory
        self._card_updater = card_updater

    def set_entities(self, entities: Iterable[object]) -> None:
        self._entities = tuple(entities)
        if self._card_factory is None or self._card_updater is None:
            return
        entity_ids = {getattr(entity, "id") for entity in self._entities}
        for entity_id, card in tuple(self._cards.items()):
            if entity_id not in entity_ids:
                self.grid.removeWidget(card)
                card.deleteLater()
                del self._cards[entity_id]
        for entity in self._entities:
            entity_id = getattr(entity, "id")
            card = self._cards.get(entity_id)
            if card is None:
                card = self._card_factory(entity)
                card.activated.connect(self.entity_requested)
                self._cards[entity_id] = card
            self._card_updater(card, entity)
        self.header.count_label.setText(f"{len(self._entities)} {self._count_label}")
        self.scroll_area.setVisible(bool(self._entities))
        self.empty_state.setVisible(not self._entities)
        self._schedule_reflow()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.header.set_theme(theme)
        self.search_box.set_theme(theme)
        self.view_toggle.set_theme(theme)
        self.empty_state.set_theme(theme)
        for card in self._cards.values():
            card.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        compact = width < 950
        if compact != self._compact:
            self._compact = compact
            self._schedule_reflow()
        self.search_box.setMinimumWidth(160 if compact else 220)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def _schedule_reflow(self) -> None:
        if self._reflow_pending:
            return
        self._reflow_pending = True
        QTimer.singleShot(0, self._reflow_cards)

    def _reflow_cards(self) -> None:
        self._reflow_pending = False
        if self._reflowing or not self._cards:
            return
        self._reflowing = True
        try:
            while self.grid.count():
                self.grid.takeAt(0)
            columns = 1 if self._compact or self.view_toggle.mode == "list" else 2
            for index, entity in enumerate(self._entities):
                card = self._cards[getattr(entity, "id")]
                self.grid.addWidget(card, index // columns, index % columns)
            self.grid.setColumnStretch(columns, 1)
        finally:
            self._reflowing = False
