"""音源绑定：谁是这首歌的「正式来源」，以及它被验证到什么程度。

设计原则（参见任务书）：

* ``tracks.source_id / source_name / remote_id / raw`` 是**唯一的权威身份**，
  任何写绑定的路径都必须改这几列，而不是另存一份 JSON。
* :class:`TrackBindingService` 只负责「怎么改」：事务、版本号（revision）、
  ``manual`` 锁、验证状态。它不猜歌曲，也不搜索。
* ``manual`` 表示用户亲手选的来源，自动回退永远不能覆盖它；``auto`` 表示
  导入匹配或自动回退选出来的来源，可以在真正播放成功后被晋升。
* 每次写入 revision +1。播放器拿着旧 revision 的异步回调必须被拒绝，
  这样「A 的 late callback 覆盖 B」在数据层就不可能发生。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..model.track import Track, album_key, artist_key

AUTO = "auto"
MANUAL = "manual"

PENDING = "pending"
VERIFIED = "verified"
FAILED = "failed"

_SELECTION_MODES = {AUTO, MANUAL}
_VERIFY_STATES = {PENDING, VERIFIED, FAILED}


@dataclass(frozen=True)
class BindingChoice:
    """一次来源选择需要写进 ``tracks`` 的字段。"""

    source_id: str
    source_name: str
    remote_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_ms: int = 0
    artwork_url: str = ""
    album_id: str = ""
    artist_id: str = ""
    raw: dict = field(default_factory=dict)

    def valid(self) -> bool:
        return bool(self.source_id and self.remote_id)

    @classmethod
    def from_track(cls, track: Track) -> "BindingChoice":
        return cls(
            source_id=track.source_id,
            source_name=track.source_name,
            remote_id=track.remote_id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_ms=int(track.duration_ms or 0),
            artwork_url=track.artwork_url,
            album_id=track.album_id
        or (album_key(track.album, track.album_artist or track.artist)
            if track.album else ""),
            artist_id=track.artist_id,
            raw=dict(track.raw or {}),
        )

    def as_update_kwargs(self) -> dict[str, Any]:
        names = [part for part in (self.artist or "").split() if part] if False else []
        del names  # artist_key 由 repository 统一按 split_artists 处理
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "remote_id": self.remote_id,
            "raw": dict(self.raw or {}),
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_ms": int(self.duration_ms or 0),
            "artwork_url": self.artwork_url,
            "album_id": self.album_id,
            "artist_id": self.artist_id or artist_key(self.artist or ""),
        }


@dataclass(frozen=True)
class BindingState:
    track_id: str
    selection_mode: str = AUTO
    verify_state: str = PENDING
    revision: int = 1
    origin_platform: str = ""
    origin_remote_id: str = ""
    verified_at: float = 0.0
    updated_at: float = 0.0

    @property
    def manual(self) -> bool:
        return self.selection_mode == MANUAL

    @property
    def verified(self) -> bool:
        return self.verify_state == VERIFIED


class TrackBindingService:
    """事务化的绑定写入器（不依赖 Qt，便于单测）。"""

    def __init__(self, library, on_change: Callable[[str], None] | None = None) -> None:
        self._library = library
        self._db = library.db
        self._tracks = library.tracks
        self._on_change = on_change

    # ------------------------------------------------------------- read
    def state(self, track_id: str) -> BindingState:
        row = self._db.connection().execute(
            """
            SELECT track_id, selection_mode, verify_state, revision,
                   origin_platform, origin_remote_id, verified_at, updated_at
            FROM track_source_binding_state WHERE track_id=?
            """,
            (track_id,),
        ).fetchone()
        if row is None:
            return BindingState(track_id=track_id)
        return BindingState(
            track_id=row[0],
            selection_mode=row[1],
            verify_state=row[2],
            revision=int(row[3] or 1),
            origin_platform=row[4] or "",
            origin_remote_id=row[5] or "",
            verified_at=float(row[6] or 0.0),
            updated_at=float(row[7] or 0.0),
        )

    def get_target(self, track_id: str) -> Track | None:
        return self._tracks.get(track_id)

    # ------------------------------------------------------------ write
    def commit_binding(
        self,
        track_id: str,
        choice: BindingChoice,
        *,
        mode: str,
        verify_state: str,
        expected_revision: int | None = None,
        origin: tuple[str, str] | None = None,
    ) -> bool:
        """原子地写入来源与状态；任一 guard 不满足则整笔放弃并返回 False。"""

        if mode not in _SELECTION_MODES:
            raise ValueError(f"未知 selection_mode: {mode!r}")
        if verify_state not in _VERIFY_STATES:
            raise ValueError(f"未知 verify_state: {verify_state!r}")
        if not choice.valid():
            return False

        now = time.time()
        with self._db.transaction() as tx:
            row = tx.execute(
                "SELECT selection_mode, revision, origin_platform, origin_remote_id "
                "FROM track_source_binding_state WHERE track_id=?",
                (track_id,),
            ).fetchone()
            current_mode = row[0] if row else AUTO
            revision = int(row[1]) if row else 0
            if expected_revision is not None and revision != int(expected_revision):
                return False
            # 手动锁定后，自动路径一律不得覆盖。
            if current_mode == MANUAL and mode == AUTO:
                return False

            updated = self._tracks.update_source_tx(
                tx, track_id, **choice.as_update_kwargs()
            )
            if not updated:
                return False

            if origin is not None:
                origin_platform, origin_remote_id = origin
            else:
                origin_platform = row[2] if row else ""
                origin_remote_id = row[3] if row else ""

            new_revision = revision + 1
            verified_at = now if verify_state == VERIFIED else 0.0
            tx.execute(
                """
                INSERT INTO track_source_binding_state(
                    track_id, selection_mode, verify_state, revision,
                    origin_platform, origin_remote_id, verified_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(track_id) DO UPDATE SET
                    selection_mode=excluded.selection_mode,
                    verify_state=excluded.verify_state,
                    revision=excluded.revision,
                    origin_platform=excluded.origin_platform,
                    origin_remote_id=excluded.origin_remote_id,
                    verified_at=excluded.verified_at,
                    updated_at=excluded.updated_at
                """,
                (
                    track_id,
                    mode,
                    verify_state,
                    new_revision,
                    origin_platform,
                    origin_remote_id,
                    verified_at,
                    now,
                ),
            )

        self._emit(track_id)
        return True

    def ensure_auto(
        self,
        track_id: str,
        *,
        origin_platform: str = "",
        origin_remote_id: str = "",
    ) -> BindingState:
        """给没有状态行的歌曲补一条 ``auto/pending``（幂等）。"""

        now = time.time()
        with self._db.transaction() as tx:
            tx.execute(
                """
                INSERT OR IGNORE INTO track_source_binding_state(
                    track_id, selection_mode, verify_state, revision,
                    origin_platform, origin_remote_id, verified_at, updated_at
                ) VALUES (?, 'auto', 'pending', 1, ?, ?, 0, ?)
                """,
                (track_id, origin_platform, origin_remote_id, now),
            )
        return self.state(track_id)

    def import_choice(
        self,
        track_id: str,
        choice: BindingChoice,
        *,
        origin: tuple[str, str] | None = None,
    ) -> bool:
        """导入时批量选出的候选：写来源但保持 ``pending``，不冒充已验证。"""

        return self.commit_binding(
            track_id,
            choice,
            mode=AUTO,
            verify_state=PENDING,
            origin=origin,
        )

    def manual_choose(
        self,
        track_id: str,
        choice: BindingChoice,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        """用户在 UI 里亲手选源：立即写入并锁定为 ``manual``。"""

        return self.commit_binding(
            track_id,
            choice,
            mode=MANUAL,
            verify_state=PENDING,
            expected_revision=expected_revision,
        )

    def mark_play_verified(
        self,
        track_id: str,
        *,
        expected_revision: int | None,
        choice: BindingChoice | None = None,
    ) -> bool:
        """真正播出声之后调用：``auto`` 可晋升来源，``manual`` 只更新验证状态。"""

        current = self.state(track_id)
        if expected_revision is not None and current.revision != int(expected_revision):
            return False
        if current.manual:
            return self._mark_state(
                track_id, verify_state=VERIFIED, expected_revision=current.revision
            )
        target = choice or BindingChoice.from_track(
            self.get_target(track_id) or Track(id=track_id)
        )
        return self.commit_binding(
            track_id,
            target,
            mode=AUTO,
            verify_state=VERIFIED,
            expected_revision=expected_revision,
        )

    def adopt_verified_fallback(
        self,
        track_id: str,
        choice: BindingChoice,
        *,
        expected_revision: int | None,
    ) -> bool:
        """跨源回退确认成功后，把这次真实播放的来源晋升为正式绑定。"""

        return self.commit_binding(
            track_id,
            choice,
            mode=AUTO,
            verify_state=VERIFIED,
            expected_revision=expected_revision,
        )

    def notify_updated(self, track_id: str) -> None:
        """广播“这首歌的来源/封面已变”，让列表、歌词页、播放栏一起刷新。"""
        try:
            self._library.track_updated.emit(str(track_id))
        except Exception:  # noqa: BLE001 - UI 刷新失败不影响播放
            pass

    def mark_failed(self, track_id: str, *, expected_revision: int | None) -> None:
        self._mark_state(
            track_id, verify_state=FAILED, expected_revision=expected_revision
        )

    # ----------------------------------------------------------- private
    def _mark_state(
        self,
        track_id: str,
        *,
        verify_state: str,
        expected_revision: int | None,
    ) -> bool:
        now = time.time()
        with self._db.transaction() as tx:
            row = tx.execute(
                "SELECT revision FROM track_source_binding_state WHERE track_id=?",
                (track_id,),
            ).fetchone()
            revision = int(row[0]) if row else 0
            if expected_revision is not None and revision != int(expected_revision):
                return False
            if row is None:
                tx.execute(
                    """
                    INSERT INTO track_source_binding_state(
                        track_id, selection_mode, verify_state, revision,
                        origin_platform, origin_remote_id, verified_at, updated_at
                    ) VALUES (?, 'auto', ?, 1, '', '', ?, ?)
                    """,
                    (track_id, verify_state, now if verify_state == VERIFIED else 0.0, now),
                )
            else:
                tx.execute(
                    """
                    UPDATE track_source_binding_state
                    SET verify_state=?, revision=revision+1, verified_at=?, updated_at=?
                    WHERE track_id=?
                    """,
                    (
                        verify_state,
                        now if verify_state == VERIFIED else 0.0,
                        now,
                        track_id,
                    ),
                )
        self._emit(track_id)
        return True

    def _emit(self, track_id: str) -> None:
        if self._on_change is not None:
            try:
                self._on_change(track_id)
            except Exception:  # noqa: BLE001 - 通知失败不能影响数据写入
                pass
