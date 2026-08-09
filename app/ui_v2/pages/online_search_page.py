"""Quiet Orbit online discovery page backed by one shared query surface."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_search_state import OnlineSearchState
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.online_result_table import OnlineResultTable
from app.ui_v2.widgets.online_result_toolbar import OnlineResultToolbar
from app.ui_v2.widgets.online_search_bar import OnlineSearchBar
from app.ui_v2.widgets.search_history_view import SearchHistoryView
from app.ui_v2.widgets.search_state_view import SearchStateView
from app.ui_v2.widgets.source_selector import SourceSelector


class OnlineSearchPage(QWidget):
    """Keeps one result model and query state until the V2 shell is closed."""

    source_management_requested = Signal()

    def __init__(
        self,
        adapter: OnlineAdapter,
        playlists: PlaylistAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self.setObjectName("onlineSearchPage")
        self.title_label = QLabel("在线搜索", self)
        self.detail_label = QLabel("从已启用的在线来源聚合结果。", self)
        self.search_bar = OnlineSearchBar(theme, self)
        self.source_selector = SourceSelector(adapter, theme, self)
        self.source_summary_label = QLabel(self)
        self.recommendation_label = QLabel("推荐搜索", self)
        self.recommendation_widget = QWidget(self)
        recommendation_layout = QHBoxLayout(self.recommendation_widget)
        recommendation_layout.setContentsMargins(0, 0, 0, 0)
        recommendation_layout.setSpacing(6)
        recommendation_layout.addWidget(self.recommendation_label)
        self.recommendation_buttons: list[QToolButton] = []
        for query in ("夜航", "Paper Moon", "中文 English", "长标题"):
            button = QToolButton(self.recommendation_widget)
            button.setText(query)
            button.setToolTip(query)
            button.clicked.connect(lambda checked=False, value=query: self._search_history(value))
            recommendation_layout.addWidget(button)
            self.recommendation_buttons.append(button)
        recommendation_layout.addStretch(1)
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)
        search_row.addWidget(self.search_bar, 1)
        search_row.addWidget(self.source_selector)
        # The shell title bar is the single production query input. Keep this
        # control as a compatibility handle for deterministic tests.
        self.search_bar.setVisible(False)
        self.result_toolbar = OnlineResultToolbar(theme, self)
        self.result_table = OnlineResultTable(adapter, playlists, theme, self)
        self.history_view = SearchHistoryView(theme, self)
        self.state_view = SearchStateView(theme, self)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(metrics.page_margin, metrics.spacing_lg, metrics.page_margin, metrics.page_margin)
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addLayout(search_row)
        layout.addWidget(self.source_summary_label)
        layout.addWidget(self.recommendation_widget)
        layout.addWidget(self.result_toolbar)
        layout.addWidget(self.history_view, 1)
        layout.addWidget(self.state_view, 1)
        layout.addWidget(self.result_table, 1)
        self.search_bar.query_changed.connect(adapter.set_query)
        self.search_bar.search_requested.connect(self._search)
        self.history_view.query_requested.connect(self._search_history)
        self.history_view.remove_requested.connect(adapter.remove_history_item)
        self.history_view.clear_requested.connect(adapter.clear_history)
        self.state_view.cancel_requested.connect(adapter.cancel_search)
        self.state_view.retry_requested.connect(adapter.retry)
        self.state_view.sources_requested.connect(self.source_management_requested)
        self.state_view.history_requested.connect(adapter.clear_results)
        self.result_toolbar.retry_requested.connect(adapter.retry)
        self.result_toolbar.sources_requested.connect(self.source_management_requested)
        self.result_toolbar.source_filter_changed.connect(self.result_table.set_source_filter)
        self.result_toolbar.sort_changed.connect(self.result_table.set_sort_mode)
        self.result_table.source_requested.connect(self.source_management_requested)
        adapter.history_changed.connect(self.history_view.set_history)
        adapter.source_state_changed.connect(self._sync_sources)
        adapter.source_state_changed.connect(self.result_toolbar.set_sources)
        adapter.state_changed.connect(self._sync_state)
        adapter.search_results_changed.connect(lambda _results: self._sync_state(adapter.state))
        adapter.notification_changed.connect(self._sync_notification)
        self.search_bar.set_text(adapter.query)
        self.history_view.set_history(adapter.history())
        self._sync_sources(adapter.sources())
        self.result_toolbar.set_sources(adapter.sources())
        self.set_theme(theme)
        self._sync_state(adapter.state)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(f"color: {theme.colors.secondary_text};")
        self.source_summary_label.setStyleSheet(f"color: {theme.colors.subtle_text};")
        self.recommendation_label.setStyleSheet(f"color: {theme.colors.secondary_text};")
        recommendation_style = (
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_sm}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
        )
        for button in self.recommendation_buttons:
            button.setStyleSheet(recommendation_style)
        self.search_bar.set_theme(theme)
        self.source_selector.set_theme(theme)
        self.result_toolbar.set_theme(theme)
        self.result_table.set_theme(theme)
        self.history_view.set_theme(theme)
        self.state_view.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        narrow = width < 950
        self.detail_label.setVisible(not narrow)
        self.source_summary_label.setVisible(not narrow)
        self.source_selector.set_compact(narrow)
        self.result_table.set_responsive_reference_width(width)
        self.result_toolbar.set_compact(narrow)
        self.result_toolbar.sources_button.setText("来源" if narrow else "来源状态")

    def _search(self) -> None:
        self.adapter.search()

    def _search_history(self, query: str) -> None:
        self.search_bar.set_text(query)
        self.adapter.search()

    def _sync_state(self, state: OnlineSearchState) -> None:
        has_results = bool(self.adapter.results())
        self.history_view.setVisible(state.phase == "idle")
        self.recommendation_widget.setVisible(state.phase == "idle")
        self.result_table.setVisible(state.phase == "results" and has_results)
        self.result_toolbar.setVisible(state.phase == "results" and has_results)
        self.state_view.setVisible(not (state.phase == "results" and has_results))
        self.state_view.set_state(state)
        self.result_toolbar.set_summary(len(self.adapter.results()), state.message)

    def _sync_sources(self, sources) -> None:
        enabled = [source for source in sources if source.enabled]
        unavailable = [source for source in enabled if source.status in {"failed", "disabled"}]
        summary = f"已启用 {len(enabled)} 个在线来源"
        if unavailable:
            summary += f"，其中 {len(unavailable)} 个暂不可用"
        self.source_summary_label.setText(summary)

    def _sync_notification(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.detail_label.setText(text)
