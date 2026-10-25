"""The song table used across the whole application.

A ``QAbstractTableModel`` keeps the ordering logic in one place and a custom
delegate paints the row so it looks like a native, well-behaved list instead of
a grid of boxes.  The header is drawn separately to keep full control over
hover and sort indicators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QStyleFactory,
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...core.icons import draw as draw_icon
from ...core.theme import Metrics, draw_text, mix, qcolor, rgba, theme
from ...model.track import Track, format_duration
from ..context import ctx
from .hover_tip import display_source, hide_tip, show_tip, tip_text
from .common import elide

COLUMN_INDEX = "index"
COLUMN_TITLE = "title"
COLUMN_ARTIST = "artist"
COLUMN_ALBUM = "album"
COLUMN_DURATION = "duration"
COLUMN_FAVORITE = "favorite"

TITLE_ROLE = int(Qt.UserRole) + 1


@dataclass
class Column:
    key: str
    title: str
    width: int = 0  # 0 means stretch
    align: Qt.AlignmentFlag = Qt.AlignLeft | Qt.AlignVCenter
    sortable: bool = True


DEFAULT_COLUMNS: tuple[Column, ...] = (
    Column(COLUMN_INDEX, "#", 46, Qt.AlignHCenter | Qt.AlignVCenter, sortable=False),
    Column(COLUMN_TITLE, "标题", 0),
    Column(COLUMN_ARTIST, "歌手", 190),
    Column(COLUMN_ALBUM, "专辑", 190),
    Column(COLUMN_DURATION, "时长", 70, Qt.AlignRight | Qt.AlignVCenter),
    Column(COLUMN_FAVORITE, "", 44, Qt.AlignHCenter | Qt.AlignVCenter, sortable=False),
)


class TrackTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[Track] = []
        self._favorites: set[str] = set()
        self._current_id = ""
        self._playing = False
        self._sort_key = ""
        self._sort_asc = True
        self.compact = False

    # ------------------------------------------------------------ qt basics
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(DEFAULT_COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        track = self._items[index.row()]
        column = DEFAULT_COLUMNS[index.column()].key
        if role == TITLE_ROLE:
            return track
        if role == Qt.DisplayRole:
            if column == COLUMN_TITLE:
                return track.title
            if column == COLUMN_ARTIST:
                return track.artist
            if column == COLUMN_ALBUM:
                return track.album
            if column == COLUMN_DURATION:
                return format_duration(track.duration_ms)
            if column == COLUMN_INDEX:
                return str(index.row() + 1)
            return ""
        if role == Qt.ToolTipRole:
            return tip_text(track)
        if role == Qt.AccessibleTextRole:
            return f"{track.title} - {track.artist}"
        return None

    # ------------------------------------------------------------- accessors
    @property
    def tracks(self) -> list[Track]:
        return self._items

    @property
    def current_id(self) -> str:
        return self._current_id

    @property
    def playing(self) -> bool:
        return self._playing

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def row_of(self, track_id: str) -> int:
        for row, track in enumerate(self._items):
            if track.id == track_id:
                return row
        return -1

    def is_favorite(self, track_id: str) -> bool:
        return track_id in self._favorites

    # ------------------------------------------------------------- mutation
    def set_tracks(self, tracks: Sequence[Track], *, keep_sort: bool = True) -> None:
        sort_key, sort_asc = self._sort_key, self._sort_asc
        self.beginResetModel()
        self._items = list(tracks)
        self.endResetModel()
        if keep_sort and sort_key:
            self.sort(sort_key, sort_asc, emit=False)

    def append(self, tracks: Sequence[Track]) -> None:
        if not tracks:
            return
        self.beginInsertRows(QModelIndex(), len(self._items), len(self._items) + len(tracks) - 1)
        self._items.extend(tracks)
        self.endInsertRows()

    def remove_rows(self, rows: Iterable[int]) -> None:
        targets = sorted({int(row) for row in rows}, reverse=True)
        for row in targets:
            if 0 <= row < len(self._items):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._items[row]
                self.endRemoveRows()

    def remove_ids(self, ids: Iterable[str]) -> None:
        wanted = set(ids)
        rows = [row for row, track in enumerate(self._items) if track.id in wanted]
        self.remove_rows(rows)

    def replace_track(self, track: Track) -> None:
        row = self.row_of(track.id)
        if row < 0:
            return
        self._items[row] = track
        left = self.index(row, 0)
        right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(left, right)

    def set_favorites(self, ids: Iterable[str]) -> None:
        self._favorites = set(ids)
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._items) - 1, self.columnCount() - 1)
            )

    def set_current(self, track_id: str, playing: bool) -> None:
        old = self._current_id
        self._current_id = track_id or ""
        self._playing = playing
        for changed in {old, self._current_id}:
            row = self.row_of(changed) if changed else -1
            if row >= 0:
                self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))
        if old != self._current_id:
            self._current_row_changed(self._current_id)

    def _current_row_changed(self, track_id: str) -> None:
        view = self.parent()
        if isinstance(view, TrackTable):
            view.ensure_current_visible()

    def set_compact(self, compact: bool) -> None:
        if compact == self.compact:
            return
        self.compact = compact
        self.layoutChanged.emit()

    def sort(self, key: str, ascending: bool = True, *, emit: bool = True) -> None:  # noqa: N802
        if not key:
            return
        self._sort_key = key
        self._sort_asc = ascending
        reverse = not ascending

        def value(track: Track):
            if key == COLUMN_TITLE:
                return (track.title or "").casefold()
            if key == COLUMN_ARTIST:
                return (track.artist or "").casefold()
            if key == COLUMN_ALBUM:
                return (track.album or "").casefold()
            if key == COLUMN_DURATION:
                return track.duration_ms
            if key == "added":
                return track.added_at or 0.0
            if key == "played":
                return track.play_count
            if key == "year":
                return track.year
            return 0

        self.layoutAboutToBeChanged.emit()
        self._items.sort(key=value, reverse=reverse)
        self.layoutChanged.emit()
        if emit:
            self._resort_finished()

    def _resort_finished(self) -> None:
        pass


class TrackHeader(QWidget):
    sort_requested = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self._columns: list[Column] = list(DEFAULT_COLUMNS)
        self._widths: list[int] = [column.width for column in DEFAULT_COLUMNS]
        self._sort_key = ""
        self._sort_asc = True
        self._hover = -1
        self._view = None
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    def _pal(self):
        override = getattr(self, "_palette_override", None)
        return override or theme().palette

    def set_palette_override(self, palette) -> None:
        self._palette_override = palette
        self.update()

    def set_view(self, view) -> None:
        """Follow the table's real section geometry instead of guessing."""
        self._view = view
        self.update()

    def _spans(self) -> list[tuple[int, int]]:
        view = self._view
        if view is not None:
            spans = []
            for column in self._columns:
                try:
                    position = DEFAULT_COLUMNS.index(column)
                except ValueError:
                    continue
                if view.isColumnHidden(position):
                    continue
                width = view.columnWidth(position)
                if width > 0:
                    spans.append((view.columnViewportPosition(position), width))
            if len(spans) == len(self._columns):
                return spans
        spans = []
        left = 0
        for index, column in enumerate(self._columns):
            width = self._widths[index] if index < len(self._widths) else column.width
            spans.append((left, width))
            left += width
        return spans

    def set_widths(self, widths: Sequence[int]) -> None:
        self._widths = list(widths)
        self.update()

    def set_columns(self, columns: Sequence[Column]) -> None:
        self._columns = list(columns)
        self.update()

    def set_sort(self, key: str, ascending: bool) -> None:
        self._sort_key = key
        self._sort_asc = ascending
        self.update()

    def _hit(self, x: int) -> int:
        for index, (left, width) in enumerate(self._spans()):
            if left <= x < left + width:
                return index
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = self._hit(int(event.position().x()))
        if hover != self._hover:
            self._hover = hover
            self.update()
        column = self._columns[hover] if 0 <= hover < len(self._columns) else None
        self.setCursor(
            Qt.PointingHandCursor if column is not None and column.sortable else Qt.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            index = self._hit(int(event.position().x()))
            if 0 <= index < len(self._columns):
                column = self._columns[index]
                if column.sortable and column.key:
                    ascending = not self._sort_asc if column.key == self._sort_key else True
                    self.sort_requested.emit(column.key, ascending)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._pal()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = theme().font(8.4, 600)
        painter.setFont(font)
        left = 0
        for index, column in enumerate(self._columns):
            start, width = self._spans()[index]
            rect = QRectF(start, 0, width, self.height())
            active = column.key == self._sort_key and column.key
            color = rgba(palette.accent if active else palette.text, 0.92 if active else 0.42)
            painter.setPen(QPen(color))
            text_rect = rect.adjusted(12 if column.key != COLUMN_TITLE else 12, 0, -10, 0)
            draw_text(painter, text_rect, int(column.align), column.title)
            if active:
                arrow_rect = QRect(
                    int(rect.right()) - (12 if column.align & Qt.AlignRight else 22),
                    int(self.height() / 2 - 4),
                    8,
                    8,
                )
                draw_icon(
                    painter,
                    "chevron_up" if self._sort_asc else "chevron_down",
                    arrow_rect,
                    color,
                    0.9,
                )
            left += width
        painter.end()


class TrackDelegate(QStyledItemDelegate):
    def __init__(self, view: "TrackTable") -> None:
        super().__init__(view)
        self.view = view

    def _pal(self):
        override = getattr(self.view, "palette_override", None)
        return override or theme().palette

    # ----------------------------------------------------------------- paint
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        model = self.view.model()
        track: Track | None = index.data(TITLE_ROLE)
        if track is None:
            return
        palette = self._pal()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(option.rect).adjusted(1, 1, -1, -2)
        selected = bool(option.state & QStyle.State_Selected)
        # Row-level hover: Qt sets State_MouseOver per *cell*, which made the
        # cell under the cursor use a stronger tint than its siblings and the
        # row looked patchy.  Use the table's tracked hover row instead.
        hovered = getattr(self.view, '_hover_row', -1) == index.row()
        hover = hovered and not selected
        focused = bool(option.state & QStyle.State_HasFocus)
        is_current = track.id == model.current_id
        radius = 7.0

        # --- visual precedence (BUG-10) ------------------------------------
        # selected  : soft berry tint, title/text keep the normal colour so the
        #             playing state can never make the row unreadable
        # playing   : berry title + equaliser bars + leading accent marker
        # both      : tint + bars + marker, title stays text colour
        # hover     : neutral wash (never a second accent layer)
        # Draw the *same* full-row rounded rect in every column and let Qt's
        # per-cell clip do the rest. Painting it from column 0 only looked
        # continuous until Qt repainted a single cell (a cover finished loading,
        # a favourite toggled ...): that cell had no column 0, so the row looked
        # "broken". With the identical rect in every cell, both the row ends
        # (rounded) and the middle cells (square) line up seamlessly.
        # The row band is painted once by ``TrackTable.paintEvent`` before the
        # items are drawn.  Per-cell painting (even with a clip) left visible
        # seams whenever Qt repainted a single cell or a style path invoked the
        # delegate twice; one shape per row cannot stack or drift.

        if is_current and index.column() == COLUMN_INDEX:
            marker = QRectF(rect.left() + 2.5, rect.center().y() - rect.height() * 0.20, 3.0,
                            rect.height() * 0.40)
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.accent, 0.95))
            painter.drawRoundedRect(marker, 1.5, 1.5)

        column = DEFAULT_COLUMNS[index.column()].key
        inner = rect.adjusted(12, 0, -10, 0)
        if column == COLUMN_INDEX:
            self._paint_index(painter, rect, index.row(), is_current, selected)
        elif column == COLUMN_TITLE:
            self._paint_title(painter, inner, track, is_current, selected)
        elif column == COLUMN_ARTIST:
            self._paint_text(painter, inner, track.artist, 9.2, 0.66, is_current, selected,
                             secondary=True)
        elif column == COLUMN_ALBUM:
            self._paint_text(painter, inner, track.album, 9.2, 0.52, is_current, selected,
                             secondary=True)
        elif column == COLUMN_DURATION:
            self._paint_duration(painter, inner, track, selected)
        elif column == COLUMN_FAVORITE:
            self._paint_favorite(painter, rect, track, index.row())
        painter.restore()

    def _paint_index(self, painter: QPainter, rect: QRectF, row: int, is_current: bool,
                     selected: bool = False) -> None:
        palette = self._pal()
        if is_current:
            self._paint_bars(painter, rect)
            return
        font = theme().font(8.8, 500)
        painter.setFont(font)
        painter.setPen(QPen(rgba(palette.text, 0.50 if selected else 0.32)))
        painter.drawText(
            rect.adjusted(0, 0, -8, 0),
            int(Qt.AlignRight | Qt.AlignVCenter),
            str(row + 1),
        )

    def _paint_bars(self, painter: QPainter, rect: QRectF, ) -> None:
        palette = self._pal()
        phase = self.view.bar_phase
        playing = self.view.model().playing
        heights = []
        for i in range(3):
            if not playing:
                heights.append(4 + i * 2)
            else:
                import math

                wave = abs(math.sin(phase * 2.4 + i * 1.15))
                heights.append(4 + wave * 12)
        width = 2.4
        gap = 2.6
        total = 3 * width + 2 * gap
        # BUG-09: the row-number column right-aligns its text (rect.right()-8),
        # but the equaliser used to be centred in the column, so the playing
        # indicator looked shifted left compared with every other row number.
        x = rect.right() - 8 - total
        for height in heights:
            bar = QRectF(x, rect.center().y() - height / 2, width, height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(qcolor(palette.accent))
            painter.drawRoundedRect(bar, width / 2, width / 2)
            x += width + gap

    def _paint_title(self, painter: QPainter, rect: QRectF, track: Track, is_current: bool,
                     selected: bool = False) -> None:
        palette = self._pal()
        compact = self.view.model().compact
        cover_size = 36 if compact else 40
        cover_rect = QRectF(rect.left(), rect.center().y() - cover_size / 2, cover_size, cover_size)
        pixmap = None
        try:
            pixmap = ctx().covers.pixmap(track, cover_size * 2)
        except Exception:
            pixmap = None
        if pixmap is not None:
            from .common import paint_rounded_pixmap

            paint_rounded_pixmap(
                painter,
                cover_rect,
                pixmap,
                5.0,
                border=rgba(palette.text, 0.08),
            )
        else:
            radius = 5.0
            painter.setPen(Qt.NoPen)
            painter.setBrush(rgba(palette.text, 0.06))
            painter.drawRoundedRect(cover_rect, radius, radius)
            note = QRectF(cover_rect).adjusted(cover_size * 0.28, cover_size * 0.28, -cover_size * 0.28, -cover_size * 0.28)
            draw_icon(painter, "music_note", note, rgba(palette.text, 0.35))

        text_left = cover_rect.right() + 12
        # The source used to sit in a rounded pill on the right edge; with long
        # import ids it crowded the title and read as visual noise. It is now a
        # quiet suffix on the artist line: "加木 · 网易音乐".
        source = display_source(track) if track.is_online else ""
        available = rect.right() - text_left - 8

        title_font = theme().font(9.6 if not compact else 9.2, 600 if is_current else 500)
        painter.setFont(title_font)
        # accent title only while the row is *not* selected: on the tinted
        # selection background berry-on-berry was unreadable (BUG-10)
        if is_current and not selected:
            # The raw brand accent is 4.4:1 on the surface tone; nudge it toward
            # the foreground in dark mode so the playing title clears WCAG AA
            # (4.5:1) without losing the berry hue.
            color = (
                mix(palette.accent, palette.text, 0.16)
                if palette.is_dark
                else palette.accent
            )
        else:
            color = palette.text
        painter.setPen(QPen(rgba(color, 0.98)))
        metrics = QFontMetrics(title_font)
        title = metrics.elidedText(track.title, Qt.ElideRight, int(max(20, available)))

        # The two text rows are laid out from font metrics: fixed offsets
        # (16/20 px boxes) overlapped as soon as the type scale grew.
        sub_font = theme().font(8.2 if compact else 8.4, 400)
        title_metrics = QFontMetrics(title_font)
        sub_metrics = QFontMetrics(sub_font)
        row_gap = 2
        block_h = title_metrics.height() + row_gap + sub_metrics.height()
        block_top = rect.center().y() - block_h / 2.0
        title_rect = QRectF(text_left, block_top, max(20, available), title_metrics.height())
        sub_rect = QRectF(
            text_left,
            block_top + title_metrics.height() + row_gap,
            max(20, available),
            sub_metrics.height(),
        )
        artist_text = sub_metrics.elidedText(track.artist, Qt.ElideRight, int(max(20, available)))
        artist_w = min(float(sub_metrics.horizontalAdvance(artist_text)), available)
        source_text = ""
        if source and available - artist_w > 52:
            source_text = sub_metrics.elidedText(
                "· " + source, Qt.ElideRight, int(max(30, available - artist_w - 16))
            )

        def draw_subtitle(alpha: float) -> None:
            painter.setFont(sub_font)
            painter.setPen(QPen(rgba(palette.text, alpha)))
            draw_text(painter, sub_rect, int(Qt.AlignLeft | Qt.AlignVCenter), artist_text)
            if source_text:
                painter.setPen(QPen(rgba(palette.text, 0.3)))
                draw_text(
                    painter,
                    QRectF(
                        text_left + artist_w + 8,
                        sub_rect.top(),
                        max(24, available - artist_w - 8),
                        sub_rect.height(),
                    ),
                    int(Qt.AlignLeft | Qt.AlignVCenter),
                    source_text,
                )

        if compact:
            draw_text(painter, title_rect, int(Qt.AlignLeft | Qt.AlignVCenter), title)
            draw_subtitle(0.62 if selected else 0.5)
        elif track.artist:
            draw_text(painter, title_rect, int(Qt.AlignLeft | Qt.AlignVCenter), title)
            draw_subtitle(0.62 if selected else 0.46)
        else:
            draw_text(
                painter,
                QRectF(text_left, rect.top(), max(20, available), rect.height()),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                title,
            )


    def _paint_text(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        size: float,
        opacity: float,
        is_current: bool,
        selected: bool = False,
        *,
        secondary: bool = False,
    ) -> None:
        palette = self._pal()
        font = theme().font(size, 500)
        painter.setFont(font)
        color = palette.text
        alpha = max(opacity, 0.72) if selected else opacity
        painter.setPen(QPen(rgba(color, alpha)))
        metrics = QFontMetrics(font)
        painter.drawText(
            rect,
            int(Qt.AlignLeft | Qt.AlignVCenter),
            metrics.elidedText(text or "—", Qt.ElideRight, int(rect.width())),
        )

    def _paint_duration(self, painter: QPainter, rect: QRectF, track: Track,
                        selected: bool = False) -> None:
        palette = self._pal()
        font = theme().font(8.6, 500)
        painter.setFont(font)
        painter.setPen(QPen(rgba(palette.text, 0.58 if selected else 0.42)))
        text = format_duration(track.duration_ms) if track.duration_ms else "—"
        painter.drawText(rect, int(Qt.AlignRight | Qt.AlignVCenter), text)

    def _paint_favorite(self, painter: QPainter, rect: QRectF, track: Track, row: int) -> None:
        palette = self._pal()
        favorite = self.view.model().is_favorite(track.id)
        hovered = self.view.favorite_hover_row == row
        size = 15
        icon_rect = QRect(
            int(rect.center().x() - size / 2),
            int(rect.center().y() - size / 2),
            size,
            size,
        )
        if favorite:
            draw_icon(painter, "heart_fill", icon_rect, rgba(palette.accent, 0.95))
        elif hovered:
            draw_icon(painter, "heart", icon_rect, rgba(palette.text, 0.35))
        else:
            draw_icon(painter, "heart", icon_rect, rgba(palette.text, 0.0))

    # ---------------------------------------------------------------- sizing
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        base = 44 if self.view.model().compact else 54
        height = theme().scaled(base, factor=0.8)
        return QSize(100, height)


class TrackTable(QTableView):
    """Table view with a hand-drawn header and rich row delegate."""

    def _pal(self):
        return getattr(self, "palette_override", None) or theme().palette

    play_requested = Signal(object, int)  # list[Track], index
    menu_requested = Signal(object, QPoint)  # list[Track], global pos
    favorite_clicked = Signal(object)  # Track
    sort_requested = Signal(str, bool)
    remove_requested = Signal(object)  # list[Track]
    rows_moved = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = TrackTableModel(self)
        self.setModel(self._model)
        self.palette_override = None
        self._delegate = TrackDelegate(self)
        self.setItemDelegate(self._delegate)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        # When the scrollbar appears the viewport narrows by its width; without
        # re-applying the columns the last one (时长) ends up clipped.
        self._column_timer = QTimer(self)
        self._column_timer.setSingleShot(True)
        self._column_timer.setInterval(0)
        self._column_timer.timeout.connect(self._apply_columns)
        self.verticalScrollBar().rangeChanged.connect(
            lambda *_: self._column_timer.start()
        )
        self.setShowGrid(False)
        # Windows 11 原生样式会在选中行的每个单元格边上画 2px 系统强调色描边，
        # 视觉上就是“分块的色带”。表格固定用 Fusion，自己画整行色带。
        self.setStyle(QStyleFactory.create("Fusion"))
        self.setFrameShape(QTableView.NoFrame)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(theme().scaled(54, factor=0.8))
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCornerButtonEnabled(False)
        self.setStyleSheet("QTableView{background:transparent;border:none;outline:none;}")
        # BUG-10: Qt still painted its own highlight/focus decorations (solid
        # blue bars at every cell edge) on top of the delegate painter. Make
        # the native highlight fully transparent; the delegate owns selection.
        self._neutralise_native_selection()
        self.viewport().setAutoFillBackground(False)
        self.setAutoFillBackground(False)
        self._columns = list(DEFAULT_COLUMNS)
        self._header = TrackHeader()
        self._header.set_view(self)
        self.setAccessibleName("歌曲列表")
        self._header.sort_requested.connect(self._on_sort_requested)
        self.bar_phase = 0.0
        self.favorite_hover_row = -1
        self._hover_row = -1
        self.selectionModel().selectionChanged.connect(lambda *_: self.viewport().update())
        self._reorder = False
        self._anim = QTimer(self)
        self._anim.setInterval(90)
        self._anim.timeout.connect(self._tick)
        self.doubleClicked.connect(self._on_double_click)
        self.clicked.connect(self._on_click)
        self._empty_text = "这里还没有歌曲"
        self._empty_hint = ""
        self.setAccessibleName("歌曲列表")

    # ------------------------------------------------------------- tooltips
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt name)
        kind = event.type()
        if watched is self.viewport():
            if kind == QEvent.Type.MouseMove:
                index = self.indexAt(event.pos())
                row = index.row() if index.isValid() else -1
                if row != self._hover_row:
                    self._hover_row = row
                    self.viewport().update()
            elif kind == QEvent.Type.Leave:
                if self._hover_row != -1:
                    self._hover_row = -1
                    self.viewport().update()
            if kind == QEvent.Type.ToolTip:
                index = self.indexAt(event.pos())
                if index.isValid():
                    text = tip_text(self._model.track_at(index.row()))
                    if text:
                        show_tip(event.globalPos(), text)
                        return True
                hide_tip()
            elif kind in (
                QEvent.Type.Leave,
                QEvent.Type.Wheel,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.Hide,
            ):
                hide_tip()
        return super().eventFilter(watched, event)

    def _neutralise_native_selection(self) -> None:
        from PySide6.QtGui import QColor as _QColor, QPalette as _QPalette

        pal = self.palette()
        for role in (_QPalette.ColorRole.Highlight, _QPalette.ColorRole.HighlightedText):
            color = _QColor(0, 0, 0, 0) if role == _QPalette.ColorRole.Highlight else _QColor(
                theme().palette.text
            )
            pal.setColor(_QPalette.ColorGroup.Active, role, color)
            pal.setColor(_QPalette.ColorGroup.Inactive, role, color)
            pal.setColor(_QPalette.ColorGroup.Disabled, role, color)
        self.setPalette(pal)
        self.viewport().setPalette(pal)

    # ------------------------------------------------------------------- api
    @property
    def header(self) -> TrackHeader:
        return self._header

    @property
    def table_model(self) -> TrackTableModel:
        return self._model

    def set_tracks(self, tracks: Sequence[Track]) -> None:
        self._model.set_tracks(tracks)
        self._apply_columns()
        self._update_anim()
        self.viewport().update()

    def set_empty_text(self, text: str, hint: str = "") -> None:
        self._empty_text = text
        self._empty_hint = hint
        self.viewport().update()

    def set_compact(self, compact: bool) -> None:
        self._model.set_compact(compact)
        self.verticalHeader().setDefaultSectionSize(
            theme().scaled(44 if compact else 54, factor=0.8)
        )
        self._apply_columns()
        self.viewport().update()

    def set_drag_reorder(self, enabled: bool) -> None:
        self._reorder = enabled
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.setDropIndicatorShown(enabled)
        self.setDragDropMode(
            QAbstractItemView.InternalMove if enabled else QAbstractItemView.NoDragDrop
        )
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event) -> None:  # noqa: N802
        if not self._reorder:
            super().dropEvent(event)
            return
        source = self.currentIndex().row()
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(position)
        target = index.row() if index.isValid() else self._model.rowCount() - 1
        event.accept()
        if source >= 0 and target >= 0 and source != target:
            self.rows_moved.emit(source, target)

    def set_favorites(self, ids: Iterable[str]) -> None:
        self._model.set_favorites(ids)

    def set_current(self, track_id: str, playing: bool) -> None:
        self._model.set_current(track_id, playing)
        self._update_anim()

    def tracks(self) -> list[Track]:
        return self._model.tracks

    def selected_tracks(self) -> list[Track]:
        rows = sorted({index.row() for index in self.selectionModel().selectedRows()})
        return [self._model.tracks[row] for row in rows if 0 <= row < len(self._model.tracks)]

    def sort(self, key: str, ascending: bool = True) -> None:
        self._model.sort(key, ascending)
        self._header.set_sort(key, ascending)
        self._update_anim()

    def ensure_current_visible(self) -> None:
        row = self._model.row_of(self._model.current_id)
        if row >= 0:
            index = self._model.index(row, 0)
            self.scrollTo(index, QAbstractItemView.EnsureVisible)

    def refresh_theme(self) -> None:
        self._neutralise_native_selection()
        self.viewport().update()
        self._header.update()

    def refresh_covers(self) -> None:
        self.viewport().update()

    def _update_anim(self) -> None:
        playing = self._model.playing and bool(self._model.current_id)
        wanted = playing and not theme().reduce_motion
        if wanted and not self._anim.isActive():
            self._anim.start()
        elif not wanted and self._anim.isActive():
            self._anim.stop()
        self.viewport().update()

    def _tick(self) -> None:
        self.bar_phase += 0.1
        row = self._model.row_of(self._model.current_id)
        if row < 0:
            return
        rect = self.visualRect(self._model.index(row, 0))
        self.viewport().update(rect.adjusted(0, 0, self.viewport().width(), 0))

    # ---------------------------------------------------------------- columns
    def _apply_columns(self) -> None:
        width = max(240, self.viewport().width())
        compact = self._model.compact or width < 760
        visible: list[Column] = []
        widths: list[int] = []
        fixed = 0
        for column in DEFAULT_COLUMNS:
            if column.key == COLUMN_ALBUM and width < 900:
                continue
            if column.key == COLUMN_ARTIST and width < 620:
                continue
            if column.key == COLUMN_FAVORITE and width < 470:
                # In the narrow queue panel the heart steals the room the
                # source badge and title need; the menu still has 收藏.
                continue
            # Fixed column widths follow the type scale, otherwise enlarged
            # text gets elided while the column keeps its 1.0-era width.
            column_width = theme().scaled(column.width, factor=0.55) if column.width else 0
            if column.key == COLUMN_INDEX and width < 360:
                # The narrow fallback must follow the type scale too: at 1.5x
                # a 46 px duration column clipped "4:02" to ":02".
                column_width = max(30, theme().scaled(26, factor=0.6))
            if column.key == COLUMN_DURATION and width < 360:
                column_width = max(
                    46,
                    theme().scaled(40, factor=0.6)
                    + QFontMetrics(theme().font(8.4, 400)).horizontalAdvance("00:00") // 4,
                )
            visible.append(column)
            widths.append(column_width)
            if column_width:
                fixed += column_width
        stretch = max(110, width - fixed - 2)
        for position, column in enumerate(DEFAULT_COLUMNS):
            hidden = column not in visible
            self.setColumnHidden(position, hidden)
        resolved: list[int] = []
        for column, column_width in zip(visible, widths):
            if not column_width:
                column_width = stretch
            position = DEFAULT_COLUMNS.index(column)
            self.setColumnWidth(position, column_width)
            resolved.append(column_width)
        self._columns = visible
        self._header.set_columns(visible)
        self._header.set_widths(resolved)
        if self._model.compact != compact:
            self._model.compact = compact
            self.verticalHeader().setDefaultSectionSize(
            theme().scaled(44 if compact else 54, factor=0.8)
        )
        self._header.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_columns()

    # ----------------------------------------------------------------- events
    def _on_sort_requested(self, key: str, ascending: bool) -> None:
        self._model.sort(key, ascending)
        self._header.set_sort(key, ascending)
        self.sort_requested.emit(key, ascending)

    def _on_double_click(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = index.row()
        self.play_requested.emit(list(self._model.tracks), row)

    def _on_click(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        column = DEFAULT_COLUMNS[index.column()].key if index.column() < len(DEFAULT_COLUMNS) else ""
        if column == COLUMN_FAVORITE:
            track = self._model.track_at(index.row())
            if track is not None:
                self.favorite_clicked.emit(track)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.position().toPoint())
        row = index.row() if index.isValid() else -1
        column = DEFAULT_COLUMNS[index.column()].key if index.isValid() else ""
        wanted = row if column == COLUMN_FAVORITE else -1
        if wanted != self.favorite_hover_row:
            old = self.favorite_hover_row
            self.favorite_hover_row = wanted
            for target in {old, wanted}:
                if target >= 0:
                    rect = self.visualRect(self._model.index(target, len(DEFAULT_COLUMNS) - 1))
                    self.viewport().update(rect)
        if column == COLUMN_FAVORITE:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.favorite_hover_row >= 0:
            row = self.favorite_hover_row
            self.favorite_hover_row = -1
            self.viewport().update()
        super().leaveEvent(event)

    def _on_context_menu(self, point: QPoint) -> None:
        index = self.indexAt(point)
        if index.isValid() and index.row() not in {
            item.row() for item in self.selectionModel().selectedRows()
        }:
            self.selectRow(index.row())
        tracks = self.selected_tracks()
        if not tracks:
            track = self._model.track_at(index.row()) if index.isValid() else None
            if track is None:
                return
            tracks = [track]
        self.menu_requested.emit(tracks, self.viewport().mapToGlobal(point))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            tracks = self.selected_tracks()
            if tracks:
                row = self._model.row_of(tracks[0].id)
                self.play_requested.emit(list(self._model.tracks), max(0, row))
            return
        if event.key() == Qt.Key_Delete:
            tracks = self.selected_tracks()
            if tracks:
                self.remove_requested.emit(tracks)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802
        self._paint_row_bands()
        super().paintEvent(event)
        if self._model.rowCount() == 0:
            self._paint_empty()

    def _paint_row_bands(self) -> None:
        """选中的行与悬停行只在视口画一次整条色带，避免逐格叠加/接缝。"""
        model = self.model()
        if model is None or model.rowCount() == 0:
            return
        palette = self._pal()
        selection = self.selectionModel()
        hover_row = getattr(self, "_hover_row", -1)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        width = max(1.0, self.viewport().width() - 1.0)
        for row in range(model.rowCount()):
            selected = bool(selection and selection.isRowSelected(row, QModelIndex()))
            hovered = row == hover_row
            if not selected and not hovered:
                continue
            top = self.rowViewportPosition(row)
            height = self.rowHeight(row)
            if height <= 0:
                continue
            rect = QRectF(0.5, top + 1.0, width, height - 3.0)
            if selected:
                alpha = (0.20 if hovered else 0.15) if palette.is_dark else (0.15 if hovered else 0.11)
                painter.setBrush(rgba(palette.accent, alpha))
            else:
                painter.setBrush(rgba(palette.text, 0.045))
            painter.drawRoundedRect(rect, 7.0, 7.0)
        painter.end()

    def _paint_empty(self) -> None:
        palette = self._pal()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.viewport().rect())
        note_rect = QRect(int(rect.center().x() - 22), int(rect.center().y() - 74), 44, 44)
        draw_icon(painter, "music_note", note_rect, rgba(palette.text, 0.18))
        font = theme().font(10.5, 600)
        painter.setFont(font)
        painter.setPen(QPen(rgba(palette.text, 0.55)))
        painter.drawText(
            QRectF(rect.left(), rect.center().y() - 18, rect.width(), 22),
            int(Qt.AlignHCenter | Qt.AlignVCenter),
            self._empty_text,
        )
        if self._empty_hint:
            sub = theme().font(9.0, 400)
            painter.setFont(sub)
            painter.setPen(QPen(rgba(palette.text, 0.36)))
            painter.drawText(
                QRectF(rect.left(), rect.center().y() + 6, rect.width(), 20),
                int(Qt.AlignHCenter | Qt.AlignVCenter),
                self._empty_hint,
            )
        painter.end()


