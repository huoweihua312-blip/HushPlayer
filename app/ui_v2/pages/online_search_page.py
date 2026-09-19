"""Quiet Orbit online discovery page backed by one shared query surface."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_search_state import OnlineSearchState
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.online_result_table import OnlineResultTable
from app.ui_v2.widgets.online_result_toolbar import OnlineResultToolbar
from app.ui_v2.widgets.online_search_bar import OnlineSearchBar
from app.ui_v2.widgets.search_history_view import SearchHistoryView
from app.ui_v2.widgets.search_state_view import SearchStateView
from app.ui_v2.widgets.source_selector import SourceSelector
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.online_presentation import style_action, style_caption


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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.identity_surface = QFrame(self)
        self.identity_surface.setObjectName("onlineSearchIdentitySurface")
        self.result_surface = QFrame(self)
        self.result_surface.setObjectName("onlineSearchResultSurface")
        self.title_label = QLabel("在线搜索", self.identity_surface)
        self.title_label.setObjectName("onlineSearchTitle")
        self.detail_label = QLabel("从已启用的在线来源聚合结果。", self.identity_surface)
        self.detail_label.setObjectName("onlineSearchDetail")
        self.query_context_label = ElidedLabel(self)
        self.query_context_label.setObjectName("onlineSearchQueryContext")
        self.search_bar = OnlineSearchBar(theme, self)
        self.source_selector = SourceSelector(adapter, theme, self)
        self.source_summary_label = QLabel(self)
        self.search_bar.setMinimumWidth(420)
        self.search_bar.setMaximumWidth(16777215)
        self.search_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.result_toolbar = OnlineResultToolbar(theme, self.result_surface)
        self.result_table = OnlineResultTable(adapter, playlists, theme, self.result_surface)
        self.history_view = SearchHistoryView(theme, self.result_surface)
        self.history_view.setObjectName("onlineSearchHistorySurface")
        self.state_view = SearchStateView(theme, self.result_surface)
        self.state_view.setObjectName("onlineSearchStateSurface")
        self.state_view.progress.setFixedSize(180, 3)
        self.state_view.progress.setTextVisible(False)
        self.state_view.layout().setAlignment(self.state_view.progress, Qt.AlignmentFlag.AlignHCenter)
        identity_heading = QVBoxLayout()
        identity_heading.setContentsMargins(0, 0, 0, 0)
        identity_heading.setSpacing(9)
        self.eyebrow = QLabel("在线音乐", self)
        identity_heading.addWidget(self.eyebrow)
        identity_heading.addWidget(self.title_label)
        identity_heading.addWidget(self.detail_label)
        self.source_summary_label.show()
        self.query_context_label.hide()
        identity_layout = QVBoxLayout(self.identity_surface)
        identity_layout.setContentsMargins(0, 0, 0, 14)
        identity_layout.setSpacing(18)
        top = QHBoxLayout()
        top.addLayout(identity_heading, 0)
        top.addSpacing(42)
        top.addWidget(self.search_bar, 1, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.result_toolbar.sources_button, 0, Qt.AlignmentFlag.AlignVCenter)
        identity_layout.addLayout(top)
        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.setSpacing(theme.metrics.spacing_sm)
        scope_row.addWidget(self.source_selector, 0, Qt.AlignmentFlag.AlignVCenter)
        scope_row.addWidget(self.source_summary_label, 0, Qt.AlignmentFlag.AlignVCenter)
        scope_row.addStretch(1)
        identity_layout.addLayout(scope_row)
        self.feedback_label = ElidedLabel(self)
        identity_layout.addSpacing(12)
        identity_layout.addWidget(self.feedback_label)
        result_layout = QVBoxLayout(self.result_surface)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(theme.metrics.spacing_sm)
        result_layout.addWidget(self.result_toolbar)
        result_layout.addWidget(self.history_view)
        result_layout.addWidget(self.state_view, 1)
        result_layout.addWidget(self.result_table, 1)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(42, 32, 42, 30)
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.identity_surface)
        layout.addWidget(self.result_surface, 1)
        self.result_table.setMinimumHeight(180)
        self.search_bar.query_changed.connect(lambda _text: self._sync_query_context())
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
        self.search_bar.set_text("")
        self.history_view.set_history(adapter.history())
        self._sync_sources(adapter.sources())
        self.result_toolbar.set_sources(adapter.sources())
        self.set_theme(theme)
        self._sync_state(adapter.state)

    def set_theme(self, theme: Theme) -> None:
        theme = get_theme(theme.mode, profile="b2")
        self._theme = theme
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            build_stylesheet(theme)
            + f"""
            QWidget#onlineSearchPage {{ background: {colors.app_background}; }}
            QFrame#onlineSearchIdentitySurface {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QFrame#onlineSearchResultSurface {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QLabel#onlineSearchTitle {{
                font-size: {theme.fonts.page_title}px;
                font-weight: 600;
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
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QWidget#onlineSearchStateSurface {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QTableView#onlineResultTable {{
                background: {colors.content_background};
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
        self.history_view.setStyleSheet(self.history_view.styleSheet() +
            "QWidget#onlineSearchHistorySurface, QWidget#searchHistoryRow { border: 0; background: transparent; }")
        self.state_view.title_label.setStyleSheet(f"font-size: 20px; font-weight: 500; color: {colors.primary_text};")
        self.state_view.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style_caption(self.state_view.detail_label, theme)
        for button in (self.state_view.cancel_button, self.state_view.sources_button, self.state_view.history_button):
            style_action(button, theme)
        style_action(self.state_view.retry_button, theme, primary=True)
        for label in (self.eyebrow, self.feedback_label):
            style_caption(label, theme, subtle=True)
        style_caption(self.detail_label, theme)
        style_action(self.result_toolbar.sources_button, theme)
        self.source_selector.setStyleSheet(self.source_selector.styleSheet() +
            "QToolButton#onlineSourceSelector { border: 0; background: transparent; font-size: 13px; }")

    def set_responsive_reference_width(self, width: int) -> None:
        self._responsive_width = max(1, int(width))
        narrow = width < 950
        inset = 28 if narrow else 42
        self.layout().setContentsMargins(inset, 32, inset, 30)
        self.source_selector.set_compact(narrow)
        self.result_table.set_responsive_reference_width(width)
        self.result_toolbar.set_compact(narrow)
        self.result_toolbar.sources_button.setText("来源" if narrow else "管理来源")
        self.search_bar.setMinimumWidth(360 if narrow else 420)
        self.search_bar.setMaximumWidth(16777215)
        self.identity_surface.setMinimumHeight(0)
        self._sync_header_visibility()

    def _search(self) -> None:
        self.adapter.set_query(self.search_bar.line_edit.text())
        self.adapter.search()

    def _search_history(self, query: str) -> None:
        self.search_bar.set_text(query)
        self.adapter.set_query(query)
        self.adapter.search()

    def _sync_state(self, state: OnlineSearchState) -> None:
        has_results = bool(self.adapter.results())
        has_history = bool(self.adapter.history())
        self.history_view.setVisible(state.phase == "idle" and has_history)
        self.result_table.setVisible(state.phase == "results" and has_results)
        self.result_toolbar.setVisible(state.phase == "results" and has_results)
        self.state_view.setVisible(not (state.phase == "results" and has_results))
        self.state_view.set_state(state)
        self.state_view.progress.setToolTip(f"搜索进度：{state.progress}%")
        self.result_toolbar.set_summary(len(self.adapter.results()), state.message)
        self.feedback_label.set_full_text(state.message or ("聚合查询完成 · 来源信息仅供选择时参考" if has_results else ""))
        self._sync_query_context()
        self._sync_header_visibility()

    def _sync_header_visibility(self) -> None:
        """Keep query and scope anchored across loading, failure and results."""

        narrow = (self._responsive_width or 1200) < 950
        self.detail_label.setVisible(True)
        self.source_summary_label.show()
        self.identity_surface.setMinimumHeight(0)

    def _sync_sources(self, sources) -> None:
        self._sync_header_visibility()
        enabled = [source for source in sources if source.enabled]
        unavailable = [source for source in enabled if source.status in {"failed", "disabled"}]
        summary = f"已启用 {len(enabled)} 个在线来源"
        if unavailable:
            summary += f"，其中 {len(unavailable)} 个暂不可用"
        self.source_summary_label.setText(summary)

    def _sync_query_context(self) -> None:
        query = str(self.search_bar.line_edit.text() or "").strip()
        self.query_context_label.set_full_text(
            f"当前搜索：{query}" if query else "尚未输入关键词"
        )

    def _sync_notification(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.detail_label.setText(text)
