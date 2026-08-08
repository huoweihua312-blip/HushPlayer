"""A virtualized Qt model for the V2 song table."""

from __future__ import annotations

from enum import IntEnum
from collections.abc import Callable, Iterable
from weakref import WeakMethod

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.ui_v2.models.track import Track, format_duration


class TrackColumn(IntEnum):
    STATUS = 0
    TITLE = 1
    ARTIST = 2
    ALBUM = 3
    DURATION = 4
    FAVORITE = 5
    SOURCE = 6
    MORE = 7
    # Kept as a compatibility alias for the adapters' added-at sort key.
    # The visible column is now the trailing More action column.
    ADDED_AT = MORE


TRACK_ROLE = int(Qt.ItemDataRole.UserRole) + 1
PLAYING_ROLE = TRACK_ROLE + 1
PLAYBACK_ACTIVE_ROLE = TRACK_ROLE + 2


class TrackTableModel(QAbstractTableModel):
    """Stores track references only; views never allocate one widget per row."""

    HEADERS = ("#", "歌曲", "歌手", "专辑", "时长", "收藏", "来源", "")

    def __init__(
        self,
        tracks: Iterable[Track] = (),
        parent=None,
        *,
        meta_provider: Callable[[Track], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._tracks = list(tracks)
        self._row_by_id = {track.id: row for row, track in enumerate(self._tracks)}
        self._playing_track_id = ""
        self._playing_active = True
        self._meta_provider: Callable[[Track], str] | None = None
        self._meta_provider_ref = None
        self._header_overrides: dict[TrackColumn, str] = {}

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
        if role == PLAYBACK_ACTIVE_ROLE:
            return track.id == self._playing_track_id and self._playing_active
        if role == Qt.ItemDataRole.DisplayRole:
            if column == TrackColumn.SOURCE and self._has_meta_provider:
                return self._meta_text(track)
            return self._display_value(track, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_value(track, column)
        if role == Qt.ItemDataRole.TextAlignmentRole and column == TrackColumn.DURATION:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.HEADERS):
                column = TrackColumn(section)
                return self._header_overrides.get(column, self.HEADERS[section])
            return None
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

    def set_meta_provider(self, provider: Callable[[Track], str] | None) -> None:
        """Set optional page metadata without changing track ownership."""

        self._meta_provider = None
        self._meta_provider_ref = None
        if provider is not None:
            try:
                self._meta_provider_ref = WeakMethod(provider)
            except TypeError:
                self._meta_provider = provider
        self._header_overrides[TrackColumn.SOURCE] = "最近" if provider else "来源"
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            int(TrackColumn.SOURCE),
            int(TrackColumn.SOURCE),
        )

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
                PLAYBACK_ACTIVE_ROLE,
            ],
        )

    def set_playing_track(self, track_id: str) -> None:
        previous_id = self._playing_track_id
        if previous_id == track_id:
            return
        self._playing_track_id = track_id
        self._playing_active = True
        changed_rows = {self._row_by_id[item_id] for item_id in (previous_id, track_id) if item_id in self._row_by_id}
        for row in sorted(changed_rows):
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, self.columnCount() - 1),
                [
                    Qt.ItemDataRole.DisplayRole,
                    Qt.ItemDataRole.ToolTipRole,
                    PLAYING_ROLE,
                    PLAYBACK_ACTIVE_ROLE,
                ],
            )

    def set_playback_state(self, track_id: str, is_playing: bool) -> None:
        """Update paused/playing presentation without rebuilding the model."""

        normalized = str(track_id or "")
        active = bool(is_playing)
        if normalized == self._playing_track_id and active == self._playing_active:
            return
        previous_id = self._playing_track_id
        self._playing_track_id = normalized
        self._playing_active = active
        changed_rows = {
            self._row_by_id[item_id]
            for item_id in (previous_id, normalized)
            if item_id in self._row_by_id
        }
        for row in sorted(changed_rows):
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, self.columnCount() - 1),
                [PLAYING_ROLE, PLAYBACK_ACTIVE_ROLE],
            )

    @staticmethod
    def _display_value(track: Track, column: TrackColumn) -> str:
        from app.ui_v2.widgets.track_display import display_track_text

        title, artist, album = display_track_text(track)
        values = {
            TrackColumn.STATUS: "",
            TrackColumn.FAVORITE: "",
            TrackColumn.TITLE: title,
            TrackColumn.ARTIST: artist,
            TrackColumn.ALBUM: album,
            TrackColumn.DURATION: format_duration(track.duration_ms),
            TrackColumn.SOURCE: track.source_name,
            TrackColumn.MORE: "",
        }
        return values[column]

    def _tooltip_value(self, track: Track, column: TrackColumn) -> str:
        from app.ui_v2.widgets.track_display import display_track_text

        title, artist, album = display_track_text(track)
        if column in {TrackColumn.STATUS, TrackColumn.MORE}:
            return ""
        if column == TrackColumn.FAVORITE:
            return "取消收藏" if track.is_favorite else "添加到我喜欢"
        if column == TrackColumn.TITLE:
            added = TrackTableModel._safe_date(track.added_at, "%Y-%m-%d %H:%M")
            details = [
                title,
                f"歌手: {artist}",
                f"专辑: {album}",
                f"来源: {track.source_name}",
            ]
            if added:
                details.append(f"添加时间: {added}")
            return "\n".join(
                details
            )
        if column == TrackColumn.SOURCE:
            if self._has_meta_provider:
                return self._meta_text(track)
            return f"{track.source_name} ({'在线' if track.is_online else '本地'})"
        if column == TrackColumn.DURATION:
            return format_duration(track.duration_ms)
        if track.is_missing:
            return f"文件不可用: {TrackTableModel._display_value(track, column)}"
        return TrackTableModel._display_value(track, column)

    @staticmethod
    def _safe_date(value, pattern: str) -> str:
        """Hide missing/Unix-epoch placeholders from user-visible metadata."""

        if value is None or value.year <= 1970:
            return ""
        return value.strftime(pattern)

    @property
    def _has_meta_provider(self) -> bool:
        return self._meta_provider is not None or self._meta_provider_ref is not None

    def _meta_text(self, track: Track) -> str:
        provider = self._meta_provider
        if provider is None and self._meta_provider_ref is not None:
            provider = self._meta_provider_ref()
        return str(provider(track) or "") if provider is not None else ""
