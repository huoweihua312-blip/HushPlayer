"""Virtualized model for deterministic online search results."""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.ui_v2.models.online_track import OnlineTrack
from app.ui_v2.models.track import format_duration


class OnlineColumn(IntEnum):
    FAVORITE = 0
    TITLE = 1
    ARTIST = 2
    ALBUM = 3
    DURATION = 4
    SOURCE = 5
    QUALITY = 6
    STATUS = 7


ONLINE_TRACK_ROLE = int(Qt.ItemDataRole.UserRole) + 31
ONLINE_PLAYING_ROLE = ONLINE_TRACK_ROLE + 1


class OnlineTrackModel(QAbstractTableModel):
    HEADERS = ("收藏", "歌曲", "歌手", "专辑", "时长", "来源", "音质", "状态")

    def __init__(self, tracks: Iterable[OnlineTrack] = (), parent=None) -> None:
        super().__init__(parent)
        self._tracks = list(tracks)
        self._row_by_id = {track.id: row for row, track in enumerate(self._tracks)}
        self._playing_track_id = ""

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(OnlineColumn)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]
        column = OnlineColumn(index.column())
        if role == ONLINE_TRACK_ROLE:
            return track
        if role == ONLINE_PLAYING_ROLE:
            return track.id == self._playing_track_id
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(track, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_value(track, column)
        if role == Qt.ItemDataRole.TextAlignmentRole and column == OnlineColumn.DURATION:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section] if 0 <= section < len(self.HEADERS) else None
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        track = self._tracks[index.row()]
        flags = Qt.ItemFlag.ItemIsSelectable
        return flags | Qt.ItemFlag.ItemIsEnabled if track.availability == "available" else flags

    def track_at(self, row: int) -> OnlineTrack | None:
        return self._tracks[row] if 0 <= row < len(self._tracks) else None

    def tracks(self) -> tuple[OnlineTrack, ...]:
        return tuple(self._tracks)

    def set_tracks(self, tracks: Iterable[OnlineTrack]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self._row_by_id = {track.id: row for row, track in enumerate(self._tracks)}
        self.endResetModel()

    def update_track(self, updated: OnlineTrack) -> None:
        row = self._row_by_id.get(updated.id)
        if row is None:
            return
        self._tracks[row] = updated
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, self.columnCount() - 1),
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ToolTipRole,
                ONLINE_TRACK_ROLE,
                ONLINE_PLAYING_ROLE,
            ],
        )

    def set_playing_track(self, track_id: str) -> None:
        previous = self._playing_track_id
        if previous == track_id:
            return
        self._playing_track_id = track_id
        rows = {
            self._row_by_id[item_id]
            for item_id in (previous, track_id)
            if item_id in self._row_by_id
        }
        for row in rows:
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, self.columnCount() - 1),
                [ONLINE_PLAYING_ROLE],
            )

    @staticmethod
    def _display_value(track: OnlineTrack, column: OnlineColumn) -> str:
        values = {
            OnlineColumn.FAVORITE: "",
            OnlineColumn.TITLE: track.title,
            OnlineColumn.ARTIST: track.artist,
            OnlineColumn.ALBUM: track.album,
            OnlineColumn.DURATION: format_duration(track.duration_ms),
            OnlineColumn.SOURCE: track.source_name,
            OnlineColumn.QUALITY: track.quality,
            OnlineColumn.STATUS: "可用" if track.availability == "available" else "来源不可用",
        }
        return values[column]

    @staticmethod
    def _tooltip_value(track: OnlineTrack, column: OnlineColumn) -> str:
        if column == OnlineColumn.FAVORITE:
            return "取消收藏" if track.is_favorite else "添加到我喜欢"
        if column == OnlineColumn.TITLE:
            explicit = "\n显式内容" if track.explicit else ""
            return (
                f"{track.title}\n歌手: {track.artist}\n专辑: {track.album}\n"
                f"来源: {track.source_name}\n音质: {track.quality}{explicit}"
            )
        if column == OnlineColumn.SOURCE:
            return f"{track.source_name} ({track.source_id})"
        return OnlineTrackModel._display_value(track, column)
