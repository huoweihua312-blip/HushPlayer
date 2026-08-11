"""QTableView wiring for UI V2's fast song-library surface."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QFont, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableView,
    QWidget,
)

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import TrackColumn, TrackTableModel
from app.ui_v2.theme.icons import paint_icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.quiet_context_menu import apply_menu_theme
from app.ui_v2.widgets.responsive_columns import ResponsiveColumnPolicy
from app.ui_v2.widgets.track_delegate import TrackDelegate


class TrackHeaderView(QHeaderView):
    """Theme-aware headers with a lightweight V2 sort indicator."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._theme = theme
        self._hovered_section = -1
        self.setMouseTracking(True)
        self.setHighlightSections(False)

    @property
    def hovered_section(self) -> int:
        return self._hovered_section

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.viewport().update()

    def is_sorted_section(self, logical_index: int) -> bool:
        """Return whether a visible data header should show a sort state."""

        return (
            int(logical_index) == self.sortIndicatorSection()
            and int(logical_index) != int(TrackColumn.MORE)
        )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._set_hovered_section(self.logicalIndexAt(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hovered_section(-1)
        super().leaveEvent(event)

    def paintSection(self, painter: QPainter, rect, logical_index: int) -> None:  # noqa: N802
        if not rect.isValid():
            return
        colors = self._theme.colors
        is_sorted = self.is_sorted_section(logical_index)
        is_hovered = logical_index == self._hovered_section
        background = (
            colors.hover_background
            if is_hovered
            else colors.elevated_background
            if is_sorted
            else colors.content_background
        )
        painter.save()
        painter.fillRect(rect, QColor(background))
        painter.setPen(QPen(QColor(colors.divider), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if is_sorted:
            accent = QColor(colors.accent)
            accent.setAlpha(170)
            painter.fillRect(rect.left() + 8, rect.bottom() - 1, max(0, rect.width() - 16), 2, accent)
        if logical_index == int(TrackColumn.FAVORITE):
            icon_rect = QRectF(rect.center().x() - 8, rect.center().y() - 8, 16, 16)
            paint_icon(painter, "favorite", icon_rect, self._theme, "normal")
            painter.restore()
            return
        if logical_index == int(TrackColumn.MORE):
            painter.restore()
            return
        label = self.model().headerData(
            logical_index,
            Qt.Orientation.Horizontal,
            Qt.ItemDataRole.DisplayRole,
        )
        text_rect = QRectF(rect.adjusted(8, 0, -8, 0))
        if is_sorted:
            icon_rect = QRectF(rect.right() - 22, rect.center().y() - 8, 16, 16)
            icon_name = (
                "sort_ascending"
                if self.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
                else "sort_descending"
            )
            paint_icon(painter, icon_name, icon_rect, self._theme, "selected")
            text_rect.setRight(icon_rect.left() - 4)
        font = QFont(painter.font())
        font.setWeight(QFont.Weight.DemiBold if is_sorted else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(colors.accent if is_sorted else colors.subtle_text))
        text = painter.fontMetrics().elidedText(
            str(label or ""), Qt.TextElideMode.ElideRight, max(0, int(text_rect.width()))
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def _set_hovered_section(self, section: int) -> None:
        if section == self._hovered_section:
            return
        previous = self._hovered_section
        self._hovered_section = section
        for changed in (previous, section):
            if changed >= 0:
                self.updateSection(changed)


class TrackTable(QTableView):
    """View/controller boundary for selection, playback, favorites, and menus."""

    play_requested = Signal(str)
    favorite_toggled = Signal(str, bool)
    mock_action_requested = Signal(str, str)
    artist_requested = Signal(str)

    def __init__(self, adapter: LibraryAdapter, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self.model = TrackTableModel(adapter.tracks(), self)
        meta_provider = getattr(adapter, "row_metadata", None)
        if callable(meta_provider):
            self.model.set_meta_provider(meta_provider)
        self.delegate = TrackDelegate(theme, self)
        self._theme = theme
        self._hovered_row = -1
        self._column_profile = "narrow"
        self._responsive_reference_width: int | None = None
        self._visible_row_limit: int | None = None
        self._playlist_remove_callback: Callable[[str], None] | None = None
        self._artist_navigation_enabled = False
        self._playback_enabled = True
        self.setObjectName("trackTable")
        self.setAccessibleName("歌曲列表")
        self.setAccessibleDescription("使用方向键选择歌曲，按 Enter 播放，按空格不改变播放状态")
        self.header = TrackHeaderView(theme, self)
        self.setHorizontalHeader(self.header)
        self.setModel(self.model)
        self.setItemDelegate(self.delegate)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.doubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)
        header = self.header
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.setSortIndicator(int(adapter.sort_column), adapter.sort_order)
        header.sectionClicked.connect(self._on_header_clicked)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(48)
        self.verticalHeader().setMinimumSectionSize(48)
        self.header.setFixedHeight(36)
        self.adapter.tracks_reset.connect(self.model.set_tracks)
        self.adapter.track_updated.connect(self.model.update_track)
        self.adapter.playing_track_changed.connect(self.model.set_playing_track)
        self.model.modelReset.connect(self._apply_visible_row_limit)
        self._apply_column_widths()
        self._apply_scrollbar_style()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.delegate.set_theme(theme)
        self.header.set_theme(theme)
        self._apply_scrollbar_style()
        self.viewport().update()

    def _apply_scrollbar_style(self) -> None:
        c = self._theme.colors
        self.setStyleSheet(
            f"QTableView#trackTable QScrollBar:vertical {{ width: 6px; background: transparent; "
            f"margin: 2px 0; border: 0; }}"
            f"QTableView#trackTable QScrollBar::handle:vertical {{ min-height: 24px; border-radius: 3px; "
            f"background: {c.border_strong}; }}"
            f"QTableView#trackTable QScrollBar::handle:vertical:hover {{ background: {c.secondary_text}; }}"
            f"QTableView#trackTable QScrollBar::add-line:vertical, QTableView#trackTable QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QTableView#trackTable QScrollBar::add-page:vertical, QTableView#trackTable QScrollBar::sub-page:vertical {{ background: transparent; }}"
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_column_widths()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and index.column() == int(TrackColumn.FAVORITE)
        ):
            track = self.model.track_at(index.row())
            if (
                track is not None
                and self._can_change_favorite(track)
                and self.adapter.collection.can_mutate_favorites
            ):
                next_value = not track.is_favorite
                self.adapter.toggle_favorite(track.id)
                self.favorite_toggled.emit(track.id, next_value)
                event.accept()
                return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and index.column() == int(TrackColumn.MORE)
        ):
            menu = self.build_context_menu(index)
            if menu is not None:
                menu.exec(self.viewport().mapToGlobal(event.position().toPoint()))
                menu.deleteLater()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        self._set_hovered_row(index.row() if index.isValid() else -1)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hovered_row(-1)
        super().leaveEvent(event)

    @property
    def column_profile(self) -> str:
        return self._column_profile

    def set_responsive_reference_width(self, width: int | None) -> None:
        """Use a shell width for profile choice while sizing against the viewport."""
        reference = max(1, int(width)) if width is not None else None
        if reference == self._responsive_reference_width:
            return
        self._responsive_reference_width = reference
        self._apply_column_widths()

    def set_visible_row_limit(self, limit: int | None) -> None:
        """Limit displayed rows without changing the shared model or adapter."""

        normalized = None if limit is None else max(0, int(limit))
        if normalized == self._visible_row_limit:
            self._apply_visible_row_limit()
            return
        self._visible_row_limit = normalized
        self._apply_visible_row_limit()

    @property
    def visible_row_limit(self) -> int | None:
        return self._visible_row_limit

    def _apply_visible_row_limit(self) -> None:
        limit = self._visible_row_limit
        for row in range(self.model.rowCount()):
            self.setRowHidden(row, limit is not None and row >= limit)

    def is_row_hovered(self, row: int) -> bool:
        return row >= 0 and row == self._hovered_row

    def set_playlist_context(self, remove_callback: Callable[[str], None] | None) -> None:
        self._playlist_remove_callback = remove_callback

    def set_artist_navigation_enabled(self, enabled: bool) -> None:
        """Opt in to the non-visual Artist route action for detail surfaces."""

        self._artist_navigation_enabled = bool(enabled)

    def set_playback_enabled(self, enabled: bool) -> None:
        """Gate play actions when a read-only source has no real playback yet."""

        self._playback_enabled = bool(enabled)

    def set_playback_state(self, track_id: str, is_playing: bool) -> None:
        """Forward current paused/playing state without replacing the model."""

        self.model.set_playback_state(track_id, is_playing)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        index = self.indexAt(event.pos())
        menu = self.build_context_menu(index)
        if menu is not None:
            menu.exec(event.globalPos())
            menu.deleteLater()

    def build_context_menu(self, index: QModelIndex) -> QMenu | None:
        track = self.model.track_at(index.row()) if index.isValid() else None
        if track is None:
            return None
        menu = apply_menu_theme(QMenu(self), self._theme)
        play_action = menu.addAction("播放")
        play_action.setEnabled(
            (not track.is_missing or track.is_online)
            and self._playback_enabled
        )
        if not self._playback_enabled:
            play_action.setToolTip("真实模式尚未接入播放")
        play_action.triggered.connect(lambda: self._request_play(track))
        if self.adapter.collection.can_mutate_favorites:
            favorite_action = menu.addAction("取消收藏" if track.is_favorite else "添加到我喜欢")
            favorite_action.setEnabled(self._can_change_favorite(track))
            favorite_action.triggered.connect(lambda: self._toggle_from_menu(track))
            playlist_action = menu.addAction("添加到歌单")
            playlist_action.triggered.connect(
                lambda: self.mock_action_requested.emit("add_to_playlist", track.id)
            )
        if self._playlist_remove_callback is not None:
            remove_action = menu.addAction("从当前歌单移除")
            remove_action.triggered.connect(
                lambda: self._playlist_remove_callback(track.id)
            )
        info_action = menu.addAction("查看歌曲信息")
        info_action.triggered.connect(lambda: self.mock_action_requested.emit("show_info", track.id))
        if self._artist_navigation_enabled and track.artist.strip():
            artist_action = menu.addAction("查看艺人")
            artist_action.triggered.connect(lambda: self.artist_requested.emit(track.artist))
        return menu

    @staticmethod
    def _can_change_favorite(track: Track) -> bool:
        """Allow removing stale favorites while keeping invalid additions blocked."""

        return not track.is_missing or track.is_favorite

    def _show_context_menu(self, position) -> None:
        index = self.indexAt(position)
        menu = self.build_context_menu(index)
        if menu is None:
            return
        menu.exec(self.viewport().mapToGlobal(position))
        menu.deleteLater()

    def _on_double_clicked(self, index: QModelIndex) -> None:
        track = self.model.track_at(index.row())
        if (
            track is not None
            and (not track.is_missing or track.is_online)
        ):
            self._request_play(track)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Keep keyboard playback explicit: Enter plays, Space never does."""

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            index = self.currentIndex()
            track = self.model.track_at(index.row()) if index.isValid() else None
            if track is not None:
                self._request_play(track)
                event.accept()
                return
        super().keyPressEvent(event)

    def _request_play(self, track: Track) -> None:
        if not self._playback_enabled:
            return
        self.adapter.request_play(track.id)
        self.play_requested.emit(track.id)

    def _toggle_from_menu(self, track: Track) -> None:
        if self.adapter.collection.read_only:
            return
        self.adapter.toggle_favorite(track.id)
        self.favorite_toggled.emit(track.id, not track.is_favorite)

    def _on_header_clicked(self, section: int) -> None:
        if section in {int(TrackColumn.STATUS), int(TrackColumn.MORE)}:
            return
        order = self.horizontalHeader().sortIndicatorOrder()
        if self.adapter.sort_column == TrackColumn(section):
            order = (
                Qt.SortOrder.DescendingOrder
                if order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        self.adapter.set_sort(section, order)
        self.horizontalHeader().setSortIndicator(section, order)

    def _apply_column_widths(self) -> None:
        viewport_width = max(1, self.viewport().width())
        width = max(1, viewport_width - 16)
        profile_width = self._responsive_reference_width or viewport_width
        self._column_profile = ResponsiveColumnPolicy.profile_for_width(profile_width).name
        self.setColumnHidden(
            int(TrackColumn.FAVORITE),
            self._column_profile == "narrow" or not self.adapter.collection.can_mutate_favorites,
        )
        self.setColumnHidden(int(TrackColumn.ALBUM), self._column_profile == "narrow")
        self.setColumnHidden(int(TrackColumn.SOURCE), self._column_profile != "wide")
        widths = ResponsiveColumnPolicy.widths(self._column_profile, width)
        header = self.header
        for column, column_width in widths.items():
            header.setSectionResizeMode(int(column), QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(int(column), column_width)

    @staticmethod
    def _narrow_column_widths(width: int) -> dict[TrackColumn, int]:
        status, duration, more = 40, 68, 42
        remaining = max(320, width - status - duration - more)
        artist = min(150, max(120, int(remaining * 0.29)))
        return {
            TrackColumn.STATUS: status,
            TrackColumn.TITLE: max(150, remaining - artist),
            TrackColumn.ARTIST: artist,
            TrackColumn.ALBUM: 0,
            TrackColumn.DURATION: duration,
            TrackColumn.FAVORITE: 0,
            TrackColumn.SOURCE: 0,
            TrackColumn.MORE: more,
        }

    @staticmethod
    def _standard_column_widths(width: int) -> dict[TrackColumn, int]:
        status, favorite, duration, artist, album, more = 40, 40, 74, 140, 130, 42
        return {
            TrackColumn.STATUS: status,
            TrackColumn.FAVORITE: favorite,
            TrackColumn.TITLE: max(160, width - status - favorite - duration - artist - album - more),
            TrackColumn.ARTIST: artist,
            TrackColumn.ALBUM: album,
            TrackColumn.DURATION: duration,
            TrackColumn.SOURCE: 0,
            TrackColumn.MORE: more,
        }

    @staticmethod
    def _wide_column_widths(width: int) -> dict[TrackColumn, int]:
        status, favorite, duration, artist, album, source, more = 40, 40, 80, 200, 240, 140, 44
        return {
            TrackColumn.STATUS: status,
            TrackColumn.FAVORITE: favorite,
            TrackColumn.TITLE: max(220, width - status - favorite - duration - artist - album - source - more),
            TrackColumn.ARTIST: artist,
            TrackColumn.ALBUM: album,
            TrackColumn.DURATION: duration,
            TrackColumn.SOURCE: source,
            TrackColumn.MORE: more,
        }

    def _set_hovered_row(self, row: int) -> None:
        if row == self._hovered_row:
            return
        previous = self._hovered_row
        self._hovered_row = row
        for changed_row in (previous, row):
            self._update_row(changed_row)

    def _update_row(self, row: int) -> None:
        if not (0 <= row < self.model.rowCount()):
            return
        left = self.visualRect(self.model.index(row, 0))
        visible_columns = [
            column
            for column in range(self.model.columnCount())
            if not self.isColumnHidden(column)
        ]
        if not visible_columns:
            return
        right = self.visualRect(self.model.index(row, visible_columns[-1]))
        self.viewport().update(left.united(right))
