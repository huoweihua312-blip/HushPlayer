from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.models.media_item import MediaItem


TRACK_MARKER_WIDTH = 18
TRACK_DURATION_WIDTH = 62
TRACK_COLUMN_GAP = 14


def configure_track_columns(layout: QGridLayout) -> None:
    layout.setColumnMinimumWidth(0, TRACK_MARKER_WIDTH)
    layout.setColumnStretch(1, 4)
    layout.setColumnStretch(2, 2)
    layout.setColumnStretch(3, 2)
    layout.setColumnMinimumWidth(4, TRACK_DURATION_WIDTH)


class SearchEntryLineEdit(QLineEdit):
    focused = Signal()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focused.emit()


class CanonicalTrackDelegate(QStyledItemDelegate):
    def __init__(self, playing_key_provider=None, parent=None) -> None:
        super().__init__(parent)
        self.playing_key_provider = playing_key_provider or (lambda: "")

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, 58)

    @staticmethod
    def column_rects(rect) -> dict[str, QRectF]:
        row_rect = QRectF(rect.adjusted(2, 2, -2, -2))
        content = row_rect.adjusted(12, 0, -12, 0)
        available_width = max(0, int(content.width()))
        fixed_width = TRACK_MARKER_WIDTH + TRACK_DURATION_WIDTH
        gap = min(TRACK_COLUMN_GAP, max(0, (available_width - fixed_width) // 4))
        flexible_width = max(0, available_width - fixed_width - gap * 4)
        title_width = int(flexible_width * 0.5)
        artist_width = int(flexible_width * 0.25)
        album_width = max(0, flexible_width - title_width - artist_width)
        x = content.left()
        result = {"marker": QRectF(x, content.top(), TRACK_MARKER_WIDTH, content.height())}
        x += TRACK_MARKER_WIDTH + gap
        result["title"] = QRectF(x, content.top(), title_width, content.height())
        x += title_width + gap
        result["artist"] = QRectF(x, content.top(), artist_width, content.height())
        x += artist_width + gap
        result["album"] = QRectF(x, content.top(), album_width, content.height())
        x += album_width + gap
        result["duration"] = QRectF(x, content.top(), TRACK_DURATION_WIDTH, content.height())
        return result

    def paint(self, painter: QPainter, option, index) -> None:
        raw = index.data(Qt.ItemDataRole.UserRole)
        try:
            item = MediaItem.from_mapping(raw)
        except (TypeError, ValueError):
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        row_rect = QRectF(option.rect.adjusted(2, 2, -2, -2))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_playing = bool(
            item.stable_identity
            and item.stable_identity == str(self.playing_key_provider() or "")
        )
        if selected:
            background, border = QColor(76, 141, 255, 48), QColor(76, 141, 255, 118)
        elif is_playing:
            background, border = QColor(76, 141, 255, 27), QColor(76, 141, 255, 70)
        elif hovered:
            background, border = QColor(255, 255, 255, 14), QColor(255, 255, 255, 10)
        else:
            background, border = QColor(0, 0, 0, 0), QColor(0, 0, 0, 0)
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(row_rect, 10, 10)
        if is_playing:
            painter.fillRect(
                QRectF(row_rect.left(), row_rect.top() + 8, 3, row_rect.height() - 16),
                QColor("#4c8dff"),
            )
        rects = self.column_rects(option.rect)
        duration = f"{item.duration // 60}:{item.duration % 60:02d}" if item.duration else "—"
        self._draw(painter, option, rects["marker"], "▶" if is_playing else "", "#4c8dff", True)
        self._draw(painter, option, rects["title"], item.title, "#ffffff" if is_playing else "#f3f4f6", is_playing)
        self._draw(painter, option, rects["artist"], item.artist, "#b5bbc7")
        self._draw(painter, option, rects["album"], item.album, "#b5bbc7")
        self._draw(painter, option, rects["duration"], duration, "#8a92a3", align_right=True)
        painter.restore()

    def helpEvent(self, event, view, option, index) -> bool:
        if event.type() != QEvent.Type.ToolTip:
            return super().helpEvent(event, view, option, index)
        try:
            item = MediaItem.from_mapping(index.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return False
        rects = self.column_rects(option.rect)
        for field, text in (("title", item.title), ("artist", item.artist), ("album", item.album)):
            if not rects[field].contains(event.pos()):
                continue
            if QFontMetrics(option.font).horizontalAdvance(text) > int(rects[field].width()):
                QToolTip.showText(event.globalPos(), text, view, rects[field].toRect())
                return True
            break
        QToolTip.hideText()
        return False

    @staticmethod
    def _draw(painter, option, rect, text, color, bold=False, align_right=False) -> None:
        font = QFont(option.font)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        elided = QFontMetrics(font).elidedText(
            str(text), Qt.TextElideMode.ElideRight, max(1, int(rect.width()))
        )
        alignment = Qt.AlignmentFlag.AlignVCenter
        alignment |= Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
        painter.drawText(rect, alignment, elided)


class TrackListView(QFrame):
    sortRequested = Signal(str)

    def __init__(
        self,
        object_name: str = "trackListView",
        empty_text: str = "没有歌曲",
        selection_mode=QAbstractItemView.SelectionMode.SingleSelection,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.header = QFrame()
        self.header.setObjectName("songTableHeader")
        header_layout = QGridLayout(self.header)
        header_layout.setContentsMargins(14, 0, 14, 0)
        header_layout.setHorizontalSpacing(TRACK_COLUMN_GAP)
        configure_track_columns(header_layout)
        marker = QLabel("")
        marker.setFixedWidth(TRACK_MARKER_WIDTH)
        header_layout.addWidget(marker, 0, 0)
        self.sort_buttons: dict[str, QPushButton] = {}
        for column, (label, field) in enumerate(
            (("歌曲标题", "title"), ("歌手", "artist"), ("专辑", "album")), start=1
        ):
            button = QPushButton(label)
            button.setObjectName("songTableHeaderButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            button.clicked.connect(
                lambda checked=False, current=field: self.sortRequested.emit(current)
            )
            self.sort_buttons[field] = button
            header_layout.addWidget(button, 0, column)
        duration = QLabel("时长")
        duration.setObjectName("songTableHeaderLabel")
        duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        duration.setFixedWidth(TRACK_DURATION_WIDTH)
        header_layout.addWidget(duration, 0, 4)

        self.empty_label = QLabel(empty_text)
        self.empty_label.setObjectName("listEmptyHint")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(180)
        self.empty_label.hide()

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("songList")
        self.list_widget.setWordWrap(False)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(2)
        self.list_widget.setSelectionMode(selection_mode)
        self.list_widget.setAcceptDrops(False)

        layout.addWidget(self.header)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.list_widget, 1)

    def use_canonical_delegate(self, playing_key_provider=None) -> None:
        self.list_widget.setItemDelegate(
            CanonicalTrackDelegate(playing_key_provider, self.list_widget)
        )

    def scroll_to_top(self) -> None:
        self.list_widget.scrollToTop()
        QTimer.singleShot(0, self.list_widget.scrollToTop)

    def set_items(self, items: list[MediaItem | dict], empty_text: str = "没有找到歌曲") -> None:
        selected_key = ""
        current = self.list_widget.currentItem()
        if current is not None:
            try:
                selected_key = MediaItem.from_mapping(
                    current.data(Qt.ItemDataRole.UserRole)
                ).stable_identity
            except (TypeError, ValueError):
                selected_key = ""
        self.list_widget.blockSignals(True)
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.clear()
        selected_item = None
        for value in items:
            media_item = MediaItem.from_mapping(value)
            data = media_item.to_dict()
            list_item = QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.UserRole, data)
            list_item.setToolTip(
                f"{media_item.title}\n{media_item.artist} · {media_item.album}"
            )
            self.list_widget.addItem(list_item)
            if media_item.stable_identity == selected_key:
                selected_item = list_item
        self.list_widget.blockSignals(False)
        self.list_widget.setUpdatesEnabled(True)
        has_items = self.list_widget.count() > 0
        self.list_widget.setVisible(has_items)
        self.empty_label.setText(empty_text)
        self.empty_label.setVisible(not has_items)
        if selected_item is not None:
            self.list_widget.setCurrentItem(selected_item)
        self.scroll_to_top()
