"""Quiet Orbit online discovery page backed by one shared query surface."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

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
        self._responsive_width: int | None = None
        self.setObjectName("onlineSearchPage")
        self.identity_surface = QFrame(self)
        self.identity_surface.setObjectName("onlineSearchIdentitySurface")
        self.result_surface = QFrame(self)
        self.result_surface.setObjectName("onlineSearchResultSurface")
        self.title_label = QLabel("在线搜索", self.identity_surface)
        self.title_label.setObjectName("onlineSearchTitle")
        self.detail_label = QLabel("从已启用的在线来源聚合结果。", self.identity_surface)
        self.detail_label.setObjectName("onlineSearchDetail")
        self.query_context_label = QLabel(self)
        self.query_context_label.setObjectName("onlineSearchQueryContext")
        self.scope_label = QLabel("搜索范围：已启用的在线来源", self)
        self.scope_label.setObjectName("onlineSearchScope")
        self.search_bar = OnlineSearchBar(theme, self)
        self.source_selector = SourceSelector(adapter, theme, self)
        self.source_summary_label = QLabel(self)
        # The shell title bar is the single production query input. Keep this
        # control as a compatibility handle for deterministic tests.
        self.search_bar.setVisible(False)
        self.result_toolbar = OnlineResultToolbar(theme, self.result_surface)
        self.result_table = OnlineResultTable(adapter, playlists, theme, self.result_surface)
        self.history_view = SearchHistoryView(theme, self.result_surface)
        self.history_view.setObjectName("onlineSearchHistorySurface")
        self.state_view = SearchStateView(theme, self.result_surface)
        self.state_view.setObjectName("onlineSearchStateSurface")
        identity_heading = QVBoxLayout()
        identity_heading.setContentsMargins(0, 0, 0, 0)
        identity_heading.setSpacing(3)
        identity_heading.addWidget(self.title_label)
        identity_heading.addWidget(self.detail_label)
        identity_context = QHBoxLayout()
        identity_context.setContentsMargins(0, 0, 0, 0)
        identity_context.setSpacing(theme.metrics.spacing_sm)
        identity_context.addWidget(self.query_context_label)
        identity_context.addWidget(self.scope_label)
        identity_context.addWidget(self.source_summary_label)
        identity_context.addStretch(1)
        identity_context.addWidget(self.source_selector)
        identity_layout = QVBoxLayout(self.identity_surface)
        identity_layout.setContentsMargins(20, 18, 20, 18)
        identity_layout.setSpacing(14)
        identity_layout.addLayout(identity_heading)
        identity_layout.addLayout(identity_context)
        result_layout = QVBoxLayout(self.result_surface)
        result_layout.setContentsMargins(12, 12, 12, 12)
        result_layout.setSpacing(theme.metrics.spacing_sm)
        result_layout.addWidget(self.result_toolbar)
        result_layout.addWidget(self.history_view)
        result_layout.addWidget(self.state_view, 1)
        result_layout.addWidget(self.result_table, 1)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(metrics.page_margin, metrics.spacing_lg, metrics.page_margin, metrics.page_margin)
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.identity_surface)
        layout.addWidget(self.result_surface, 1)
        self.result_table.setMinimumHeight(260)
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
        adapter.query_changed.connect(lambda _query: self._sync_query_context())
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
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            build_stylesheet(theme)
            + f"""
            QFrame#onlineSearchIdentitySurface {{
                background: {colors.surface_primary};
                border: 1px solid {colors.border};
                border-radius: {metrics.radius_lg}px;
            }}
            QFrame#onlineSearchResultSurface {{
                background: {colors.surface_primary};
                border: 1px solid {colors.border};
                border-radius: {metrics.radius_lg}px;
            }}
            QLabel#onlineSearchTitle {{
                font-size: {theme.fonts.page_title}px;
                font-weight: 700;
                color: {colors.primary_text};
            }}
            QLabel#onlineSearchDetail {{ color: {colors.secondary_text}; }}
            QLabel#onlineSearchQueryContext {{
                color: {colors.primary_text};
                font-size: {theme.fonts.secondary}px;
                font-weight: 600;
            }}
            QLabel#onlineSearchScope {{
                color: {colors.subtle_text};
                font-size: {theme.fonts.caption}px;
            }}
            QWidget#onlineSearchHistorySurface {{
                background: {colors.surface_secondary};
                border: 1px solid {colors.border};
                border-radius: {metrics.radius_md}px;
            }}
            QWidget#onlineSearchStateSurface {{
                background: {colors.surface_secondary};
                border: 1px solid {colors.border};
                border-radius: {metrics.radius_md}px;
            }}
            QTableView#onlineResultTable {{
                background: {colors.surface_primary};
                border: 0;
            }}
            """
        )
        self.source_summary_label.setStyleSheet(
            f"padding: 3px 8px; border-radius: {metrics.radius_sm}px; background: {colors.surface_secondary}; "
            f"color: {colors.secondary_text}; font-size: {theme.fonts.caption}px;"
        )
        self.search_bar.set_theme(theme)
        self.source_selector.set_theme(theme)
        self.result_toolbar.set_theme(theme)
        self.result_table.set_theme(theme)
        self.history_view.set_theme(theme)
        self.state_view.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        self._responsive_width = max(1, int(width))
        narrow = width < 950
        self.source_selector.set_compact(narrow)
        self.result_table.set_responsive_reference_width(width)
        self.result_toolbar.set_compact(narrow)
        self.result_toolbar.sources_button.setText("来源" if narrow else "管理来源")
        self.identity_surface.setMinimumHeight(112 if narrow else 126)
        self._sync_header_visibility()

    def _search(self) -> None:
        self.adapter.search()

    def _search_history(self, query: str) -> None:
        self.search_bar.set_text(query)
        self.adapter.search()

    def _sync_state(self, state: OnlineSearchState) -> None:
        has_results = bool(self.adapter.results())
        has_history = bool(self.adapter.history())
        self.history_view.setVisible(state.phase == "idle" and has_history)
        self.result_table.setVisible(state.phase == "results" and has_results)
        self.result_toolbar.setVisible(state.phase == "results" and has_results)
        self.state_view.setVisible(not (state.phase == "results" and has_results))
        self.state_view.set_state(state)
        self.result_toolbar.set_summary(len(self.adapter.results()), state.message)
        self._sync_query_context()
        self._sync_header_visibility(has_results)

    def _sync_header_visibility(self, has_results: bool | None = None) -> None:
        """Give the result table priority once a search has completed."""

        if has_results is None:
            has_results = bool(self.adapter.results()) and self.adapter.state.phase == "results"
        narrow = (self._responsive_width or 1200) < 950
        show_context = not bool(has_results)
        self.detail_label.setVisible(show_context and not narrow)
        self.scope_label.setVisible(show_context and not narrow)
        self.source_summary_label.setVisible(show_context and not narrow)
        self.identity_surface.setMinimumHeight(88 if has_results else 112 if narrow else 126)

    def _sync_sources(self, sources) -> None:
        enabled = [source for source in sources if source.enabled]
        unavailable = [source for source in enabled if source.status in {"failed", "disabled"}]
        summary = f"已启用 {len(enabled)} 个在线来源"
        if unavailable:
            summary += f"，其中 {len(unavailable)} 个暂不可用"
        self.source_summary_label.setText(summary)

    def _sync_query_context(self) -> None:
        query = str(self.adapter.query or "").strip()
        self.query_context_label.setText(
            f"当前搜索：{query}" if query else "尚未输入关键词"
        )

    def _sync_notification(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.detail_label.setText(text)
