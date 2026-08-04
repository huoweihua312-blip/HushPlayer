"""Reusable virtualized TrackTable page for shared mock library views."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedLayout, QVBoxLayout, QWidget

from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.empty_state import EmptyState
from app.ui_v2.widgets.page_header import PageHeader
from app.ui_v2.widgets.search_box import SearchBox
from app.ui_v2.widgets.section_toolbar import SectionToolbar
from app.ui_v2.widgets.track_table import TrackTable


class TrackListPage(QWidget):
    """Preserves one TrackTable model and one view-local adapter state per route."""

    track_play_requested = Signal(object, str)
    queue_requested = Signal(object, bool)
    browse_library_requested = Signal()

    def __init__(
        self,
        title: str,
        adapter: TrackListAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self.current_view_state = "content"
        self._content_safe_bottom = 0
        self.setObjectName("trackListPage")
        self.header = PageHeader(title, self)
        self.search_box = SearchBox(self)
        self.search_box.setMinimumWidth(220)
        self.header.trailing_layout.addWidget(self.search_box)
        self.toolbar = SectionToolbar(theme, self)
        self.track_table = TrackTable(adapter, theme, self)
        self.empty_state = EmptyState(self)
        self.view_host = QWidget(self)
        self.view_stack = QStackedLayout(self.view_host)
        self.view_stack.setContentsMargins(0, 0, 0, 0)
        self.view_stack.addWidget(self.track_table)
        self.view_stack.addWidget(self.empty_state)
        layout = QVBoxLayout(self)
        metrics = theme.metrics
        layout.setContentsMargins(
            metrics.page_margin,
            metrics.spacing_lg,
            metrics.page_margin,
            metrics.page_margin,
        )
        layout.setSpacing(metrics.spacing_md)
        layout.addWidget(self.header)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.view_host, 1)
        self.search_box.text_changed.connect(adapter.set_query)
        self.toolbar.play_all_requested.connect(lambda: self._request_queue(False))
        self.toolbar.shuffle_requested.connect(lambda: self._request_queue(True))
        self.track_table.play_requested.connect(self._request_track)
        self.empty_state.action_requested.connect(self.browse_library_requested)
        adapter.tracks_reset.connect(self._on_tracks_reset)
        self.set_theme(theme)
        self._on_tracks_reset(adapter.tracks())

    def set_content_safe_bottom(self, height: int) -> None:
        """Reserve one shared bottom-safe area for the global PlayerBar."""

        self._content_safe_bottom = max(0, int(height))
        self.view_stack.setContentsMargins(0, 0, 0, self._content_safe_bottom)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.header.set_theme(theme)
        self.search_box.set_theme(theme)
        self.toolbar.set_theme(theme)
        self.empty_state.set_theme(theme)
        self.track_table.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        self.track_table.set_responsive_reference_width(width)
        compact = width < 950
        self.search_box.setMinimumWidth(160 if compact else 220)
        self.toolbar.shuffle_button.setText("随机" if compact else "随机播放")
        self.toolbar.play_all_button.setText("播放" if compact else "播放全部")

    def _on_tracks_reset(self, tracks) -> None:
        self.header.set_count(len(tracks))
        self.toolbar.setEnabled(bool(tracks))
        if not tracks:
            self.current_view_state = "empty"
            self.view_stack.setCurrentWidget(self.empty_state)
        elif self.current_view_state == "empty":
            self.current_view_state = "content"
            self.view_stack.setCurrentWidget(self.track_table)

    def _request_track(self, track_id: str) -> None:
        self.track_play_requested.emit(self.adapter.tracks(), track_id)

    def _request_queue(self, shuffle: bool) -> None:
        tracks = tuple(track for track in self.adapter.tracks() if not track.is_missing)
        if tracks:
            self.queue_requested.emit(tracks, shuffle)
