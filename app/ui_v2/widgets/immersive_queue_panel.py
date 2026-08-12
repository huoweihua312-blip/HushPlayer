"""Formal immersive playback queue shown inside a stable floating panel."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListView, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget

from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.theme.immersive_tokens import IMMERSIVE_GLASS
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.immersive_side_drawer import ImmersiveFloatingPanel
from app.ui_v2.widgets.placeholder_cover import cover_pixmap
from app.ui_v2.widgets.track_display import display_track_text


class _QueueTrackModel(QAbstractListModel):
    """A projection of adapter-owned tracks, not a second queue or model."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracks: tuple[Track, ...] = ()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._tracks)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or not 0 <= index.row() < len(self._tracks):
            return None
        track = self._tracks[index.row()]
        title, artist, _album = display_track_text(track)
        if role == Qt.ItemDataRole.UserRole:
            return track
        if role == Qt.ItemDataRole.ToolTipRole:
            return title if not artist else f"{title}\n{artist}"
        if role == Qt.ItemDataRole.DisplayRole:
            return title
        return None

    def set_tracks(self, tracks: tuple[Track, ...]) -> None:
        if tracks == self._tracks:
            return
        old_tracks = self._tracks
        prefix = 0
        while (
            prefix < len(old_tracks)
            and prefix < len(tracks)
            and old_tracks[prefix].id == tracks[prefix].id
        ):
            prefix += 1
        suffix = 0
        while (
            suffix < len(old_tracks) - prefix
            and suffix < len(tracks) - prefix
            and old_tracks[len(old_tracks) - suffix - 1].id == tracks[len(tracks) - suffix - 1].id
        ):
            suffix += 1

        remove_count = len(old_tracks) - prefix - suffix
        insert_values = tracks[prefix : len(tracks) - suffix if suffix else len(tracks)]
        values = list(old_tracks)
        if remove_count:
            self.beginRemoveRows(QModelIndex(), prefix, prefix + remove_count - 1)
            del values[prefix : prefix + remove_count]
            self._tracks = tuple(values)
            self.endRemoveRows()
        if insert_values:
            self.beginInsertRows(QModelIndex(), prefix, prefix + len(insert_values) - 1)
            values[prefix:prefix] = insert_values
            self._tracks = tuple(values)
            self.endInsertRows()

        self._tracks = tracks
        if tracks:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(tracks) - 1, 0)
            self.dataChanged.emit(
                top_left,
                bottom_right,
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.UserRole],
            )

    def track_at(self, index: QModelIndex) -> Track | None:
        value = self.data(index, Qt.ItemDataRole.UserRole)
        return value if isinstance(value, Track) else None


