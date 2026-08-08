"""Queue floating panel backed by the one production playback queue."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.theme.icons import fluent_icon, icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.placeholder_cover import cover_pixmap
from app.ui_v2.widgets.track_display import display_track_text


class _QueueDelegate(QStyledItemDelegate):
    """Paint stable queue rows without letting the system draw blue selection."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._pixmaps: dict[str, QPixmap] = {}

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._pixmaps.clear()
        self.parent().viewport().update() if self.parent() is not None else None

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        return QSize(0, 62)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # noqa: N802
        track = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, Track):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(4, 3, -4, -3)
        if option.state & QStyle.StateFlag.State_Selected:
            background = self._theme.colors.selected_background
            border = self._theme.colors.accent
        elif option.state & QStyle.StateFlag.State_MouseOver:
            background = self._theme.colors.hover_background
            border = self._theme.colors.hover_background
        else:
            background = self._theme.colors.surface_elevated
            border = self._theme.colors.surface_elevated
        painter.setPen(border)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 8, 8)

        artwork_rect = rect.adjusted(8, 8, 0, -8)
        artwork_rect.setWidth(46)
        key = track.stable_id
        pixmap = self._pixmaps.get(key)
        if pixmap is None:
            pixmap = cover_pixmap(key, 46, 46)
            self._pixmaps[key] = pixmap
        painter.drawPixmap(artwork_rect, pixmap)

        title, artist, _album = display_track_text(track)
        text_left = artwork_rect.right() + 12
        duration = format_duration(track.duration_ms)
        duration_width = 48
        text_width = max(80, rect.right() - text_left - duration_width - 10)
        title_font = option.font
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(self._theme.colors.text_primary)
        title_text = QFontMetrics(title_font).elidedText(
            title, Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(text_left, rect.top() + 25, title_text)
        artist_font = option.font
        artist_font.setPointSize(max(8, artist_font.pointSize() - 1))
        painter.setFont(artist_font)
        painter.setPen(self._theme.colors.text_secondary)
        artist_text = QFontMetrics(artist_font).elidedText(
            artist, Qt.TextElideMode.ElideRight, text_width
        )
        painter.drawText(text_left, rect.top() + 44, artist_text)
        painter.setPen(self._theme.colors.text_tertiary)
        painter.drawText(rect.right() - duration_width, rect.top() + 35, duration)
        painter.restore()


class ImmersiveQueuePanel(QFrame):
    """A stable right-floating projection of the adapter-owned queue."""

    closed = Signal()
    selection_changed = Signal(str)

    def __init__(self, playback: PlaybackAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.playback = playback
        self._theme = theme
        self._selected_track_id = ""
        self.setObjectName("immersiveQueuePanel")
        self.setMinimumWidth(310)
        self.setMaximumWidth(410)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.title_label = QLabel("播放队列", self)
        self.count_label = QLabel(self)
        self.context_label = QLabel("当前播放上下文", self)
        self.close_button = QToolButton(self)
        self.close_button.setObjectName("immersiveQueueClose")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setIconSize(QSize(17, 17))
        self.close_button.clicked.connect(self.closed)

        self.current_section_label = QLabel("正在播放", self)
        self.current_row = QFrame(self)
        self.current_row.setObjectName("immersiveQueueCurrentRow")
        self.current_artwork = ArtworkThumbnail(theme, self.current_row, size=46)
        self.current_title_label = QLabel(self.current_row)
        self.current_artist_label = QLabel(self.current_row)
        self.current_playing_label = QLabel("播放中", self.current_row)
        current_text = QVBoxLayout()
        current_text.setContentsMargins(0, 0, 0, 0)
        current_text.setSpacing(2)
        current_text.addWidget(self.current_title_label)
        current_text.addWidget(self.current_artist_label)
        current_text.addWidget(self.current_playing_label)
        current_layout = QHBoxLayout(self.current_row)
        current_layout.setContentsMargins(10, 8, 10, 8)
        current_layout.setSpacing(10)
        current_layout.addWidget(self.current_artwork)
        current_layout.addLayout(current_text, 1)

        self.next_section_label = QLabel("接下来播放", self)
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("immersiveQueueList")
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.setMouseTracking(True)
        self._delegate = _QueueDelegate(theme, self.list_widget)
        self.list_widget.setItemDelegate(self._delegate)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._play_item)
        self.list_widget.itemActivated.connect(self._play_item)

        self.empty_label = QLabel("接下来没有歌曲", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()
        self.footer_label = QLabel(self)
        self.footer_label.setObjectName("immersiveQueueFooter")

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.addWidget(self.title_label)
        heading.addWidget(self.count_label)
        heading.addStretch(1)
        heading.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 14, 14)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addWidget(self.context_label)
        layout.addWidget(self.current_section_label)
        layout.addWidget(self.current_row)
        layout.addWidget(self.next_section_label)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.empty_label, 1)
        layout.addWidget(self.footer_label)

        playback.track_changed.connect(self.refresh)
        playback.queue_changed.connect(lambda _queue: self.refresh())
        self.refresh()
        self.set_theme(theme)

    @property
    def selected_track_id(self) -> str:
        return self._selected_track_id

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._delegate.set_theme(theme)
        colors = theme.colors
        self.setStyleSheet(
            f"QFrame#immersiveQueuePanel {{ background: {colors.surface_elevated}; border: 1px solid {colors.divider}; border-radius: 14px; }}"
            f"QFrame#immersiveQueueCurrentRow {{ background: {colors.playing_background}; border: 1px solid {colors.accent}; border-radius: 9px; }}"
            f"QLabel {{ background: transparent; color: {colors.text_primary}; }}"
            f"QListWidget {{ background: transparent; border: 0; outline: 0; padding: 0; }}"
            f"QListWidget::item {{ background: transparent; padding: 0; border: 0; }}"
            f"QToolButton {{ border: 0; border-radius: 16px; background: transparent; }}"
            f"QToolButton:hover {{ background: {colors.surface_hover}; }}"
            f"QToolButton:focus {{ border: 1px solid {colors.focus_ring}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 650; color: {colors.text_primary};"
        )
        for label in (self.count_label, self.context_label, self.current_artist_label, self.footer_label):
            label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {colors.text_secondary};")
        self.current_section_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 650; color: {colors.text_primary};"
        )
        self.next_section_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 650; color: {colors.text_primary};"
        )
        self.current_title_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; font-weight: 650; color: {colors.text_primary};"
        )
        self.current_playing_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {colors.accent};"
        )
        self.empty_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; color: {colors.text_secondary};"
        )
        self.close_button.setIcon(icon("window_close", theme))
        self.close_button.setToolTip("关闭队列")
        self.current_artwork.set_theme(theme)

    def refresh(self, *_args) -> None:
        tracks = tuple(self.playback.queue_tracks)
        current = self.playback.state.current_track
        current_id = current.id if current is not None else ""
        self.count_label.setText(f"{len(tracks)} 首")
        self.current_row.setVisible(current is not None)
        self.current_section_label.setVisible(current is not None)
        if current is not None:
            title, artist, _album = display_track_text(current)
            self.current_artwork.set_track(current)
            self.current_title_label.setText(title)
            self.current_artist_label.setText(artist or "未知艺人")
            self.current_title_label.setToolTip(title)
        upcoming = [track for track in tracks if track.id != current_id]
        self.list_widget.clear()
        for track in upcoming:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, track)
            item.setToolTip(display_track_text(track)[0])
            self.list_widget.addItem(item)
        self.next_section_label.setVisible(bool(upcoming) or current is not None)
        self.list_widget.setVisible(bool(upcoming))
        self.empty_label.setVisible(not upcoming)
        if not upcoming:
            self.empty_label.setText("队列中没有接下来的歌曲" if current is not None else "播放队列为空")
        self.footer_label.setText(
            f"第 {self.playback.state.current_index + 1} / {len(tracks)} 首" if current is not None else ""
        )
        self._selected_track_id = ""

    def _on_selection_changed(self) -> None:
        item = self.list_widget.currentItem()
        track = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._selected_track_id = track.id if isinstance(track, Track) else ""
        self.selection_changed.emit(self._selected_track_id)

    def _play_item(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(track, Track):
            self.playback.play_track(track.id)
