"""SQLite 连接与表结构。

设计：
* 单文件数据库，WAL 模式，按线程持有连接（扫描线程与 UI 线程互不阻塞）。
* 所有用户资产（曲库、收藏、歌单、播放历史）与可重建缓存分离：
  缓存目录删除不会影响这里的数据。
* 通过 ``PRAGMA user_version`` 做向前兼容的增量迁移。
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..core import paths
from ..core.logging_setup import get_logger

log = get_logger("db")

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'local',
    title TEXT NOT NULL DEFAULT '',
    artist TEXT NOT NULL DEFAULT '',
    album TEXT NOT NULL DEFAULT '',
    album_artist TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    path TEXT NOT NULL DEFAULT '',
    path_key TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    remote_id TEXT NOT NULL DEFAULT '',
    artwork_url TEXT NOT NULL DEFAULT '',
    artwork_path TEXT NOT NULL DEFAULT '',
    track_no INTEGER NOT NULL DEFAULT 0,
    disc_no INTEGER NOT NULL DEFAULT 0,
    year INTEGER NOT NULL DEFAULT 0,
    genre TEXT NOT NULL DEFAULT '',
    bitrate INTEGER NOT NULL DEFAULT 0,
    sample_rate INTEGER NOT NULL DEFAULT 0,
    codec TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    added_at REAL NOT NULL DEFAULT 0,
    modified_at REAL NOT NULL DEFAULT 0,
    play_count INTEGER NOT NULL DEFAULT 0,
    last_played REAL NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    favorited_at REAL NOT NULL DEFAULT 0,
    lyrics_offset_ms INTEGER NOT NULL DEFAULT 0,
    album_id TEXT NOT NULL DEFAULT '',
    artist_id TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tracks_path ON tracks(path_key);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_kind ON tracks(kind);
CREATE INDEX IF NOT EXISTS idx_tracks_favorite ON tracks(favorite, favorited_at);
CREATE INDEX IF NOT EXISTS idx_tracks_last_played ON tracks(last_played);
CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS track_artists (
    track_id TEXT NOT NULL,
    artist_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (track_id, artist_id)
);
CREATE INDEX IF NOT EXISTS idx_track_artists_artist ON track_artists(artist_id);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    cover_track_id TEXT NOT NULL DEFAULT '',
    system INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id INTEGER NOT NULL,
    track_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    added_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (playlist_id, track_id)
);
CREATE INDEX IF NOT EXISTS idx_playlist_items_pos ON playlist_items(playlist_id, position);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    played_at REAL NOT NULL DEFAULT 0,
    context TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_history_time ON history(played_at DESC);

CREATE TABLE IF NOT EXISTS lyric_bindings (
    track_id TEXT PRIMARY KEY,
    path TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_errors (
    path TEXT PRIMARY KEY,
    message TEXT NOT NULL DEFAULT '',
    at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- 音源绑定状态：tracks.{source_id,source_name,remote_id,raw} 是权威身份，
-- 这张表只保存「谁选的」「验证到哪一步」「第几版」。
CREATE TABLE IF NOT EXISTS track_source_binding_state (
    track_id TEXT PRIMARY KEY,
    selection_mode TEXT NOT NULL DEFAULT 'auto' CHECK (selection_mode IN ('auto', 'manual')),
    verify_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (verify_state IN ('pending', 'verified', 'failed')),
    revision INTEGER NOT NULL DEFAULT 1,
    origin_platform TEXT NOT NULL DEFAULT '',
    origin_remote_id TEXT NOT NULL DEFAULT '',
    verified_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_binding_verify ON track_source_binding_state(verify_state);
"""


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else paths.database_file()
        self._local = threading.local()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    # ------------------------------------------------------------------ 连接
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=15.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=8000")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def initialize(self) -> None:
        with self._lock:
            conn = self.connection()
            conn.executescript(_SCHEMA)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                self._migrate(conn, version)
                conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self._ensure_system_playlists(conn)

    def _migrate(self, conn: sqlite3.Connection, from_version: int) -> None:
        log.info("数据库迁移: %s -> %s", from_version, SCHEMA_VERSION)
        if from_version < 2:
            # v2：音源绑定状态表。`_SCHEMA` 的 CREATE TABLE IF NOT EXISTS 已经
            # 覆盖升级，这里只给已有在线曲目补一行，让「无状态行」也有确定语义。
            now = _now()
            conn.execute(
                """
                INSERT OR IGNORE INTO track_source_binding_state(
                    track_id, selection_mode, verify_state, revision,
                    origin_platform, origin_remote_id, verified_at, updated_at
                )
                SELECT id, 'auto', 'pending', 1, source_id, remote_id, 0, ?
                FROM tracks WHERE kind='online' AND source_id != ''
                """,
                (now,),
            )

    def _ensure_system_playlists(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT id FROM playlists WHERE system=1 AND name='我喜欢'").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO playlists(name, description, created_at, updated_at, system) VALUES(?,?,?,?,1)",
                ("我喜欢", "收藏的歌曲", _now(), _now()),
            )

    def close_current_thread(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None

    def vacuum(self) -> None:
        self.connection().execute("VACUUM")

    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


def _now() -> float:
    import time

    return time.time()
