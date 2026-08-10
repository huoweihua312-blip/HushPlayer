"""Artist aggregation and filtering derived from the shared Track collection."""

from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.models.artist import Artist


UNKNOWN_ARTIST = "未知歌手"
UNKNOWN_ALBUM = "未知专辑"


class ArtistsAdapter(QObject):
    """Aggregates artists by normalized name without retaining Track copies."""

    artists_reset = Signal(object)
    query_changed = Signal(str)

    def __init__(self, collection: LibraryCollectionAdapter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.collection = collection
        self._query = ""
        self._artists: tuple[Artist, ...] = ()
        collection.tracks_changed.connect(self._rebuild)
        self._rebuild(emit=False)

    @property
    def query(self) -> str:
        return self._query

    def artists(self) -> tuple[Artist, ...]:
        return self._artists

    def artist_for_id(self, artist_id: str) -> Artist | None:
        return next((artist for artist in self._artists if artist.id == artist_id), None)

    def tracks_for_artist(self, artist_id: str):
        artist = self.artist_for_id(artist_id)
        return self.collection.tracks_for_ids(artist.track_ids if artist else ())

    def set_query(self, text: str) -> None:
        query = str(text or "").strip()
        if query == self._query:
            return
        self._query = query
        self._rebuild()
        self.query_changed.emit(query)

    def _rebuild(self, emit: bool = True) -> None:
        grouped: dict[str, list[str]] = defaultdict(list)
        albums: dict[str, set[str]] = defaultdict(set)
        duration: dict[str, int] = defaultdict(int)
        names: dict[str, str] = {}
        for track in self.collection.tracks():
            name = normalize_artist(track.artist)
            artist_id = artist_identity(name)
            grouped[artist_id].append(track.id)
            albums[artist_id].add(album_identity(normalize_album(track.album), name))
            duration[artist_id] += track.duration_ms or 0
            names[artist_id] = name
        query = self._query.casefold()
        self._artists = tuple(
            artist
            for artist in sorted(
                (
                    Artist(
                        id=artist_id,
                        name=names[artist_id],
                        track_ids=tuple(track_ids),
                        album_ids=tuple(sorted(albums[artist_id])),
                        total_duration_ms=duration[artist_id],
                    )
                    for artist_id, track_ids in grouped.items()
                ),
                key=lambda item: item.name.casefold(),
            )
            if not query or query in artist.name.casefold()
        )
        if emit:
            self.artists_reset.emit(self._artists)


def normalize_artist(value: str) -> str:
    return str(value or "").strip() or UNKNOWN_ARTIST


def normalize_album(value: str) -> str:
    return str(value or "").strip() or UNKNOWN_ALBUM


def artist_identity(name: str) -> str:
    return f"artist:{name.casefold()}"


def album_identity(title: str, artist: str) -> str:
    return f"album:{artist.casefold()}::{title.casefold()}"
