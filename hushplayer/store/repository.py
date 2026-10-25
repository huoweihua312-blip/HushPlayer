"""数据访问层：曲库、歌单、收藏、历史。"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ..core.logging_setup import get_logger
from ..model.track import Album, Artist, Playlist, Track, artist_key, normalize_path, split_artists
from .db import Database

log = get_logger("repository")

SORT_COLUMNS = {
    "title": "title COLLATE NOCASE",
    "artist": "artist COLLATE NOCASE",
    "album": "album COLLATE NOCASE",
    "duration": "duration_ms",
    "added": "added_at",
    "year": "year",
    "played": "play_count",
    "track_no": "track_no",
}

_TRACK_FIELDS = (
    "id", "kind", "title", "artist", "album", "album_artist", "duration_ms", "path",
    "source_id", "source_name", "remote_id", "artwork_url", "artwork_path", "track_no",
    "disc_no", "year", "genre", "bitrate", "sample_rate", "codec", "size", "added_at",
    "modified_at", "play_count", "last_played", "favorite", "favorited_at",
    "lyrics_offset_ms", "album_id", "artist_id", "raw",
)
_TRACK_COLUMNS = ", ".join(_TRACK_FIELDS)


def _track_columns(alias: str) -> str:
    return ", ".join(f"{alias}.{field}" for field in _TRACK_FIELDS)


@dataclass
class LibraryStats:
    track_count: int = 0
    online_count: int = 0
    album_count: int = 0
    artist_count: int = 0
    favorite_count: int = 0
    total_duration_ms: int = 0
    total_size: int = 0


class TrackRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ 写入
    def upsert_many(
        self, tracks: Sequence[Track], *, chunk: int = 400, return_counts: bool = False
    ):
        """批量写入。`return_counts=True` 时返回 (新增数, 更新数)。"""
        if not tracks:
            return (0, 0) if return_counts else 0
        written = 0
        ids = [track.id for track in tracks]
        existing: set[str] = set()
        conn = self.db.connection()
        try:
            for start in range(0, len(ids), 300):
                batch_ids = ids[start : start + 300]
                marks = ",".join("?" for _ in batch_ids)
                rows = conn.execute(
                    f"SELECT id FROM tracks WHERE id IN ({marks})", batch_ids
                ).fetchall()
                existing.update(row["id"] for row in rows)
        except sqlite3.Error:
            pass
        added = 0
        updated = 0
        with self.db.transaction() as tx:
            for start in range(0, len(tracks), chunk):
                batch = tracks[start : start + chunk]
                for track in batch:
                    self._upsert_one(tx, track)
                    if track.id in existing:
                        updated += 1
                    else:
                        added += 1
                written += len(batch)
        if return_counts:
            return added, updated
        return written

    def upsert(self, track: Track) -> None:
        with self.db.transaction() as tx:
            self._upsert_one(tx, track)

    def _upsert_one(self, tx: sqlite3.Connection, track: Track) -> None:
        tx.execute(
            """
            INSERT INTO tracks (
                id, kind, title, artist, album, album_artist, duration_ms, path, path_key,
                source_id, source_name, remote_id, artwork_url, artwork_path, track_no, disc_no,
                year, genre, bitrate, sample_rate, codec, size, added_at, modified_at,
                play_count, last_played, favorite, favorited_at, lyrics_offset_ms,
                album_id, artist_id, raw
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                kind=excluded.kind,
                title=excluded.title,
                artist=excluded.artist,
                album=excluded.album,
                album_artist=excluded.album_artist,
                duration_ms=excluded.duration_ms,
                path=excluded.path,
                path_key=excluded.path_key,
                source_id=excluded.source_id,
                source_name=excluded.source_name,
                remote_id=excluded.remote_id,
                artwork_url=CASE WHEN excluded.artwork_url != '' THEN excluded.artwork_url ELSE tracks.artwork_url END,
                artwork_path=CASE WHEN excluded.artwork_path != '' THEN excluded.artwork_path ELSE tracks.artwork_path END,
                track_no=excluded.track_no,
                disc_no=excluded.disc_no,
                year=excluded.year,
                genre=excluded.genre,
                bitrate=excluded.bitrate,
                sample_rate=excluded.sample_rate,
                codec=excluded.codec,
                size=excluded.size,
                modified_at=excluded.modified_at,
                album_id=excluded.album_id,
                artist_id=excluded.artist_id,
                raw=excluded.raw
            """,
            (
                track.id,
                track.kind,
                track.title,
                track.artist,
                track.album,
                track.album_artist,
                track.duration_ms,
                track.path,
                normalize_path(track.path) if track.path else "",
                track.source_id,
                track.source_name,
                track.remote_id,
                track.artwork_url,
                track.artwork_path,
                track.track_no,
                track.disc_no,
                track.year,
                track.genre,
                track.bitrate,
                track.sample_rate,
                track.codec,
                track.size,
                track.added_at or time.time(),
                track.modified_at,
                track.play_count,
                track.last_played,
                1 if track.favorite else 0,
                track.favorited_at,
                track.lyrics_offset_ms,
                track.album_id,
                track.artist_id,
                json.dumps(track.raw, ensure_ascii=False) if track.raw else "{}",
            ),
        )
        tx.execute("DELETE FROM track_artists WHERE track_id=?", (track.id,))
        names = split_artists(track.artist)
        for position, name in enumerate(names):
            tx.execute(
                "INSERT OR IGNORE INTO track_artists(track_id, artist_id, name, position) VALUES(?,?,?,?)",
                (track.id, artist_key(name), name, position),
            )

    def set_favorite(self, track_id: str, favorite: bool) -> None:
        self.db.connection().execute(
            "UPDATE tracks SET favorite=?, favorited_at=? WHERE id=?",
            (1 if favorite else 0, time.time() if favorite else 0, track_id),
        )

    def update_lyrics_offset(self, track_id: str, offset_ms: int) -> None:
        self.db.connection().execute(
            "UPDATE tracks SET lyrics_offset_ms=? WHERE id=?", (int(offset_ms), track_id)
        )

    def update_path(self, track_id: str, path: str, size: int = 0, modified: float = 0.0) -> None:
        self.db.connection().execute(
            "UPDATE tracks SET path=?, path_key=?, size=?, modified_at=? WHERE id=?",
            (path, normalize_path(path), size, modified, track_id),
        )

    def update_source(
        self,
        track_id: str,
        *,
        source_id: str,
        source_name: str,
        remote_id: str,
        raw: dict | None = None,
        title: str = "",
        artist: str = "",
        album: str = "",
        duration_ms: int = 0,
        artwork_url: str = "",
        album_id: str = "",
        artist_id: str = "",
    ) -> None:
        """只换「来源」相关字段，保留 ``id``，所以收藏/歌单/历史都不受影响。"""

        with self.db.transaction() as tx:
            self.update_source_tx(
                tx,
                track_id,
                source_id=source_id,
                source_name=source_name,
                remote_id=remote_id,
                raw=raw,
                title=title,
                artist=artist,
                album=album,
                duration_ms=duration_ms,
                artwork_url=artwork_url,
                album_id=album_id,
                artist_id=artist_id,
            )

    def update_source_tx(
        self,
        tx,
        track_id: str,
        *,
        source_id: str,
        source_name: str,
        remote_id: str,
        raw: dict | None = None,
        title: str = "",
        artist: str = "",
        album: str = "",
        duration_ms: int = 0,
        artwork_url: str = "",
        album_id: str = "",
        artist_id: str = "",
    ) -> bool:
        """在调用方事务里改来源；返回是否命中该行。

        与 :meth:`update_source` 的差别：``album_id`` 直接写入（允许空串清掉旧
        专辑关联），歌手关联按新的 ``artist`` 重建，避免跨源后仍挂着旧专辑/歌手。
        """

        payload = json.dumps(raw or {}, ensure_ascii=False)
        cursor = tx.execute(
            """
            UPDATE tracks SET
                source_id=?, source_name=?, remote_id=?, raw=?,
                title=COALESCE(NULLIF(?, ''), title),
                artist=COALESCE(NULLIF(?, ''), artist),
                album=COALESCE(NULLIF(?, ''), album),
                duration_ms=CASE WHEN ? > 0 THEN ? ELSE duration_ms END,
                artwork_url=COALESCE(NULLIF(?, ''), artwork_url),
                album_id=?,
                artist_id=?
            WHERE id=?
            """,
            (
                source_id,
                source_name,
                remote_id,
                payload,
                title,
                artist,
                album,
                int(duration_ms),
                int(duration_ms),
                artwork_url,
                album_id,
                artist_id,
                track_id,
            ),
        )
        if not cursor.rowcount:
            return False
        names = split_artists(artist or "")
        if names:
            tx.execute("DELETE FROM track_artists WHERE track_id=?", (track_id,))
            for position, name in enumerate(names):
                tx.execute(
                    "INSERT OR IGNORE INTO track_artists (track_id, artist_id, name, position) VALUES (?,?,?,?)",
                    (track_id, artist_key(name), name, position),
                )
        return True

    def delete(self, track_ids: Iterable[str]) -> int:
        ids = list(dict.fromkeys(track_ids))
        if not ids:
            return 0
        with self.db.transaction() as tx:
            for start in range(0, len(ids), 400):
                chunk = ids[start : start + 400]
                marks = ",".join("?" * len(chunk))
                tx.execute(f"DELETE FROM tracks WHERE id IN ({marks})", chunk)
                tx.execute(f"DELETE FROM track_artists WHERE track_id IN ({marks})", chunk)
                tx.execute(f"DELETE FROM playlist_items WHERE track_id IN ({marks})", chunk)
                tx.execute(f"DELETE FROM lyric_bindings WHERE track_id IN ({marks})", chunk)
        return len(ids)

    def delete_local_missing(
        self, existing_path_keys: set[str], roots: Sequence[str] | None = None
    ) -> int:
        """删除扫描目录下已不存在的本地曲目。

        `roots` 限定范围：只清理这些目录里的条目，避免误删单独导入的歌曲。
        """
        conn = self.db.connection()
        rows = conn.execute("SELECT id, path, path_key FROM tracks WHERE kind='local'").fetchall()
        prefixes = []
        if roots:
            prefixes = [normalize_path(str(root)) for root in roots if root]
        stale: list[str] = []
        for row in rows:
            path_key = row["path_key"]
            if not path_key or path_key in existing_path_keys:
                continue
            if prefixes:
                path = normalize_path(row["path"] or "")
                if not any(path.startswith(prefix) for prefix in prefixes):
                    continue
            stale.append(row["id"])
        if stale:
            self.delete(stale)
        return len(stale)

    # ------------------------------------------------------------------ 读取
    def get(self, track_id: str) -> Track | None:
        row = self.db.connection().execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE id=?", (track_id,)
        ).fetchone()
        return Track.from_row(row) if row else None

    def get_many(self, track_ids: Sequence[str]) -> list[Track]:
        if not track_ids:
            return []
        result: dict[str, Track] = {}
        conn = self.db.connection()
        ids = list(dict.fromkeys(track_ids))
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE id IN ({marks})", chunk
            ).fetchall()
            for row in rows:
                track = Track.from_row(row)
                result[track.id] = track
        return [result[item] for item in ids if item in result]

    def list(
        self,
        *,
        kind: str | None = None,
        search: str = "",
        sort: str = "title",
        descending: bool = False,
        favorite: bool | None = None,
        limit: int = -1,
        offset: int = 0,
    ) -> list[Track]:
        where, params = self._where(kind=kind, search=search, favorite=favorite)
        order = SORT_COLUMNS.get(sort, SORT_COLUMNS["title"])
        direction = "DESC" if descending else "ASC"
        sql = f"SELECT {_TRACK_COLUMNS} FROM tracks {where} ORDER BY {order} {direction}, title COLLATE NOCASE ASC"
        if limit > 0:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = self.db.connection().execute(sql, params).fetchall()
        return [Track.from_row(row) for row in rows]

    def count(self, *, kind: str | None = None, search: str = "", favorite: bool | None = None) -> int:
        where, params = self._where(kind=kind, search=search, favorite=favorite)
        row = self.db.connection().execute(f"SELECT COUNT(*) FROM tracks {where}", params).fetchone()
        return int(row[0]) if row else 0

    def _where(self, *, kind: str | None, search: str, favorite: bool | None) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        if favorite is not None:
            clauses.append("favorite=?")
            params.append(1 if favorite else 0)
        term = (search or "").strip()
        if term:
            like = f"%{term}%"
            clauses.append(
                "(title LIKE ? OR artist LIKE ? OR album LIKE ? OR album_artist LIKE ?)"
            )
            params.extend([like, like, like, like])
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    def search_local(self, term: str, limit: int = 60) -> list[Track]:
        term = (term or "").strip()
        if not term:
            return []
        like = f"%{term}%"
        prefix = f"{term}%"
        rows = self.db.connection().execute(
            f"""
            SELECT {_TRACK_COLUMNS} FROM tracks
            WHERE title LIKE ? OR artist LIKE ? OR album LIKE ?
            ORDER BY CASE
                WHEN title LIKE ? THEN 0
                WHEN artist LIKE ? THEN 1
                WHEN album LIKE ? THEN 2
                ELSE 3 END,
                play_count DESC, title COLLATE NOCASE
            LIMIT ?
            """,
            (like, like, like, prefix, prefix, prefix, int(limit)),
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def track_by_path(self, path: str) -> "Track | None":
        """Exact lookup used by playlist import (m3u/pls carry file paths)."""
        key = normalize_path(path)
        if not key:
            return None
        row = self.db.connection().execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE path_key=? AND kind='local' LIMIT 1",
            (key,),
        ).fetchone()
        return Track.from_row(row) if row else None

    def albums(self, *, search: str = "", limit: int = -1) -> list[Album]:
        # Favourited online tracks join the album view so saved streaming music
        # is browsable next to local files instead of only in 我喜欢.
        clauses = [
            "(kind='local' OR (kind='online' AND favorite=1))",
            "album_id != ''",
        ]
        params: list[Any] = []
        if search.strip():
            clauses.append("(album LIKE ? OR album_artist LIKE ?)")
            params.extend([f"%{search.strip()}%"] * 2)
        sql = f"""
            SELECT album_id AS id, album AS name, album_artist AS artist,
                   MAX(year) AS year, COUNT(*) AS track_count, SUM(duration_ms) AS duration_ms,
                   MIN(id) AS cover_track_id, MAX(artwork_path) AS artwork_path, MAX(genre) AS genre
            FROM tracks WHERE {' AND '.join(clauses)}
            GROUP BY album_id
            ORDER BY album COLLATE NOCASE
        """
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.connection().execute(sql, params).fetchall()
        return [
            Album(
                id=row["id"],
                name=row["name"],
                artist=row["artist"],
                year=int(row["year"] or 0),
                track_count=int(row["track_count"] or 0),
                duration_ms=int(row["duration_ms"] or 0),
                cover_track_id=row["cover_track_id"] or "",
                artwork_path=row["artwork_path"] or "",
                genre=row["genre"] or "",
            )
            for row in rows
        ]

    def artists(self, *, search: str = "", limit: int = -1) -> list[Artist]:
        clauses = ["(t.kind='local' OR (t.kind='online' AND t.favorite=1))"]
        params: list[Any] = []
        if search.strip():
            clauses.append("a.name LIKE ?")
            params.append(f"%{search.strip()}%")
        sql = f"""
            SELECT a.artist_id AS id, a.name AS name,
                   COUNT(DISTINCT t.id) AS track_count,
                   COUNT(DISTINCT t.album_id) AS album_count,
                   MIN(t.id) AS cover_track_id,
                   MAX(t.artwork_path) AS artwork_path
            FROM track_artists a JOIN tracks t ON t.id = a.track_id
            WHERE {' AND '.join(clauses)}
            GROUP BY a.artist_id
            ORDER BY a.name COLLATE NOCASE
        """
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.connection().execute(sql, params).fetchall()
        return [
            Artist(
                id=row["id"],
                name=row["name"],
                track_count=int(row["track_count"] or 0),
                album_count=int(row["album_count"] or 0),
                cover_track_id=row["cover_track_id"] or "",
                artwork_path=row["artwork_path"] or "",
            )
            for row in rows
        ]

    def album_tracks(self, album_id: str) -> list[Track]:
        rows = self.db.connection().execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE album_id=? ORDER BY disc_no, track_no, title COLLATE NOCASE",
            (album_id,),
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def artist_tracks(self, artist_id: str) -> list[Track]:
        rows = self.db.connection().execute(
            f"""
            SELECT {_TRACK_COLUMNS} FROM tracks
            WHERE id IN (SELECT track_id FROM track_artists WHERE artist_id=?)
            ORDER BY album COLLATE NOCASE, disc_no, track_no
            """,
            (artist_id,),
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def artist_albums(self, artist_id: str) -> list[Album]:
        rows = self.db.connection().execute(
            """
            SELECT t.album_id AS id, t.album AS name, t.album_artist AS artist, MAX(t.year) AS year,
                   COUNT(*) AS track_count, SUM(t.duration_ms) AS duration_ms,
                   MIN(t.id) AS cover_track_id, MAX(t.artwork_path) AS artwork_path, MAX(t.genre) AS genre
            FROM tracks t
            WHERE t.album_id IN (SELECT t2.album_id FROM tracks t2 JOIN track_artists a ON a.track_id=t2.id
                                 WHERE a.artist_id=? AND t2.album_id != '')
            GROUP BY t.album_id
            ORDER BY year DESC, name COLLATE NOCASE
            """,
            (artist_id,),
        ).fetchall()
        return [
            Album(
                id=row["id"],
                name=row["name"],
                artist=row["artist"],
                year=int(row["year"] or 0),
                track_count=int(row["track_count"] or 0),
                duration_ms=int(row["duration_ms"] or 0),
                cover_track_id=row["cover_track_id"] or "",
                artwork_path=row["artwork_path"] or "",
                genre=row["genre"] or "",
            )
            for row in rows
        ]

    def recent(self, limit: int = 40, *, days: int | None = None) -> list[Track]:
        params: list[Any] = []
        clause = ""
        if days:
            clause = "AND h.played_at > ?"
            params.append(time.time() - days * 86400)
        rows = self.db.connection().execute(
            f"""
            SELECT {_track_columns("t")} FROM tracks t
            JOIN (SELECT track_id, MAX(played_at) AS played_at FROM history
                  WHERE 1=1 {clause} GROUP BY track_id) h ON h.track_id = t.id
            ORDER BY h.played_at DESC LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def recently_added(self, limit: int = 20) -> list[Track]:
        rows = self.db.connection().execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE kind='local' ORDER BY added_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def most_played(self, limit: int = 20) -> list[Track]:
        rows = self.db.connection().execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE play_count > 0 ORDER BY play_count DESC, last_played DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def record_play(self, track_id: str, context: str = "") -> None:
        now = time.time()
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE tracks SET play_count = play_count + 1, last_played=? WHERE id=?", (now, track_id)
            )
            tx.execute(
                "INSERT INTO history(track_id, played_at, context) VALUES(?,?,?)", (track_id, now, context)
            )
            tx.execute(
                "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY played_at DESC LIMIT 5000)"
            )

    def favorites(self, limit: int = -1, offset: int = 0) -> list[Track]:
        sql = f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE favorite=1 ORDER BY favorited_at DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = self.db.connection().execute(sql).fetchall()
        return [Track.from_row(row) for row in rows]

    def stats(self) -> LibraryStats:
        conn = self.db.connection()
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN kind='online' THEN 1 ELSE 0 END) AS online,
                   SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) AS favorites,
                   SUM(duration_ms) AS duration,
                   SUM(size) AS size
            FROM tracks
            """
        ).fetchone()
        albums = conn.execute("SELECT COUNT(DISTINCT album_id) FROM tracks WHERE album_id != ''").fetchone()[0]
        artists = conn.execute("SELECT COUNT(DISTINCT artist_id) FROM track_artists").fetchone()[0]
        return LibraryStats(
            track_count=int(row["total"] or 0) - int(row["online"] or 0),
            online_count=int(row["online"] or 0),
            album_count=int(albums or 0),
            artist_count=int(artists or 0),
            favorite_count=int(row["favorites"] or 0),
            total_duration_ms=int(row["duration"] or 0),
            total_size=int(row["size"] or 0),
        )

    def paths_set(self) -> set[str]:
        rows = self.db.connection().execute("SELECT path_key FROM tracks WHERE kind='local'").fetchall()
        return {row[0] for row in rows if row[0]}

    def tracks_under(self, folder: str) -> list[Track]:
        folder_norm = normalize_path(folder).rstrip("\\/") + "\\"
        rows = self.db.connection().execute(
            f"SELECT {_TRACK_COLUMNS} FROM tracks WHERE kind='local' AND path_key LIKE ?",
            (folder_norm + "%",),
        ).fetchall()
        return [Track.from_row(row) for row in rows]


class PlaylistRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, name: str, description: str = "") -> Playlist:
        now = time.time()
        conn = self.db.connection()
        cursor = conn.execute(
            "INSERT INTO playlists(name, description, created_at, updated_at) VALUES(?,?,?,?)",
            (name.strip() or "新建歌单", description, now, now),
        )
        playlist_id = int(cursor.lastrowid)
        playlist = self.get(playlist_id)
        assert playlist is not None
        return playlist

    def get(self, playlist_id: int) -> Playlist | None:
        row = self.db.connection().execute(
            """
            SELECT p.*, (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id=p.id) AS track_count,
                   (SELECT COALESCE(SUM(t.duration_ms),0) FROM playlist_items i JOIN tracks t ON t.id=i.track_id
                    WHERE i.playlist_id=p.id) AS duration_ms,
                   (SELECT i.track_id FROM playlist_items i WHERE i.playlist_id=p.id
                    ORDER BY i.position LIMIT 1) AS first_track
            FROM playlists p WHERE p.id=?
            """,
            (playlist_id,),
        ).fetchone()
        return self._to_playlist(row) if row else None

    def list(self) -> list[Playlist]:
        rows = self.db.connection().execute(
            """
            SELECT p.*, (SELECT COUNT(*) FROM playlist_items i WHERE i.playlist_id=p.id) AS track_count,
                   (SELECT COALESCE(SUM(t.duration_ms),0) FROM playlist_items i JOIN tracks t ON t.id=i.track_id
                    WHERE i.playlist_id=p.id) AS duration_ms,
                   (SELECT i.track_id FROM playlist_items i WHERE i.playlist_id=p.id
                    ORDER BY i.position LIMIT 1) AS first_track
            FROM playlists p ORDER BY p.system DESC, p.created_at ASC
            """
        ).fetchall()
        return [self._to_playlist(row) for row in rows]

    def _to_playlist(self, row: sqlite3.Row) -> Playlist:
        return Playlist(
            id=int(row["id"]),
            name=row["name"],
            description=row["description"] or "",
            created_at=float(row["created_at"] or 0),
            updated_at=float(row["updated_at"] or 0),
            track_count=int(row["track_count"] or 0) if "track_count" in row.keys() else 0,
            duration_ms=int(row["duration_ms"] or 0) if "duration_ms" in row.keys() else 0,
            cover_track_id=(row["cover_track_id"] or row["first_track"] or "") if "first_track" in row.keys() else row["cover_track_id"],
            system=bool(row["system"]),
        )

    def rename(self, playlist_id: int, name: str) -> None:
        self.db.connection().execute(
            "UPDATE playlists SET name=?, updated_at=? WHERE id=?", (name.strip(), time.time(), playlist_id)
        )

    def update_description(self, playlist_id: int, description: str) -> None:
        self.db.connection().execute(
            "UPDATE playlists SET description=?, updated_at=? WHERE id=?",
            (description, time.time(), playlist_id),
        )

    def delete(self, playlist_id: int) -> None:
        with self.db.transaction() as tx:
            tx.execute("DELETE FROM playlist_items WHERE playlist_id=?", (playlist_id,))
            tx.execute("DELETE FROM playlists WHERE id=? AND system=0", (playlist_id,))

    def add_tracks(self, playlist_id: int, track_ids: Sequence[str]) -> int:
        if not track_ids:
            return 0
        now = time.time()
        added = 0
        with self.db.transaction() as tx:
            row = tx.execute(
                "SELECT COALESCE(MAX(position), -1) FROM playlist_items WHERE playlist_id=?", (playlist_id,)
            ).fetchone()
            position = int(row[0]) + 1
            for track_id in track_ids:
                exists = tx.execute(
                    "SELECT 1 FROM playlist_items WHERE playlist_id=? AND track_id=?", (playlist_id, track_id)
                ).fetchone()
                if exists:
                    continue
                tx.execute(
                    "INSERT INTO playlist_items(playlist_id, track_id, position, added_at) VALUES(?,?,?,?)",
                    (playlist_id, track_id, position, now),
                )
                position += 1
                added += 1
            tx.execute("UPDATE playlists SET updated_at=? WHERE id=?", (now, playlist_id))
        return added

    def remove_tracks(self, playlist_id: int, track_ids: Sequence[str]) -> int:
        if not track_ids:
            return 0
        removed = 0
        with self.db.transaction() as tx:
            for track_id in track_ids:
                cursor = tx.execute(
                    "DELETE FROM playlist_items WHERE playlist_id=? AND track_id=?", (playlist_id, track_id)
                )
                removed += cursor.rowcount
            self._compact(tx, playlist_id)
            tx.execute("UPDATE playlists SET updated_at=? WHERE id=?", (time.time(), playlist_id))
        return removed

    def _compact(self, tx: sqlite3.Connection, playlist_id: int) -> None:
        rows = tx.execute(
            "SELECT track_id FROM playlist_items WHERE playlist_id=? ORDER BY position", (playlist_id,)
        ).fetchall()
        for index, row in enumerate(rows):
            tx.execute(
                "UPDATE playlist_items SET position=? WHERE playlist_id=? AND track_id=?",
                (index, playlist_id, row["track_id"]),
            )

    def tracks(self, playlist_id: int, *, search: str = "") -> list[Track]:
        params: list[Any] = [playlist_id]
        clause = ""
        if search.strip():
            clause = "AND (t.title LIKE ? OR t.artist LIKE ? OR t.album LIKE ?)"
            like = f"%{search.strip()}%"
            params.extend([like, like, like])
        rows = self.db.connection().execute(
            f"""
            SELECT {_track_columns("t")} FROM tracks t
            JOIN playlist_items i ON i.track_id = t.id
            WHERE i.playlist_id=? {clause}
            ORDER BY i.position
            """,
            params,
        ).fetchall()
        return [Track.from_row(row) for row in rows]

    def move(self, playlist_id: int, from_index: int, to_index: int) -> None:
        with self.db.transaction() as tx:
            rows = tx.execute(
                "SELECT track_id FROM playlist_items WHERE playlist_id=? ORDER BY position", (playlist_id,)
            ).fetchall()
            ids = [row["track_id"] for row in rows]
            if not (0 <= from_index < len(ids)) or not (0 <= to_index < len(ids)) or from_index == to_index:
                return
            item = ids.pop(from_index)
            ids.insert(to_index, item)
            for index, track_id in enumerate(ids):
                tx.execute(
                    "UPDATE playlist_items SET position=? WHERE playlist_id=? AND track_id=?",
                    (index, playlist_id, track_id),
                )
            tx.execute("UPDATE playlists SET updated_at=? WHERE id=?", (time.time(), playlist_id))

    def set_cover(self, playlist_id: int, track_id: str) -> None:
        self.db.connection().execute(
            "UPDATE playlists SET cover_track_id=?, updated_at=? WHERE id=?",
            (track_id, time.time(), playlist_id),
        )

    def containing(self, track_id: str) -> list[int]:
        rows = self.db.connection().execute(
            "SELECT playlist_id FROM playlist_items WHERE track_id=?", (track_id,)
        ).fetchall()
        return [int(row[0]) for row in rows]


class LyricBindingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, track_id: str) -> tuple[str, str]:
        row = self.db.connection().execute(
            "SELECT path, source FROM lyric_bindings WHERE track_id=?", (track_id,)
        ).fetchone()
        return (row["path"], row["source"]) if row else ("", "")

    def set(self, track_id: str, path: str, source: str = "manual") -> None:
        self.db.connection().execute(
            "INSERT INTO lyric_bindings(track_id, path, source, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(track_id) DO UPDATE SET path=excluded.path, source=excluded.source, updated_at=excluded.updated_at",
            (track_id, path, source, time.time()),
        )

    def clear(self, track_id: str) -> None:
        self.db.connection().execute("DELETE FROM lyric_bindings WHERE track_id=?", (track_id,))


class MetaStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: str = "") -> str:
        row = self.db.connection().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.connection().execute(
            "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def record_scan_error(self, path: str, message: str) -> None:
        self.db.connection().execute(
            "INSERT INTO scan_errors(path, message, at) VALUES(?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET message=excluded.message, at=excluded.at",
            (path, message[:500], time.time()),
        )

    def scan_errors(self, limit: int = 100) -> list[tuple[str, str]]:
        rows = self.db.connection().execute(
            "SELECT path, message FROM scan_errors ORDER BY at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [(row["path"], row["message"]) for row in rows]

    def clear_scan_errors(self) -> None:
        self.db.connection().execute("DELETE FROM scan_errors")