class TrackListWidget(QWidget):
    """Header + table composite, what pages actually embed."""

    play_requested = Signal(object, int)
    menu_requested = Signal(object, QPoint)
    favorite_clicked = Signal(object)
    sort_requested = Signal(str, bool)
    remove_requested = Signal(object)
    selection_changed = Signal(object)
    reordered = Signal(int, int)  # from row, to row

    play_selected_requested = Signal(object)
    play_next_requested = Signal(object)
    enqueue_requested = Signal(object)
    favorite_selected_requested = Signal(object)
    playlist_requested = Signal(object)
    remove_selected_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = TrackTable(self)
        self._can_remove_rows = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.table.header)
        layout.addWidget(self.table, 1)
        self.table.play_requested.connect(self.play_requested)
        self.table.menu_requested.connect(self.menu_requested)
        self.table.favorite_clicked.connect(self.favorite_clicked)
        self.table.sort_requested.connect(self.sort_requested)
        self.table.remove_requested.connect(self.remove_requested)
        self.table.rows_moved.connect(self.reordered)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)

        from .selectionbar import SelectionBar

        self.selection_bar = SelectionBar(self)
        self.selection_bar.play_requested.connect(
            lambda: self.play_selected_requested.emit(self.selected_tracks())
        )
        self.selection_bar.next_requested.connect(
            lambda: self.play_next_requested.emit(self.selected_tracks())
        )
        self.selection_bar.queue_requested.connect(
            lambda: self.enqueue_requested.emit(self.selected_tracks())
        )
        self.selection_bar.favorite_requested.connect(
            lambda: self.favorite_selected_requested.emit(self.selected_tracks())
        )
        self.selection_bar.playlist_requested.connect(
            lambda: self.playlist_requested.emit(self.selected_tracks())
        )
        self.selection_bar.remove_requested.connect(
            lambda: self.remove_selected_requested.emit(self.selected_tracks())
        )
        self.selection_bar.clear_requested.connect(self.clear_selection)

    def set_drag_reorder(self, enabled: bool) -> None:
        self.table.set_drag_reorder(enabled)

    def _on_selection(self, *_args) -> None:
        tracks = self.table.selected_tracks()
        self.selection_changed.emit(tracks)
        self.selection_bar.set_selection(len(tracks), can_remove=self._can_remove_rows)
        self._place_selection_bar()

    def set_can_remove_selected(self, allowed: bool) -> None:
        self._can_remove_rows = bool(allowed)
        self.selection_bar.set_selection(len(self.selected_tracks()), can_remove=allowed)

    def clear_selection(self) -> None:
        self.table.clearSelection()
        self.table.setCurrentIndex(self.table.model().index(-1, -1))

    def _place_selection_bar(self) -> None:
        bar = getattr(self, "selection_bar", None)
        if bar is None or not bar.isVisible():
            return
        margin = 16
        bar.setGeometry(
            margin,
            max(0, self.height() - bar.height() - margin),
            max(240, self.width() - margin * 2),
            bar.height(),
        )
        bar.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_selection_bar()

    # convenience passthroughs
    def set_tracks(self, tracks: Sequence[Track]) -> None:
        self.table.set_tracks(tracks)

    def set_empty_text(self, text: str, hint: str = "") -> None:
        self.table.set_empty_text(text, hint)

    def set_favorites(self, ids: Iterable[str]) -> None:
        self.table.set_favorites(ids)

    def set_current(self, track_id: str, playing: bool) -> None:
        self.table.set_current(track_id, playing)

    def ensure_current_visible(self) -> None:
        self.table.ensure_current_visible()

    def set_compact(self, compact: bool) -> None:
        self.table.set_compact(compact)

    def tracks(self) -> list[Track]:
        return self.table.tracks()

    def selected_tracks(self) -> list[Track]:
        return self.table.selected_tracks()

    def sort(self, key: str, ascending: bool = True) -> None:
        self.table.sort(key, ascending)

    def set_palette_override(self, palette) -> None:
        """Paint this list with a fixed palette (the immersive stage is dark)."""
        self.table.palette_override = palette
        header = getattr(self.table, "_header", None)
        if header is not None:
            header.set_palette_override(palette)
        self.table.viewport().update()
        self.table.update()

    def refresh_theme(self) -> None:
        self.table.refresh_theme()

    def refresh_covers(self) -> None:
        self.table.refresh_covers()


__all__ = [
    "COLUMN_ALBUM",
    "COLUMN_ARTIST",
    "COLUMN_DURATION",
    "COLUMN_FAVORITE",
    "COLUMN_INDEX",
    "COLUMN_TITLE",
    "DEFAULT_COLUMNS",
    "TrackListWidget",
    "TrackTable",
    "TrackTableModel",
]
