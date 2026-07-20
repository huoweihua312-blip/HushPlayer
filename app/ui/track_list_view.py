from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
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
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.models.media_item import MediaItem


TRACK_LIKE_WIDTH = 28
TRACK_MARKER_WIDTH = 18
TRACK_DURATION_WIDTH = 62
TRACK_COLUMN_GAP = 14


def configure_track_columns(layout: QGridLayout) -> None:
    layout.setColumnMinimumWidth(0, TRACK_LIKE_WIDTH)
    layout.setColumnMinimumWidth(1, TRACK_MARKER_WIDTH)
    layout.setColumnStretch(2, 4)
    layout.setColumnStretch(3, 2)
    layout.setColumnStretch(4, 2)
    layout.setColumnMinimumWidth(5, TRACK_DURATION_WIDTH)


def track_like_rect(rect) -> QRectF:
    row_rect = QRectF(rect.adjusted(2, 2, -2, -2))
    content = row_rect.adjusted(8, 0, -8, 0)
    return QRectF(content.left(), content.top(), TRACK_LIKE_WIDTH, content.height())


def draw_track_like_icon(
    painter: QPainter,
    rect: QRectF,
    *,
    liked: bool,
    hovered: bool = False,
) -> None:
    icon_size = min(20.0, max(14.0, min(rect.width(), rect.height()) - 8.0))
    icon_rect = QRectF(0, 0, icon_size, icon_size)
    icon_rect.moveCenter(rect.center())
    if hovered:
        hover_color = QColor(225, 91, 100, 38) if liked else QColor(255, 255, 255, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hover_color)
        painter.drawEllipse(icon_rect.adjusted(-4, -4, 4, 4))

    left = icon_rect.left()
    top = icon_rect.top()
    width = icon_rect.width()
    height = icon_rect.height()
    path = QPainterPath()
    path.moveTo(left + width * 0.50, top + height * 0.88)
    path.cubicTo(
        left + width * 0.42,
        top + height * 0.80,
        left + width * 0.10,
        top + height * 0.59,
        left + width * 0.10,
        top + height * 0.34,
    )
    path.cubicTo(
        left + width * 0.10,
        top + height * 0.15,
        left + width * 0.25,
        top + height * 0.06,
        left + width * 0.39,
        top + height * 0.13,
    )
    path.cubicTo(
        left + width * 0.45,
        top + height * 0.16,
        left + width * 0.48,
        top + height * 0.21,
        left + width * 0.50,
        top + height * 0.25,
    )
    path.cubicTo(
        left + width * 0.52,
        top + height * 0.21,
        left + width * 0.55,
        top + height * 0.16,
        left + width * 0.61,
        top + height * 0.13,
    )
    path.cubicTo(
        left + width * 0.75,
        top + height * 0.06,
        left + width * 0.90,
        top + height * 0.15,
        left + width * 0.90,
        top + height * 0.34,
    )
    path.cubicTo(
        left + width * 0.90,
        top + height * 0.59,
        left + width * 0.58,
        top + height * 0.80,
        left + width * 0.50,
        top + height * 0.88,
    )
    path.closeSubpath()
    color = QColor("#e15b64" if liked else ("#f0f3f8" if hovered else "#aeb6c5"))
    pen = QPen(color, 1.8)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(color if liked else Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


class LikeAwareListWidget(QListWidget):
    """QListWidget with a delegate-painted, non-selecting like hit target."""

    likeToggleRequested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._like_state_provider = lambda _value: False
        self._pressed_like_item: QListWidgetItem | None = None
        self._hovered_like_item: QListWidgetItem | None = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def set_like_state_provider(self, provider) -> None:
        self._like_state_provider = provider or (lambda _value: False)
        self.viewport().update()

    def is_value_liked(self, value: dict) -> bool:
        try:
            state = self._like_state_provider(value)
        except Exception:
            return False
        if isinstance(state, dict):
            return bool(state.get("liked"))
        return bool(state)

    def is_index_like_hovered(self, index) -> bool:
        item = self.itemFromIndex(index)
        return item is not None and item is self._hovered_like_item

    @staticmethod
    def identity_for_value(value: dict | None) -> str:
        if not isinstance(value, dict):
            return ""
        try:
            return MediaItem.from_mapping(value).stable_identity
        except (TypeError, ValueError):
            return ""

    def refresh_like_identity(self, identity: str) -> int:
        target = str(identity or "")
        if not target:
            return 0
        refreshed = 0
        for row in range(self.count()):
            item = self.item(row)
            value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if self.identity_for_value(value) != target:
                continue
            self.viewport().update(self.visualItemRect(item))
            refreshed += 1
        return refreshed

    def like_rect_for_item(self, item: QListWidgetItem) -> QRectF:
        return track_like_rect(self.visualItemRect(item))

    def _like_item_at(self, position) -> QListWidgetItem | None:
        point = position.toPoint() if hasattr(position, "toPoint") else position
        item = self.itemAt(point)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, dict):
            return None
        return item if self.like_rect_for_item(item).contains(point) else None

    def _set_hovered_like_item(self, item: QListWidgetItem | None) -> None:
        previous = self._hovered_like_item
        if previous is item:
            return
        self._hovered_like_item = item
        for changed in (previous, item):
            if changed is not None and self.row(changed) >= 0:
                self.viewport().update(self.visualItemRect(changed))
        if item is None:
            self.viewport().unsetCursor()
        else:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseMoveEvent(self, event) -> None:
        item = self._like_item_at(event.position())
        self._set_hovered_like_item(item)
        if self._pressed_like_item is not None:
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            item = self._like_item_at(event.position())
            if item is not None:
                self._pressed_like_item = item
                self._set_hovered_like_item(item)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        pressed = self._pressed_like_item
        if pressed is not None:
            self._pressed_like_item = None
            released = self._like_item_at(event.position())
            if released is pressed:
                value = pressed.data(Qt.ItemDataRole.UserRole)
                if isinstance(value, dict):
                    self.likeToggleRequested.emit(dict(value))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._like_item_at(event.position()) is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered_like_item(None)
        super().leaveEvent(event)

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            item = self._like_item_at(event.pos())
            if item is not None:
                value = item.data(Qt.ItemDataRole.UserRole)
                tooltip = (
                    "从我喜欢移除"
                    if isinstance(value, dict) and self.is_value_liked(value)
                    else "添加到我喜欢"
                )
                QToolTip.showText(event.globalPos(), tooltip, self.viewport())
                return True
        return super().viewportEvent(event)


