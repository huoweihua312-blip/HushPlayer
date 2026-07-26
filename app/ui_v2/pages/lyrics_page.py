"""Ordinary UI V2 lyrics page backed only by the deterministic LyricsAdapter."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedLayout, QVBoxLayout, QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.lyrics_state import LyricsState
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.lyrics_header import LyricsHeader
from app.ui_v2.widgets.lyrics_state_view import LyricsStateView
from app.ui_v2.widgets.lyrics_timeline import LyricsTimeline
from app.ui_v2.widgets.lyrics_view import LyricsView


class LyricsPage(QWidget):
    """Keeps its document, options, scroll position, and rows while cached by the router."""

    source_requested = Signal()
    immersive_requested = Signal()

    def __init__(self, adapter: LyricsAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self.setObjectName("lyricsPage")
        self.header = LyricsHeader(theme, self)
        self.timeline = LyricsTimeline(theme, self)
        self.side = QWidget(self)
        side_layout = QVBoxLayout(self.side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(theme.metrics.spacing_md)
        side_layout.addWidget(self.header)
        side_layout.addWidget(self.timeline)
        side_layout.addStretch(1)
        self.lyrics_view = LyricsView(theme, self)
        self.state_view = LyricsStateView(theme, self)
        self.content = QWidget(self)
        self.content_stack = QStackedLayout(self.content)
        self.content_stack.setContentsMargins(0, 0, 0, 0)
        self.content_stack.addWidget(self.lyrics_view)
        self.content_stack.addWidget(self.state_view)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.metrics.page_margin, theme.metrics.spacing_lg, theme.metrics.page_margin, theme.metrics.page_margin)
        layout.setSpacing(theme.metrics.spacing_lg)
        layout.addWidget(self.side)
        layout.addWidget(self.content, 1)
        self.side.setMinimumWidth(245)
        self.side.setMaximumWidth(320)
        self.header.translation_requested.connect(adapter.toggle_translation)
        self.header.romanization_requested.connect(adapter.toggle_romanization)
        self.header.font_scale_requested.connect(self._adjust_font_scale)
        self.header.immersive_requested.connect(self.immersive_requested)
        self.timeline.seek_requested.connect(adapter.request_seek)
        self.lyrics_view.seek_requested.connect(adapter.seek_to_line)
        self.state_view.retry_requested.connect(adapter.retry)
        self.state_view.source_requested.connect(self.source_requested)
        adapter.document_changed.connect(self._on_document_changed)
        adapter.state_changed.connect(self._on_state_changed)
        adapter.active_line_changed.connect(self.lyrics_view.set_active_line)
        adapter.active_segment_changed.connect(self.lyrics_view.set_active_segment)
        adapter.position_changed.connect(self.timeline.set_position)
        adapter.display_options_changed.connect(self._on_display_options)
        self._on_document_changed(adapter.document)
        self._on_state_changed(adapter.state)
        self._on_display_options(adapter.display_options)
        self.lyrics_view.set_active_line(adapter.active_line)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme))
        self.header.set_theme(theme)
        self.timeline.set_theme(theme)
        self.lyrics_view.set_theme(theme)
        self.state_view.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        narrow = width < 1_000
        self.side.setMinimumWidth(205 if narrow else 245)
        self.side.setMaximumWidth(240 if narrow else 320)
        self.header.cover_label.setVisible(not narrow)
        self.lyrics_view.set_horizontal_padding(
            32 if width < 1_100 else 88 if width < 1_400 else 150 if width < 1_600 else 190
        )

    def _on_document_changed(self, document: LyricsDocument | None) -> None:
        self.lyrics_view.set_document(document)
        self.lyrics_view.set_display_options(self.adapter.display_options)
        self.header.set_track(self.adapter.track, document)
        self.timeline.set_duration(self.adapter.track.duration_ms if self.adapter.track else None)

    def _on_state_changed(self, state: LyricsState) -> None:
        self.state_view.set_state(state)
        self.content_stack.setCurrentWidget(
            self.lyrics_view if state.phase == "ready" else self.state_view
        )

    def _on_display_options(self, options: dict[str, object]) -> None:
        self.header.set_options(options)
        self.lyrics_view.set_display_options(options)

    def _adjust_font_scale(self, delta: float) -> None:
        self.adapter.set_font_scale(float(self.adapter.display_options["font_scale"]) + delta)
