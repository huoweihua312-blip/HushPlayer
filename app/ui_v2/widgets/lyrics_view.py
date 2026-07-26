"""Scrollable lyric rows with one replaceable follow animation and browse mode."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QScrollArea, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.lyric_line_item import LyricLineItem


class LyricsView(QWidget):
    seek_requested = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._document: LyricsDocument | None = None
        self._items: dict[str, LyricLineItem] = {}
        self._active_line_id = ""
        self._browsing = False
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("lyricsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.viewport().installEventFilter(self)
        self.scroll_area.verticalScrollBar().sliderPressed.connect(self._enter_browse_mode)
        self.content = QWidget(self.scroll_area)
        self.content.setObjectName("lyricsContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(32, 26, 32, 42)
        self.content_layout.setSpacing(8)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)
        self.return_button = QToolButton(self.scroll_area.viewport())
        self.return_button.setText("回到当前歌词")
        self.return_button.clicked.connect(self.return_to_current)
        self.return_button.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area, 1)
        self._animation = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value", self)
        self._animation.setDuration(180)
        self.set_theme(theme)

    @property
    def browsing(self) -> bool:
        return self._browsing

    @property
    def document(self) -> LyricsDocument | None:
        return self._document

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._apply_surface_palette(self, theme.colors.content_background)
        self._apply_surface_palette(self.scroll_area, theme.colors.content_background)
        self._apply_surface_palette(self.scroll_area.viewport(), theme.colors.content_background)
        self._apply_surface_palette(self.content, theme.colors.content_background)
        self.scroll_area.setStyleSheet(
            f"QScrollArea#lyricsScrollArea, QAbstractScrollArea#lyricsScrollArea::viewport, QWidget#lyricsContent "
            f"{{ border: 0; background: {theme.colors.content_background}; }}"
            f"QScrollBar:vertical {{ width: 5px; margin: 8px 2px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ min-height: 22px; border-radius: 2px; background: {theme.colors.border}; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.colors.border_strong}; }}"
        )
        self.return_button.setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; "
            f"border: 0; border-radius: {theme.metrics.radius_sm}px; color: {theme.colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {theme.colors.hover_background}; }}"
        )
        for item in self._items.values():
            item.set_theme(theme)

    def set_document(self, document: LyricsDocument | None) -> None:
        if document is self._document:
            return
        self._animation.stop()
        self._document = document
        self._active_line_id = ""
        self._browsing = False
        self.return_button.hide()
        while self.content_layout.count() > 1:
            entry = self.content_layout.takeAt(0)
            if entry.widget() is not None:
                entry.widget().deleteLater()
        self._items.clear()
        if document is None:
            return
        for line in document.lines:
            item = LyricLineItem(line, self._theme, self.content)
            item.clicked.connect(self._on_line_clicked)
            self._items[line.id] = item
            self.content_layout.insertWidget(self.content_layout.count() - 1, item)

    def set_display_options(self, options: dict[str, object]) -> None:
        for item in self._items.values():
            item.set_display_options(options)

    def set_horizontal_padding(self, padding: int) -> None:
        self.content_layout.setContentsMargins(max(24, int(padding)), 26, max(24, int(padding)), 42)

    def set_active_line(self, line: LyricLine | None) -> None:
        next_id = line.id if line is not None else ""
        if next_id == self._active_line_id:
            return
        previous = self._items.get(self._active_line_id)
        if previous is not None:
            previous.set_active(False)
        self._active_line_id = next_id
        current = self._items.get(next_id)
        if current is not None:
            current.set_active(True)
            if not self._browsing:
                self._follow_item(current)

    def set_active_segment(self, line: LyricLine, segment_index: int, progress: float) -> None:
        item = self._items.get(line.id)
        if item is not None and line.id == self._active_line_id:
            item.set_active(True, segment_index, progress)

    def return_to_current(self) -> None:
        self._browsing = False
        self.return_button.hide()
        current = self._items.get(self._active_line_id)
        if current is not None:
            self._follow_item(current)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Wheel:
            self._enter_browse_mode()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for item in self._items.values():
            item.updateGeometry()
        self._position_return_button()

    def _on_line_clicked(self, line_id: str) -> None:
        self.seek_requested.emit(line_id)

    def _enter_browse_mode(self) -> None:
        if self._browsing:
            return
        self._browsing = True
        self._animation.stop()
        self._position_return_button()
        self.return_button.show()
        self.return_button.raise_()

    def _position_return_button(self) -> None:
        self.return_button.adjustSize()
        viewport = self.scroll_area.viewport()
        self.return_button.move(
            max(8, viewport.width() - self.return_button.width() - 14),
            max(8, viewport.height() - self.return_button.height() - 14),
        )

    def _follow_item(self, item: LyricLineItem) -> None:
        bar = self.scroll_area.verticalScrollBar()
        target = max(0, min(bar.maximum(), item.y() - self.scroll_area.viewport().height() // 3))
        if abs(target - bar.value()) < 3:
            return
        self._animation.stop()
        self._animation.setStartValue(bar.value())
        self._animation.setEndValue(target)
        self._animation.start()

    @staticmethod
    def _apply_surface_palette(widget: QWidget, background: str) -> None:
        palette = widget.palette()
        color = QColor(background)
        palette.setColor(QPalette.ColorRole.Window, color)
        palette.setColor(QPalette.ColorRole.Base, color)
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)