class IndentedLikeDelegate(QStyledItemDelegate):
    """Adds the common vector heart to otherwise standard list rows."""

    def paint(self, painter: QPainter, option, index) -> None:
        value = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, dict):
            super().paint(painter, option, index)
            return
        adjusted = QStyleOptionViewItem(option)
        adjusted.rect = option.rect.adjusted(TRACK_LIKE_WIDTH + 8, 0, 0, 0)
        super().paint(painter, adjusted, index)
        view = self.parent()
        liked = bool(
            isinstance(view, LikeAwareListWidget) and view.is_value_liked(value)
        )
        hovered = bool(
            isinstance(view, LikeAwareListWidget)
            and view.is_index_like_hovered(index)
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw_track_like_icon(
            painter,
            track_like_rect(option.rect),
            liked=liked,
            hovered=hovered,
        )
        painter.restore()


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
        fixed_width = TRACK_LIKE_WIDTH + TRACK_MARKER_WIDTH + TRACK_DURATION_WIDTH
        gap = min(TRACK_COLUMN_GAP, max(0, (available_width - fixed_width) // 5))
        flexible_width = max(0, available_width - fixed_width - gap * 5)
        title_width = int(flexible_width * 0.5)
        artist_width = int(flexible_width * 0.25)
        album_width = max(0, flexible_width - title_width - artist_width)
        x = content.left()
        result = {"like": QRectF(x, content.top(), TRACK_LIKE_WIDTH, content.height())}
        x += TRACK_LIKE_WIDTH + gap
        result["marker"] = QRectF(x, content.top(), TRACK_MARKER_WIDTH, content.height())
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
        view = self.parent()
        liked = bool(
            isinstance(view, LikeAwareListWidget) and view.is_value_liked(raw)
        )
        like_hovered = bool(
            isinstance(view, LikeAwareListWidget)
            and view.is_index_like_hovered(index)
        )
        draw_track_like_icon(
            painter,
            rects["like"],
            liked=liked,
            hovered=like_hovered,
        )
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
        like_marker = QLabel("")
        like_marker.setFixedWidth(TRACK_LIKE_WIDTH)
        header_layout.addWidget(like_marker, 0, 0)
        marker = QLabel("")
        marker.setFixedWidth(TRACK_MARKER_WIDTH)
        header_layout.addWidget(marker, 0, 1)
        self.sort_buttons: dict[str, QPushButton] = {}
        for column, (label, field) in enumerate(
            (("歌曲标题", "title"), ("歌手", "artist"), ("专辑", "album")), start=2
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
        header_layout.addWidget(duration, 0, 5)

        self.empty_label = QLabel(empty_text)
        self.empty_label.setObjectName("listEmptyHint")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(180)
        self.empty_label.hide()

        self.list_widget = LikeAwareListWidget()
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

    def set_like_state_provider(self, provider) -> None:
        self.list_widget.set_like_state_provider(provider)

    def refresh_like_identity(self, identity: str) -> int:
        return self.list_widget.refresh_like_identity(identity)

    def scroll_to_top(self) -> None:
        self.list_widget.scrollToTop()
        QTimer.singleShot(0, self.list_widget.scrollToTop)

    def set_items(
        self,
        items: list[MediaItem | dict],
        empty_text: str = "没有找到歌曲",
        preserve_scroll: bool = False,
    ) -> None:
        selected_key = ""
        current = self.list_widget.currentItem()
        scroll_value = self.list_widget.verticalScrollBar().value()
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
        self.update_empty_state(empty_text)
        if selected_item is not None:
            self.list_widget.setCurrentItem(selected_item)
        if preserve_scroll:
            scroll_bar = self.list_widget.verticalScrollBar()

            def restore_scroll() -> None:
                scroll_bar.setValue(
                    max(scroll_bar.minimum(), min(scroll_value, scroll_bar.maximum()))
                )

            restore_scroll()
            QTimer.singleShot(0, restore_scroll)
        else:
            self.scroll_to_top()

    def update_empty_state(self, empty_text: str) -> None:
        has_items = self.list_widget.count() > 0
        self.list_widget.setVisible(has_items)
        self.empty_label.setText(empty_text)
        self.empty_label.setVisible(not has_items)
