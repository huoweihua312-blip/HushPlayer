"""Album aggregation with an artist-qualified key to prevent false merges."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.artists_adapter import (
    album_identity,
    normalize_album,
    normalize_artist,
)
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.models.album import Album


class AlbumsAdapter(QObject):
    """Aggregates albums by album title plus artist identity."""

    albums_reset = Signal(object)
    query_changed = Signal(str)

    def __init__(self, collection: LibraryCollectionAdapter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.collection = collection
        self._query = ""
        self._albums: tuple[Album, ...] = ()
        collection.tracks_changed.connect(self._rebuild)
        self._rebuild(emit=False)

    @property
    def query(self) -> str:
        return self._query

    def albums(self) -> tuple[Album, ...]:
        return self._albums

    def album_for_id(self, album_id: str) -> Album | None:
        return next((album for album in self._albums if album.id == album_id), None)

    def tracks_for_album(self, album_id: str):
        album = self.album_for_id(album_id)
        return self.collection.tracks_for_ids(album.track_ids if album else ())

    def set_query(self, text: str) -> None:
        query = str(text or "").strip()
        if query == self._query:
            return
        self._query = query
        self._rebuild()
        self.query_changed.emit(query)

    def _rebuild(self, emit: bool = True) -> None:
        grouped: dict[str, list[str]] = defaultdict(list)
        duration: dict[str, int] = defaultdict(int)
        labels: dict[str, tuple[str, str]] = {}
        for track in self.collection.tracks():
            artist = normalize_artist(track.artist)
            title = normalize_album(track.album)
            album_id = album_identity(title, artist)
            grouped[album_id].append(track.id)
            duration[album_id] += track.duration_ms or 0
            labels[album_id] = (title, artist)
        query = self._query.casefold()
        self._albums = tuple(
            album
            for album in sorted(
                (
                    Album(
                        id=album_id,
                        title=labels[album_id][0],
                        artist=labels[album_id][1],
                        track_ids=tuple(track_ids),
                        total_duration_ms=duration[album_id],
                    )
                    for album_id, track_ids in grouped.items()
                ),
                key=lambda item: (item.title.casefold(), item.artist.casefold()),
            )
            if not query
            or query in album.title.casefold()
            or query in album.artist.casefold()
        )
        if emit:
            self.albums_reset.emit(self._albums)