class _QueueTrackDelegate(QStyledItemDelegate):
    """Paint fixed queue rows lazily so a long real queue stays lightweight."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._current_track_id = ""
        self._current_playing = False

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme

    def set_current_track(self, track: Track | None, *, playing: bool) -> None:
        self._current_track_id = track.id if track is not None else ""
        self._current_playing = bool(playing)

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(max(1, option.rect.width()), 62)

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        track = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, Track):
            return
        painter.save()
        painter.setClipRect(option.rect)
        row = option.rect.adjusted(0, 1, 0, -1)
        # This delegate owns the entire row, including the current-track row.
        # There are no child labels layered above this paint path.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(option.rect, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        current = track.id == self._current_track_id
        if current:
            current_surface = QColor(self._theme.colors.playing_background)
            current_surface.setAlpha(220 if self._current_playing else 150)
            painter.fillRect(row, current_surface)
        elif selected:
            selected_surface = QColor(self._theme.colors.surface_selected)
            selected_surface.setAlpha(220)
            painter.fillRect(row, selected_surface)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            hover_surface = QColor(self._theme.colors.surface_hover)
            hover_surface.setAlpha(150)
            painter.fillRect(row, hover_surface)
        else:
            normal_surface = QColor(self._theme.colors.surface_primary)
            normal_surface.setAlpha(160)
            painter.fillRect(row, normal_surface)
        if current:
            painter.fillRect(QRect(row.left() + 4, row.top() + 12, 2, max(1, row.height() - 24)), QColor(
                self._theme.colors.accent if self._current_playing else IMMERSIVE_GLASS.secondary_text
            ))
        artwork_rect = QRect(row.left() + 10, row.top() + 11, 40, 40)
        artwork = cover_pixmap(track.stable_id, 40, 40)
        path = QPainterPath()
        path.addRoundedRect(artwork_rect, 7, 7)
        painter.setClipPath(path)
        painter.drawPixmap(artwork_rect, artwork)
        painter.setClipping(False)
        title, artist, _album = display_track_text(track)
        duration = format_duration(track.duration_ms)
        duration_rect = QRect(row.right() - 52, row.top(), 44, row.height())
        text_rect = QRect(artwork_rect.right() + 10, row.top() + 9, max(1, duration_rect.left() - artwork_rect.right() - 18), 22)
        artist_rect = QRect(text_rect.left(), text_rect.bottom(), text_rect.width(), 20)
        title_font = QFont(painter.font())
        title_font.setPointSize(max(8, self._theme.fonts.body))
        title_font.setWeight(QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(QColor(self._theme.colors.text_primary))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, QFontMetrics(title_font).elidedText(title, Qt.TextElideMode.ElideRight, text_rect.width()))
        artist_font = QFont(painter.font())
        artist_font.setPointSize(max(7, self._theme.fonts.caption))
        painter.setFont(artist_font)
        painter.setPen(QColor(self._theme.colors.text_secondary))
        painter.drawText(artist_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, QFontMetrics(artist_font).elidedText(artist, Qt.TextElideMode.ElideRight, artist_rect.width()))
        painter.drawText(duration_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, duration)
        if selected and option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QColor(self._theme.colors.focus_ring))
            painter.drawRoundedRect(row.adjusted(1, 1, -1, -1), 6, 6)
        painter.restore()


class QueueTrackList(QListView):
    """Vertical-only virtual list retaining a small queue count compatibility API."""

    track_selected = Signal(object)
    track_activated = Signal(object)

    def __init__(self, theme: Theme, parent: QWidget | None = None, *, interactive: bool = True) -> None:
        super().__init__(parent)
        self._theme = theme
        self._interactive = bool(interactive)
        self._current_track: Track | None = None
        self.setObjectName("immersiveQueueList")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.viewport().setAutoFillBackground(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(
            QListView.SelectionMode.SingleSelection if self._interactive else QListView.SelectionMode.NoSelection
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self._interactive else Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(self._interactive)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._interactive else Qt.CursorShape.ArrowCursor)
        self.model_view = _QueueTrackModel(self)
        self.delegate = _QueueTrackDelegate(theme, self)
        self.setModel(self.model_view)
        self.setItemDelegate(self.delegate)
        if self._interactive:
            self.clicked.connect(self._emit_selected)
            self.doubleClicked.connect(self._emit_activated)
        self.set_theme(theme)

    def count(self) -> int:
        return self.model_view.rowCount()

    def set_tracks(self, tracks: tuple[Track, ...]) -> None:
        self.model_view.set_tracks(tracks)

    @property
    def current_track(self) -> Track | None:
        return self._current_track

    def set_current_track(self, track: Track | None, *, playing: bool) -> None:
        self._current_track = track
        self.delegate.set_current_track(track, playing=playing)
        self.set_tracks((track,) if track is not None else ())
        self.viewport().update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self._interactive:
            event.ignore()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            track = self.model_view.track_at(self.currentIndex())
            if track is not None:
                self.track_activated.emit(track)
                event.accept()
                return
        super().keyPressEvent(event)

    def _emit_selected(self, index: QModelIndex) -> None:
        track = self.model_view.track_at(index)
        if track is not None:
            self.track_selected.emit(track)

    def _emit_activated(self, index: QModelIndex) -> None:
        track = self.model_view.track_at(index)
        if track is not None:
            self.track_activated.emit(track)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.delegate.set_theme(theme)
        self.setStyleSheet(
            "QListView#immersiveQueueList { background: transparent; border: 0; outline: 0; } "
            "QListView#immersiveQueueList::item { background: transparent; } "
            "QListView#immersiveQueueList::item:selected, QListView#immersiveQueueList::item:hover { background: transparent; } "
            "QAbstractScrollArea#immersiveQueueList::viewport { background: transparent; } "
            "QScrollBar:horizontal { height: 0; } "
            "QScrollBar:vertical { width: 8px; background: transparent; } "
            f"QScrollBar::handle:vertical {{ min-height: 28px; border-radius: 4px; background: {theme.colors.border_strong}; }} "
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self.viewport().setStyleSheet("background: transparent; border: 0;")
        self.viewport().update()


class QueueDrawerContent(QWidget):
    """Current and next sections rendered from the adapter without a copied queue."""

    def __init__(self, playback: PlaybackAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.playback = playback
        self._theme = theme
        self.setObjectName("queueDrawerContent")
        self.current_section = QFrame(self)
        self.current_section.setObjectName("immersiveQueueSection")
        self.current_title = QLabel("正在播放", self.current_section)
        self.current_title.setObjectName("immersiveQueueSectionTitle")
        self.current_list = QueueTrackList(theme, self.current_section, interactive=False)
        self.current_list.setFixedHeight(62)
        self.current_layout = QVBoxLayout(self.current_section)
        self.current_layout.setContentsMargins(10, 4, 10, 0)
        self.current_layout.setSpacing(0)
        self.current_layout.addWidget(self.current_title)
        self.current_layout.addWidget(self.current_list)
        self.next_section = QFrame(self)
        self.next_section.setObjectName("immersiveQueueSection")
        self.next_title = QLabel("接下来播放", self.next_section)
        self.next_title.setObjectName("immersiveQueueSectionTitle")
        self.next_list = QueueTrackList(theme, self.next_section)
        self.list_widget = self.next_list
        self.next_layout = QVBoxLayout(self.next_section)
        self.next_layout.setContentsMargins(10, 8, 10, 10)
        self.next_layout.setSpacing(3)
        self.next_layout.addWidget(self.next_title)
        self.next_layout.addWidget(self.next_list, 1)
        self.empty_label = QLabel("播放队列为空", self)
        self.empty_label.setObjectName("immersiveQueueEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_rows: list[Track] = []
        self.track_rows: list[object] = []
        self.selected_track: Track | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.current_section)
        layout.addWidget(self.next_section, 1)
        layout.addWidget(self.empty_label, 1)
        playback.track_changed.connect(lambda _track: self.refresh())
        playback.queue_changed.connect(lambda _queue: self.refresh())
        playback.playing_changed.connect(lambda _playing: self.refresh())
        self.next_list.track_selected.connect(self._select_track)
        self.next_list.track_activated.connect(self._play_selected_track)
        self.set_theme(theme)

    def _select_track(self, track: Track) -> None:
        self.selected_track = track

    def _play_selected_track(self, track: Track) -> None:
        self.selected_track = track
        self.playback.play_track(track.id)

    def refresh(self) -> None:
        tracks = tuple(self.playback.queue_tracks)
        current_track = self.playback.state.current_track
        current_index = self.playback.state.current_index
        if (
            not 0 <= current_index < len(tracks)
            or current_track is None
            or tracks[current_index].id != current_track.id
        ):
            current_index = next(
                (index for index, track in enumerate(tracks) if current_track and track.id == current_track.id),
                -1,
            )
        current = tracks[current_index] if current_index >= 0 else None
        next_tracks = tracks[current_index + 1 :] if current_index >= 0 else tracks
        self.current_list.set_current_track(current, playing=self.playback.state.is_playing)
        self.next_rows = list(next_tracks)
        self.track_rows = ([current] if current is not None else []) + list(next_tracks)
        self.next_list.set_tracks(next_tracks)
        if self.selected_track is not None:
            selected_row = next(
                (row for row, track in enumerate(next_tracks) if track.id == self.selected_track.id),
                -1,
            )
            if selected_row >= 0:
                self.next_list.setCurrentIndex(self.next_list.model_view.index(selected_row, 0))
            else:
                self.next_list.clearSelection()
                self.selected_track = None
        self.current_section.setVisible(current is not None)
        self.next_section.setVisible(bool(next_tracks))
        self.empty_label.setVisible(not tracks)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for section in (self.current_section, self.next_section):
            section.setStyleSheet("QFrame#immersiveQueueSection { background: transparent; border: 0; }")
        for label in (self.current_title, self.next_title):
            label.setStyleSheet(
                f"font-size: {theme.fonts.caption}px; font-weight: 600; color: {IMMERSIVE_GLASS.secondary_text};"
            )
        self.empty_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; color: {IMMERSIVE_GLASS.secondary_text};"
        )
        self.next_list.set_theme(theme)
        self.current_list.set_theme(theme)


class QueueFloatingPanel(ImmersiveFloatingPanel):
    """Stable floating Queue panel backed by the shared playback adapter."""

    def __init__(self, playback: PlaybackAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__("播放队列", theme, parent)
        self.playback = playback
        self.content = QueueDrawerContent(playback, theme, self.content_host)
        self.set_content(self.content)
        self.list_widget = self.content.list_widget
        self.scroll_area = self.list_widget
        self.empty_label = self.content.empty_label
        self.current_section = self.content.current_section
        self.next_section = self.content.next_section
        self.refresh()
        playback.track_changed.connect(lambda _track: self._refresh_count())
        playback.queue_changed.connect(lambda _queue: self._refresh_count())

    @property
    def current_track(self) -> Track | None:
        return self.content.current_list.current_track

    @property
    def next_rows(self) -> list[Track]:
        return self.content.next_rows

    @property
    def track_rows(self) -> list[object]:
        return self.content.track_rows

    def refresh(self) -> None:
        self.content.refresh()
        self._refresh_count()

    def _refresh_count(self) -> None:
        self.set_count(f"{len(self.playback.queue_tracks)} 首" if self.playback.queue_tracks else "")

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if hasattr(self, "content"):
            self.content.set_theme(theme)


ImmersiveQueuePanel = QueueFloatingPanel
QueueDrawer = QueueFloatingPanel
