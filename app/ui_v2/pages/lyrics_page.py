"""The compact, PlayerBar-backed ordinary lyrics page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QStackedLayout, QVBoxLayout, QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.lyrics_state import LyricsState
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.compact_lyrics_toolbar import CompactLyricsToolbar
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2
from app.ui_v2.widgets.lyrics_state_view import LyricsStateView


class LyricsPage(QWidget):
    """One centred lyric column; playback identity remains exclusively in PlayerBar."""

    source_requested = Signal()
    immersive_requested = Signal()

    def __init__(self, adapter: LyricsAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._theme = theme
        self.setObjectName("lyricsPage")
        self._content_container = QWidget(self)
        self._content_container.setObjectName("ordinaryLyricsContentContainer")
        self._content_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._content_container.setAutoFillBackground(False)
        self.toolbar = CompactLyricsToolbar(theme, self._content_container)
        self.header = self.toolbar  # Compatibility name for route integrations, not an old header widget.
        # Keep the public alias for consumers that identify the lyric reading surface.
        self.lyrics_view = LyricsCanvasV2(theme, self._content_container)
        self.lyrics_view.set_mode("ordinary")
        self.canvas = self.lyrics_view
        self.state_view = LyricsStateView(theme, self._content_container)
        self._canvas_host = QWidget(self._content_container)
        canvas_host_layout = QHBoxLayout(self._canvas_host)
        canvas_host_layout.setContentsMargins(0, 0, 0, 0)
        canvas_host_layout.addStretch(1)
        canvas_host_layout.addWidget(self.lyrics_view)
        canvas_host_layout.addStretch(1)
        self.content = QWidget(self._content_container)
        self.content_stack = QStackedLayout(self.content)
        self.content_stack.setContentsMargins(0, 0, 0, 0)
        self.content_stack.addWidget(self._canvas_host)
        self.content_stack.addWidget(self.state_view)
        content_layout = QVBoxLayout(self._content_container)
        content_layout.setContentsMargins(0, 16, 0, 18)
        content_layout.setSpacing(4)
        content_layout.addWidget(self.toolbar)
        content_layout.addWidget(self.content, 1)
        self._content_layout = content_layout
        self._content_host = QWidget(self)
        host_layout = QHBoxLayout(self._content_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addStretch(1)
        host_layout.addWidget(self._content_container)
        host_layout.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content_host, 1)
        # Deprecated visual components deliberately are not allocated here: no header,
        # artwork identity, timeline, in-page transport or secondary player column.
        self.toolbar.translation_requested.connect(adapter.toggle_translation)
        self.toolbar.romanization_requested.connect(adapter.toggle_romanization)
        self.toolbar.immersive_requested.connect(self.immersive_requested)
        self.toolbar.more_menu.actions()[0].triggered.connect(self.lyrics_view.return_to_current)
        self.lyrics_view.seek_requested.connect(adapter.seek_to_line)
        self.state_view.retry_requested.connect(adapter.retry)
        self.state_view.source_requested.connect(self.source_requested)
        adapter.document_changed.connect(self._on_document_changed)
        adapter.state_changed.connect(self._on_state_changed)
        adapter.active_line_changed.connect(self.lyrics_view.set_active_line)
        adapter.active_segment_changed.connect(self.lyrics_view.set_active_segment)
        adapter.display_options_changed.connect(self._on_display_options)
        self._on_document_changed(adapter.document)
        self._on_state_changed(adapter.state)
        self._on_display_options(adapter.display_options)
        self.lyrics_view.set_active_line(adapter.active_line)
        self.set_theme(theme)

    @property
    def lyric_column_count(self) -> int:
        return 1

    @property
    def has_in_page_playback_controls(self) -> bool:
        return False

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(f"QWidget#lyricsPage {{ background: {theme.colors.content_background}; }}")
        self.toolbar.set_theme(theme)
        self.lyrics_view.set_theme(theme)
        self.state_view.set_theme(theme)

    def set_responsive_reference_width(self, width: int, height: int | None = None) -> None:
        viewport_height = max(1, int(height or self.height() or 600))
        compact = width < 900
        self.lyrics_view.set_ordinary_viewport(width, viewport_height, self.devicePixelRatioF())
        metrics = self.lyrics_view.responsive_metrics
        lyrics_max_width = metrics.lyrics_max_width if metrics is not None else min(820, width)
        container_width = min(1020, max(320, min(width - (32 if compact else 64), lyrics_max_width + 40)))
        self._content_container.setMaximumWidth(container_width)
        self._content_container.setMinimumWidth(min(320, container_width))
        self._content_layout.setContentsMargins(0, 10 if compact else 16, 0, 12 if compact else 18)
        self.toolbar.set_compact(compact)
        canvas_width = min(lyrics_max_width, container_width)
        self.lyrics_view.setMaximumWidth(canvas_width)
        self.lyrics_view.setFixedWidth(canvas_width)
        self.lyrics_view.set_responsive_scale(1.0)
        self.lyrics_view.set_max_text_width(canvas_width)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Router resize notifications use MainWindow width.  Reconcile with the
        # actual content width as well, so a visible sidebar never compresses
        # the centred canvas into a third-width column.
        self.set_responsive_reference_width(self.width(), self.height())

    def _on_document_changed(self, document: LyricsDocument | None) -> None:
        self.lyrics_view.set_document(document)
        self.lyrics_view.set_display_options(self.adapter.display_options)

    def _on_state_changed(self, state: LyricsState) -> None:
        self.state_view.set_state(state)
        self.content_stack.setCurrentWidget(self._canvas_host if state.phase == "ready" else self.state_view)

    def _on_display_options(self, options: dict[str, object]) -> None:
        self.toolbar.set_options(options)
        self.lyrics_view.set_display_options(options)
