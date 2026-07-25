"""A virtualized Qt model for the V2 song table."""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.ui_v2.models.track import Track, format_duration


class TrackColumn(IntEnum):
    FAVORITE = 0
    TITLE = 1
    ARTIST = 2
    ALBUM = 3
    DURATION = 4
    SOURCE = 5
    ADDED_AT = 6


TRACK_ROLE = int(Qt.ItemDataRole.UserRole) + 1
PLAYING_ROLE = TRACK_ROLE + 1


class TrackTableModel(QAbstractTableModel):
    """Stores track references only; views never allocate one widget per row."""

    HEADERS = ("收藏", "歌曲", "歌手", "专辑", "时长", "来源", "添加时间")

    def __init__(self, tracks: Iterable[Track] = (), parent=None) -> None:
        super().__init__(parent)
        self._tracks = list(tracks)
        self._row_by_id = {track.id: row for row, track in enumerate(self._tracks)}
        self._playing_track_id = ""

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(TrackColumn)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]
        column = TrackColumn(index.column())
        if role == TRACK_ROLE:
            return track
        if role == PLAYING_ROLE:
            return track.id == self._playing_track_id
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(track, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_value(track, column)
        if role == Qt.ItemDataRole.TextAlignmentRole and column == TrackColumn.DURATION:
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
        if track.is_missing:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def track_at(self, row: int) -> Track | None:
        return self._tracks[row] if 0 <= row < len(self._tracks) else None

    def tracks(self) -> tuple[Track, ...]:
        return tuple(self._tracks)

    def set_tracks(self, tracks: Iterable[Track]) -> None:
        self.beginResetModel()
        self._tracks = list(tracks)
        self._row_by_id = {track.id: row for row, track in enumerate(self._tracks)}
        self.endResetModel()

    def update_track(self, updated: Track) -> None:
        row = self._row_by_id.get(updated.id)
        if row is None:
            return
        self._tracks[row] = updated
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ToolTipRole,
                TRACK_ROLE,
                PLAYING_ROLE,
            ],
        )

    def set_playing_track(self, track_id: str) -> None:
        previous_id = self._playing_track_id
        if previous_id == track_id:
            return
        self._playing_track_id = track_id
        changed_rows = {self._row_by_id[item_id] for item_id in (previous_id, track_id) if item_id in self._row_by_id}
        for row in sorted(changed_rows):
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, self.columnCount() - 1),
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole, PLAYING_ROLE],
            )

    @staticmethod
    def _display_value(track: Track, column: TrackColumn) -> str:
        values = {
            TrackColumn.FAVORITE: "",
            TrackColumn.TITLE: track.title,
            TrackColumn.ARTIST: track.artist,
            TrackColumn.ALBUM: track.album,
            TrackColumn.DURATION: format_duration(track.duration_ms),
            TrackColumn.SOURCE: track.source_name,
            TrackColumn.ADDED_AT: track.added_at.strftime("%Y-%m-%d"),
        }
        return values[column]

    @staticmethod
    def _tooltip_value(track: Track, column: TrackColumn) -> str:
        if column == TrackColumn.FAVORITE:
            return "取消收藏" if track.is_favorite else "添加到我喜欢"
        if column == TrackColumn.TITLE:
            return "\n".join(
                (
                    track.title,
                    f"歌手: {track.artist}",
                    f"专辑: {track.album}",
                    f"来源: {track.source_name}",
                    f"添加时间: {track.added_at.strftime('%Y-%m-%d %H:%M')}",
                )
            )
        if column == TrackColumn.SOURCE:
            return f"{track.source_name} ({'在线' if track.is_online else '本地'})"
        if column == TrackColumn.DURATION:
            return format_duration(track.duration_ms)
        if column == TrackColumn.ADDED_AT:
            return track.added_at.strftime("%Y-%m-%d %H:%M")
        if track.is_missing:
            return f"文件不可用: {TrackTableModel._display_value(track, column)}"
        return TrackTableModel._display_value(track, column)
