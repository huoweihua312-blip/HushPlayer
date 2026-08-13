"""Virtualized online-result table with shared V2 row-state language."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QWidget,
)

from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.online_track_model import (
    ONLINE_PLAYING_ROLE,
    ONLINE_TRACK_ROLE,
    OnlineColumn,
    OnlineTrackModel,
)
from app.ui_v2.theme.icons import icon, paint_icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.track_delegate import RowVisualState
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from app.ui_v2.widgets.track_display import present_track_identity_values


class OnlineResultDelegate(QStyledItemDelegate):
    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme

    def sizeHint(self, option, index):  # noqa: N802
        return super().sizeHint(option, index).expandedTo(option.fontMetrics.size(0, 52))

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        track = index.data(ONLINE_TRACK_ROLE)
        if not isinstance(track, OnlineTrack):
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        table = self.parent()
        hovered = bool(getattr(table, "is_row_hovered", lambda _row: False)(index.row()))
        playing = bool(index.data(ONLINE_PLAYING_ROLE))
        state = self._state(track, selected, hovered, playing)
        colors = self._theme.colors
        identity = present_track_identity_values(
            track.title,
            track.artist,
            track.album,
            is_online=True,
            availability=track.availability,
            playback_detail=track.availability_detail,
        )
        painter.save()
        rect = QRectF(option.rect)
        painter.fillRect(rect, self._background(state))
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        column = OnlineColumn(index.column())
        content = rect.adjusted(10, 0, -10, 0)
        disabled = state == RowVisualState.DISABLED
        text_color = QColor(colors.disabled_text if disabled else colors.primary_text)
        secondary = QColor(colors.disabled_text if disabled else colors.secondary_text)
        icon_state = "disabled" if disabled else "selected" if playing else "hover" if hovered else "normal"
        if playing and column == OnlineColumn.FAVORITE:
            painter.fillRect(QRectF(rect.left(), rect.top() + 6, 3, rect.height() - 12), QColor(colors.accent))
        if column == OnlineColumn.FAVORITE:
            paint_icon(
                painter,
                "favorite_filled" if track.is_favorite else "favorite",
                QRectF(content.center().x() - 9, content.center().y() - 9, 18, 18),
                self._theme,
                "selected" if track.is_favorite else icon_state,
            )
        elif column == OnlineColumn.TITLE:
            left = content.left()
            artwork = artwork_pixmap_for_track(track.as_track(), 32, 32)
            painter.drawPixmap(
                int(left),
                int(content.center().y() - 16),
                artwork,
            )
            left += 42
            if playing:
                paint_icon(painter, "playing", QRectF(left, content.center().y() - 8, 16, 16), self._theme, "selected")
                left += 22
            title_rect = QRectF(left, content.top(), content.right() - left, content.height())
            if track.explicit:
                title_rect.setRight(max(title_rect.left(), title_rect.right() - 22))
            self._draw_text(painter, title_rect, identity.title, QColor(colors.accent) if playing else text_color, bold=playing)
            if track.explicit and content.width() > 72:
                badge = QRectF(content.right() - 18, content.center().y() - 8, 16, 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colors.border_strong))
                painter.drawRoundedRect(badge, 3, 3)
                painter.setPen(QColor(colors.primary_text))
                painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "E")
        elif column == OnlineColumn.SOURCE:
            paint_icon(painter, "online", QRectF(content.left(), content.center().y() - 8, 16, 16), self._theme, icon_state)
            self._draw_text(painter, content.adjusted(22, 0, 0, 0), track.source_name, secondary)
        elif column == OnlineColumn.STATUS:
            if identity.availability.is_confirmed_error:
                color = colors.disabled_text
            elif identity.availability.is_resolving:
                color = colors.subtle_text
            else:
                color = colors.success
            status_text = (
                identity.availability.label
                if identity.availability.is_visible
                else "可用"
                if identity.availability.is_playable
                else "未解析"
            )
            self._draw_text(painter, content, status_text, QColor(color))
        elif column == OnlineColumn.DURATION:
            self._draw_text(painter, content, index.data(Qt.ItemDataRole.DisplayRole) or "", secondary, align=Qt.AlignmentFlag.AlignRight)
        else:
            self._draw_text(painter, content, index.data(Qt.ItemDataRole.DisplayRole) or "", secondary)
        painter.restore()

    def _state(self, track: OnlineTrack, selected: bool, hovered: bool, playing: bool) -> RowVisualState:
        identity = present_track_identity_values(
            track.title,
            track.artist,
            track.album,
            is_online=True,
            availability=track.availability,
            playback_detail=track.availability_detail,
        )
        if identity.availability.is_confirmed_error and not identity.availability.is_retryable:
            return RowVisualState.DISABLED
        if selected and playing:
            return RowVisualState.SELECTED_PLAYING
        if selected:
            return RowVisualState.SELECTED
        if playing:
            return RowVisualState.PLAYING
        if hovered:
            return RowVisualState.HOVER
        return RowVisualState.NORMAL

    def _background(self, state: RowVisualState) -> QColor:
        values = {
            RowVisualState.NORMAL: self._theme.colors.surface_primary,
            RowVisualState.HOVER: self._theme.colors.hover_background,
            RowVisualState.SELECTED: self._theme.colors.selected_background,
            RowVisualState.PLAYING: self._theme.colors.playing_background,
            RowVisualState.SELECTED_PLAYING: self._theme.colors.selected_background,
            RowVisualState.DISABLED: self._theme.colors.surface_primary,
        }
        return QColor(values[state])

    @staticmethod
    def _draw_text(painter, rect, text, color, *, bold: bool = False, align=Qt.AlignmentFlag.AlignLeft) -> None:
        font = QFont(painter.font())
        font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(color)
        value = painter.fontMetrics().elidedText(str(text), Qt.TextElideMode.ElideRight, max(0, int(rect.width())))
        painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, value)


class OnlineResultTable(QTableView):
    source_requested = Signal()

    def __init__(
        self,
        adapter: OnlineAdapter,
        playlists: PlaylistAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self.playlists = playlists
        self.model = OnlineTrackModel((), self)
        self.delegate = OnlineResultDelegate(theme, self)
        self._theme = theme
        self._hovered_row = -1
        self._responsive_width: int | None = None
        self._all_tracks = adapter.results()
        self._source_filter = ""
        self._sort_mode = "relevance"
        self.setObjectName("onlineResultTable")
        self.setModel(self.model)
        self.setItemDelegate(self.delegate)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(52)
        self.horizontalHeader().setStretchLastSection(False)
        self.doubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)
        adapter.search_results_changed.connect(self._set_all_tracks)
        adapter.result_updated.connect(self._update_track)
        adapter.playing_track_changed.connect(self.model.set_playing_track)
        self._refresh_visible_tracks()
        self._apply_column_widths()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.delegate.set_theme(theme)
        colors = theme.colors
        metrics = theme.metrics
        self.setStyleSheet(
            f"QTableView#onlineResultTable {{ background: {colors.surface_primary}; border: 0; outline: 0; }}"
            f"QTableView#onlineResultTable QHeaderView {{ background: {colors.surface_primary}; border: 0; }}"
            f"QTableView#onlineResultTable QHeaderView::section {{ height: 36px; padding: 0 {metrics.spacing_sm}px; "
            f"background: {colors.surface_primary}; color: {colors.text_tertiary}; border: 0; "
            f"border-bottom: 1px solid {colors.divider}; font-size: {theme.fonts.card_meta}px; font-weight: 600; }}"
            f"QTableView#onlineResultTable QScrollBar:vertical {{ width: 6px; margin: 4px 2px; background: transparent; border: 0; }}"
            f"QTableView#onlineResultTable QScrollBar::handle:vertical {{ min-height: 28px; border-radius: 3px; background: {colors.border_strong}; }}"
            f"QTableView#onlineResultTable QScrollBar::handle:vertical:hover {{ background: {colors.text_tertiary}; }}"
            f"QTableView#onlineResultTable QScrollBar::add-line:vertical, QTableView#onlineResultTable QScrollBar::sub-line:vertical {{ height: 0; }}"
        )
        self.viewport().update()

    def set_responsive_reference_width(self, width: int) -> None:
        normalized = max(1, int(width))
        if normalized != self._responsive_width:
            self._responsive_width = normalized
            self._apply_column_widths()

    def set_source_filter(self, source_id: str) -> None:
        normalized = str(source_id or "")
        if normalized == self._source_filter:
            return
        self._source_filter = normalized
        self._refresh_visible_tracks()

    def set_sort_mode(self, mode: str) -> None:
        normalized = mode if mode in {"relevance", "title", "duration"} else "relevance"
        if normalized == self._sort_mode:
            return
        self._sort_mode = normalized
        self._refresh_visible_tracks()

    def is_row_hovered(self, row: int) -> bool:
        return row == self._hovered_row and row >= 0

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_column_widths()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        self._set_hovered_row(index.row() if index.isValid() else -1)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hovered_row(-1)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid() and index.column() == int(OnlineColumn.FAVORITE):
            if not self.adapter.collection.read_only or self.adapter.can_mutate_remote:
                self.adapter.toggle_favorite(self.model.track_at(index.row()).id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def build_context_menu(self, index: QModelIndex) -> QMenu | None:
        track = self.model.track_at(index.row()) if index.isValid() else None
        if track is None:
            return None
        menu = QMenu(self)
        formal = self.adapter.is_formal
        identity = present_track_identity_values(
            track.title,
            track.artist,
            track.album,
            is_online=True,
            availability=track.availability,
            playback_detail=track.availability_detail,
        )
        play = menu.addAction(icon("play", self._theme), "播放")
        play.setEnabled(
            formal
            or (
                (
                    not identity.availability.is_confirmed_error
                    or identity.availability.is_retryable
                )
                and not self.adapter.collection.read_only
            )
        )
        play.triggered.connect(lambda: self.adapter.request_play(track.id))
        if not self.adapter.collection.read_only or self.adapter.can_mutate_remote:
            favorite = menu.addAction(icon("favorite", self._theme), "取消收藏" if track.is_favorite else "收藏")
            favorite.triggered.connect(lambda: self.adapter.toggle_favorite(track.id))
            add_menu = menu.addMenu(icon("add", self._theme), "添加到歌单")
            for playlist in self.playlists.playlists():
                action = add_menu.addAction(playlist.name)
                action.triggered.connect(
                    lambda checked=False, playlist_id=playlist.id: self.adapter.request_add_to_playlist(track.id, playlist_id)
                )
            if not formal:
                download = menu.addAction(icon("local", self._theme), "下载")
                source = next((item for item in self.adapter.sources() if item.id == track.source_id), None)
                download.setEnabled(bool(source and source.supports_download and identity.availability.is_playable))
                download.triggered.connect(lambda: self.adapter.request_download(track.id))
        info = menu.addAction(icon("library", self._theme), "查看歌曲信息")
        info.setEnabled(True)
        info.triggered.connect(lambda: self.adapter.request_metadata(track.id))
        source_action = menu.addAction(icon("online", self._theme), "查看来源")
        source_action.triggered.connect(lambda: self.source_requested.emit())
        return menu

    def _on_double_clicked(self, index: QModelIndex) -> None:
        track = self.model.track_at(index.row())
        if track is not None and (self.adapter.is_formal or not self.adapter.collection.read_only):
            self.adapter.request_play(track.id)

    def _show_context_menu(self, position) -> None:
        menu = self.build_context_menu(self.indexAt(position))
        if menu is None:
            return
        menu.exec(self.viewport().mapToGlobal(position))
        menu.deleteLater()

    def _set_all_tracks(self, tracks) -> None:
        self._all_tracks = tuple(tracks)
        self._refresh_visible_tracks()

    def _update_track(self, updated: OnlineTrack) -> None:
        values = list(self._all_tracks)
        for index, track in enumerate(values):
            if track.id == updated.id:
                values[index] = updated
                self._all_tracks = tuple(values)
                if not self._source_filter or updated.source_id == self._source_filter:
                    self.model.update_track(updated)
                return

    def _refresh_visible_tracks(self) -> None:
        tracks = [
            track
            for track in self._all_tracks
            if not self._source_filter or track.source_id == self._source_filter
        ]
        if self._sort_mode == "title":
            tracks.sort(key=lambda track: (track.title.casefold(), track.artist.casefold(), track.result_rank))
        elif self._sort_mode == "duration":
            tracks.sort(
                key=lambda track: (
                    track.duration_ms is None,
                    track.duration_ms if track.duration_ms is not None else 0,
                    track.result_rank,
                )
            )
        else:
            tracks.sort(key=self._relevance_key)
        self.model.set_tracks(tracks)
        self.model.set_playing_track(self.adapter.playing_track_id)

    def _relevance_key(self, track: OnlineTrack) -> tuple[int, int]:
        """Prefer metadata matching the query while keeping ties stable."""
        query = " ".join(str(self.adapter.query or "").casefold().split())
        if not query:
            return (0, track.result_rank)
        terms = tuple(dict.fromkeys(query.split()))
        title = " ".join(str(track.title or "").casefold().split())
        artist = " ".join(str(track.artist or "").casefold().split())
        album = " ".join(str(track.album or "").casefold().split())

        def field_score(value: str, weight: int) -> int:
            if not value:
                return 0
            if value == query:
                return weight
            if query in value:
                return weight - 10
            matched = sum(1 for term in terms if term and term in value)
            if matched == len(terms) and matched:
                return weight - 20
            if matched:
                return weight - 40 + matched
            return 0

        score = max(
            field_score(title, 100),
            field_score(artist, 70),
            field_score(album, 55),
        )
        return (-score, track.result_rank)

    def _apply_column_widths(self) -> None:
        width = max(1, self.viewport().width() - 12)
        profile = self._responsive_width or width
        narrow = profile < 950
        hidden = {OnlineColumn.ALBUM, OnlineColumn.QUALITY, OnlineColumn.STATUS} if narrow else set()
        for column in OnlineColumn:
            self.setColumnHidden(int(column), column in hidden)
        if narrow:
            values = {
                OnlineColumn.FAVORITE: 38,
                OnlineColumn.TITLE: max(160, width - 38 - 126 - 68 - 52),
                OnlineColumn.ARTIST: 126,
                OnlineColumn.DURATION: 68,
                OnlineColumn.SOURCE: 52,
            }
        else:
            values = {
                OnlineColumn.FAVORITE: 40,
                OnlineColumn.TITLE: max(160, width - 40 - 160 - 190 - 78 - 118 - 72 - 88),
                OnlineColumn.ARTIST: 160,
                OnlineColumn.ALBUM: 190,
                OnlineColumn.DURATION: 78,
                OnlineColumn.SOURCE: 118,
                OnlineColumn.QUALITY: 72,
                OnlineColumn.STATUS: 88,
            }
        header = self.horizontalHeader()
        for column, value in values.items():
            header.setSectionResizeMode(int(column), QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(int(column), value)

    def _set_hovered_row(self, row: int) -> None:
        if row == self._hovered_row:
            return
        previous = self._hovered_row
        self._hovered_row = row
        for changed in (previous, row):
            if 0 <= changed < self.model.rowCount():
                self.viewport().update(self.visualRect(self.model.index(changed, 0)).united(self.visualRect(self.model.index(changed, self.model.columnCount() - 1))))
