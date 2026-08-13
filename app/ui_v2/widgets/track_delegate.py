"""Delegate painter for the V2 virtualized track table."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from app.ui_v2.models.track import Track
from app.ui_v2.models.track_table_model import (
    PLAYBACK_ACTIVE_ROLE,
    PLAYING_ROLE,
    TRACK_ROLE,
    TrackColumn,
)
from app.ui_v2.theme.icons import fluent_icon, paint_icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from app.ui_v2.widgets.track_display import present_track_identity


class RowVisualState(str, Enum):
    NORMAL = "normal"
    HOVER = "hover"
    SELECTED = "selected"
    PLAYING = "playing"
    PAUSED = "paused"
    SELECTED_PLAYING = "selected_playing"
    SELECTED_PAUSED = "selected_paused"
    DISABLED = "disabled"
    SELECTED_DISABLED = "selected_disabled"
    HOVER_DISABLED = "hover_disabled"
    CURRENT_PLAYING = "playing"
    CURRENT_PAUSED = "paused"


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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        table = self.parent()
        is_row_hovered = getattr(table, "is_row_hovered", lambda _row: False)
        hovered = bool(is_row_hovered(index.row()))
        playing = bool(index.data(PLAYING_ROLE))
        playback_active = bool(index.data(PLAYBACK_ACTIVE_ROLE))
        colors = self._theme.colors
        state = self.row_visual_state(track, selected, hovered, playing, playback_active)
        painter.fillRect(rect, self.background_color(state))

        column = TrackColumn(index.column())
        disabled = state in {
            RowVisualState.DISABLED,
            RowVisualState.SELECTED_DISABLED,
            RowVisualState.HOVER_DISABLED,
        }
        text_color = QColor(colors.disabled_text if disabled else colors.primary_text)
        secondary_color = QColor(colors.disabled_text if disabled else colors.secondary_text)
        icon_state = "disabled" if disabled else "selected" if playing else "hover" if hovered else "normal"
        identity = present_track_identity(track)
        content = rect.adjusted(10, 0, -10, 0)
        if selected and not playing and column == TrackColumn.STATUS:
            marker = QRectF(
                rect.left() + 4,
                rect.top() + 9,
                3,
                max(6, rect.height() - 18),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors.focus_ring))
            painter.drawRoundedRect(marker, 1.5, 1.5)
        if (
            state in {RowVisualState.PLAYING, RowVisualState.SELECTED_PLAYING}
            and column == TrackColumn.STATUS
        ):
            painter.fillRect(
                QRectF(rect.left(), rect.top() + 6, 2, max(0, rect.height() - 12)),
                QColor(colors.accent),
            )
        if column == TrackColumn.STATUS:
            if identity.availability.is_confirmed_error and not playing:
                paint_icon(painter, "missing", self._icon_rect(content, 17), self._theme, "disabled")
            elif identity.availability.is_resolving and not playing:
                self._draw_loading_indicator(painter, content)
            elif playing and playback_active:
                paint_icon(painter, "playing", self._icon_rect(content, 18), self._theme, "selected")
            elif playing:
                paint_icon(painter, "pause", self._icon_rect(content, 17), self._theme, "selected")
            elif hovered:
                paint_icon(painter, "play", self._icon_rect(content, 16), self._theme, "hover")
            else:
                self._draw_text(
                    painter,
                    content,
                    str(index.row() + 1),
                    secondary_color,
                    Qt.AlignmentFlag.AlignHCenter,
                )
        elif column == TrackColumn.FAVORITE:
            icon_rect = self._icon_rect(content, 18)
            if track.is_favorite:
                fluent_icon("favorite_filled", self._theme, "selected", size=18).paint(
                    painter, icon_rect.toRect()
                )
            else:
                paint_icon(painter, "favorite", icon_rect, self._theme, icon_state)
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
            artwork_size = min(36, max(32, int(rect.height() - 12)))
            artwork_rect = QRectF(content.left(), content.center().y() - artwork_size / 2, artwork_size, artwork_size)
            self._draw_artwork(painter, artwork_rect, track)
            if playing:
                marker = QRectF(artwork_rect.center().x() - 8, artwork_rect.center().y() - 8, 16, 16)
                paint_icon(painter, "playing", marker, self._theme, "selected")
            elif disabled:
                marker = QRectF(artwork_rect.center().x() - 8, artwork_rect.center().y() - 8, 16, 16)
                paint_icon(painter, "missing", marker, self._theme, "disabled")
            elif track.is_loading:
                self._draw_loading_indicator(painter, artwork_rect)
            left = artwork_rect.right() + 10
            font = QFont(option.font)
            font.setWeight(QFont.Weight.DemiBold if playing else QFont.Weight.Medium)
            painter.setFont(font)
            title_color = QColor(colors.accent) if playing and not disabled else text_color
            self._draw_text(
                painter,
                QRectF(left, content.top(), content.right() - left, content.height()),
                identity.title,
                title_color,
            )
        elif column == TrackColumn.DURATION:
            self._draw_text(painter, content, index.data(Qt.ItemDataRole.DisplayRole) or "", secondary_color, Qt.AlignmentFlag.AlignRight)
        elif column == TrackColumn.MORE:
            if hovered or selected or playing:
                if hovered:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(colors.surface_hover))
                    painter.drawEllipse(QRectF(content.center().x() - 15, content.center().y() - 15, 30, 30))
                paint_icon(painter, "more", self._icon_rect(content, 18), self._theme, icon_state)
        else:
            self._draw_text(painter, content, index.data(Qt.ItemDataRole.DisplayRole) or "", secondary_color)
        painter.restore()

    @staticmethod
    def row_visual_state(
        track: Track,
        selected: bool,
        hovered: bool,
        playing: bool,
        playback_active: bool = True,
    ) -> RowVisualState:
        """Resolve row presentation in the documented, stable priority order."""
        if track.is_missing and selected:
            return RowVisualState.SELECTED_DISABLED
        if track.is_missing and hovered:
            return RowVisualState.HOVER_DISABLED
        if track.is_missing:
            return RowVisualState.DISABLED
        if playing and not playback_active and selected:
            return RowVisualState.SELECTED_PAUSED
        if selected and playing:
            return RowVisualState.SELECTED_PLAYING
        if selected:
            return RowVisualState.SELECTED
        if playing and not playback_active:
            return RowVisualState.PAUSED
        if playing:
            return RowVisualState.PLAYING
        if hovered:
            return RowVisualState.HOVER
        return RowVisualState.NORMAL

    def background_color(self, state: RowVisualState) -> QColor:
        colors = self._theme.colors
        values = {
            RowVisualState.NORMAL: colors.surface_primary,
            RowVisualState.HOVER: colors.hover_background,
            RowVisualState.SELECTED: colors.selected_background,
            RowVisualState.PLAYING: self._playing_surface(),
            RowVisualState.PAUSED: self._paused_surface(),
            RowVisualState.SELECTED_PLAYING: colors.selected_background,
            RowVisualState.SELECTED_PAUSED: colors.selected_background,
            RowVisualState.DISABLED: colors.surface_primary,
            RowVisualState.SELECTED_DISABLED: colors.selected_background,
            RowVisualState.HOVER_DISABLED: colors.hover_background,
        }
        return QColor(values[state])

    def _playing_surface(self) -> QColor:
        """Use only a whisper of accent for the current row, never a purple block."""

        color = QColor(self._theme.colors.accent)
        color.setAlpha(4)
        return color

    def _paused_surface(self) -> QColor:
        color = QColor(self._theme.colors.surface_secondary)
        color.setAlpha(160)
        return color

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

    def _draw_artwork(self, painter: QPainter, rect: QRectF, track: Track) -> None:
        pixmap = artwork_pixmap_for_track(track, int(rect.width()), int(rect.height()))
        path = QPainterPath()
        path.addRoundedRect(rect, 5, 5)
        painter.save()
        painter.setClipPath(path)
        painter.drawPixmap(rect.toRect(), pixmap)
        painter.restore()
