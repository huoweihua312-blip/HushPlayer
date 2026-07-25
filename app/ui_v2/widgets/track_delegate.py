"""Delegate painter for the V2 virtualized track table."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import PLAYING_ROLE, TRACK_ROLE, TrackColumn
from app.ui_v2.theme.icons import paint_icon
from app.ui_v2.theme.tokens import Theme


class RowVisualState(str, Enum):
    NORMAL = "normal"
    HOVER = "hover"
    SELECTED = "selected"
    PLAYING = "playing"
    SELECTED_PLAYING = "selected_playing"
    DISABLED = "disabled"


class TrackDelegate(QStyledItemDelegate):
    """Paint row states without allocating controls for individual tracks."""

    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme

    def sizeHint(self, option, index):  # noqa: N802
        hint = super().sizeHint(option, index)
        return hint.expandedTo(option.fontMetrics.size(0, 48))

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        track = index.data(TRACK_ROLE)
        if not isinstance(track, Track):
            return
        painter.save()
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        table = self.parent()
        is_row_hovered = getattr(table, "is_row_hovered", lambda _row: False)
        hovered = bool(is_row_hovered(index.row()))
        playing = bool(index.data(PLAYING_ROLE))
        colors = self._theme.colors
        state = self.row_visual_state(track, selected, hovered, playing)
        painter.fillRect(rect, self.background_color(state))
        painter.setPen(QPen(QColor(colors.border), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        column = TrackColumn(index.column())
        disabled = state == RowVisualState.DISABLED
        text_color = QColor(colors.disabled_text if disabled else colors.primary_text)
        secondary_color = QColor(colors.disabled_text if disabled else colors.secondary_text)
        icon_state = "disabled" if disabled else "selected" if playing else "hover" if hovered else "normal"
        content = rect.adjusted(10, 0, -10, 0)
        if (
            state in {RowVisualState.PLAYING, RowVisualState.SELECTED_PLAYING}
            and column == TrackColumn.FAVORITE
        ):
            painter.fillRect(
                QRectF(rect.left(), rect.top() + 6, 3, max(0, rect.height() - 12)),
                QColor(colors.accent),
            )
        if column == TrackColumn.FAVORITE:
            name = "favorite_filled" if track.is_favorite else "favorite"
            paint_icon(painter, name, self._icon_rect(content, 18), self._theme, "selected" if track.is_favorite else icon_state)
        elif column == TrackColumn.SOURCE:
            name = "online" if track.is_online else "local"
            icon_rect = QRectF(
                content.left(), content.center().y() - 8, 16, 16
            )
            paint_icon(painter, name, icon_rect, self._theme, icon_state)
            if content.width() >= 58:
                self._draw_text(
                    painter,
                    content.adjusted(22, 0, 0, 0),
                    track.source_name,
                    secondary_color,
                )
        elif column == TrackColumn.TITLE:
            left = content.left()
            if playing:
                marker = QRectF(left, content.center().y() - 8, 16, 16)
                paint_icon(painter, "playing", marker, self._theme, "selected")
                left += 22
            elif disabled:
                marker = QRectF(left, content.center().y() - 8, 16, 16)
                paint_icon(painter, "missing", marker, self._theme, "disabled")
                left += 22
            elif track.is_loading:
                self._draw_loading_indicator(painter, content)
                left += 20
            font = QFont(option.font)
            font.setWeight(QFont.Weight.DemiBold if playing else QFont.Weight.Normal)
            painter.setFont(font)
            title_color = QColor(colors.accent) if playing and not disabled else text_color
            self._draw_text(
                painter,
                QRectF(left, content.top(), content.right() - left, content.height()),
                track.title,
                title_color,
            )
        elif column == TrackColumn.DURATION:
            self._draw_text(painter, content, index.data(Qt.ItemDataRole.DisplayRole) or "", secondary_color, Qt.AlignmentFlag.AlignRight)
        else:
            self._draw_text(painter, content, index.data(Qt.ItemDataRole.DisplayRole) or "", secondary_color)
        painter.restore()

    @staticmethod
    def row_visual_state(
        track: Track,
        selected: bool,
        hovered: bool,
        playing: bool,
    ) -> RowVisualState:
        """Resolve row presentation in the documented, stable priority order."""
        if track.is_missing:
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

    def background_color(self, state: RowVisualState) -> QColor:
        colors = self._theme.colors
        values = {
            RowVisualState.NORMAL: colors.content_background,
            RowVisualState.HOVER: colors.hover_background,
            RowVisualState.SELECTED: colors.selected_background,
            RowVisualState.PLAYING: colors.playing_background,
            RowVisualState.SELECTED_PLAYING: colors.selected_background,
            RowVisualState.DISABLED: colors.content_background,
        }
        return QColor(values[state])

    @staticmethod
    def _icon_rect(rect: QRectF, size: int) -> QRectF:
        result = QRectF(rect.left(), rect.center().y() - size / 2, size, size)
        result.moveCenter(QRectF(rect).center())
        return result

    @staticmethod
    def _draw_text(
        painter: QPainter,
        rect: QRectF,
        text: str,
        color: QColor,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
    ) -> None:
        painter.setPen(color)
        metrics = painter.fontMetrics()
        available = max(0, int(rect.width()))
        elided = metrics.elidedText(str(text), Qt.TextElideMode.ElideRight, available)
        painter.drawText(rect, alignment | Qt.AlignmentFlag.AlignVCenter, elided)

    def _draw_loading_indicator(self, painter: QPainter, rect: QRectF) -> None:
        color = QColor(self._theme.colors.subtle_text)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        center_y = rect.center().y()
        for offset in (3, 9, 15):
            painter.drawEllipse(QRectF(rect.left() + offset, center_y - 2, 4, 4))
