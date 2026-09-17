"""Remove a library track and its related user records safely."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QFile

from app.services.library_repository import LibraryRepository
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore
from app.ui_v2.models.track import Track


@dataclass(frozen=True, slots=True)
class LibraryRemovalResult:
    success: bool
    message: str = ""
    file_trashed: bool = False
    cache_removed: bool = False


class LibraryRemovalService:
    """Keep the repository read-only while offering one explicit destructive action."""

    def __init__(
        self,
        repository: LibraryRepository,
        remote_tracks: RemoteTrackStore,
        *,
        online_audio_cache=None,
        file_to_trash: Callable[[Path], bool] | None = None,
    ) -> None:
        self.repository = repository
        self.remote_tracks = remote_tracks
        self.online_audio_cache = online_audio_cache
        self._file_to_trash = file_to_trash or self._move_to_trash

    def remove_track(self, track: Track) -> LibraryRemovalResult:
        if not isinstance(track, Track):
            return LibraryRemovalResult(False, "无法识别要删除的歌曲。")
        if track.is_online:
            return self._remove_online_track(track)
        return self._remove_local_track(track)

    def _remove_local_track(self, track: Track) -> LibraryRemovalResult:
        local_path = str(track.local_path or "").strip()
        if not local_path:
            return LibraryRemovalResult(False, "这首歌曲缺少本地文件路径。")
        normalized_path = LibraryRepository.normalize_song_path(local_path)
        library = self._load_library()
        if library is None:
            return LibraryRemovalResult(False, "读取音乐库失败，未删除任何文件。")
        playlists = self.repository.load_playlist_records()
        if playlists.load_error:
            return LibraryRemovalResult(False, playlists.load_error)
        stats = self._load_json_object(self.repository.stats_file)
        if stats is None:
            return LibraryRemovalResult(False, "读取播放统计失败，未删除任何文件。")

        remaining = [
            dict(record)
            for record in library
            if self._normalized_record_path(record) != normalized_path
        ]
        if len(remaining) == len(library):
            return LibraryRemovalResult(False, "音乐库中找不到这条歌曲记录。")

        stats_changed = normalized_path in stats
        stats.pop(normalized_path, None)
        playlists_changed = self._remove_playlist_members(
            playlists.playlists,
            (PlaylistMembership.LOCAL, normalized_path),
        )

        audio_path = Path(local_path)
        file_trashed = False
        if audio_path.is_file():
            if not self._file_to_trash(audio_path):
                return LibraryRemovalResult(
                    False,
                    "无法将本地文件移入回收站，音乐库记录未修改。",
                )
            file_trashed = True

        try:
            self._write_json(self.repository.library_file, remaining)
            if playlists_changed:
                self._write_json(self.repository.playlists_file, playlists.playlists)
            if stats_changed:
                self._write_json(self.repository.stats_file, stats)
        except Exception as error:
            return LibraryRemovalResult(
                False,
                f"文件已移入回收站，但音乐库记录清理失败：{error}",
                file_trashed=file_trashed,
            )
        return LibraryRemovalResult(
            True,
            "歌曲已从音乐库删除，本地文件已移入回收站。"
            if file_trashed
            else "歌曲已从音乐库删除。",
            file_trashed=file_trashed,
        )

    def _remove_online_track(self, track: Track) -> LibraryRemovalResult:
        stable_id = str(track.stable_identity or track.remote_identity or track.id).strip()
        if not stable_id:
            return LibraryRemovalResult(False, "这首在线歌曲缺少稳定标识。")
        try:
            remote_tracks = self.remote_tracks.load_tracks()
        except Exception as error:
            return LibraryRemovalResult(False, f"读取在线歌曲记录失败：{error}")
        record = remote_tracks.get(stable_id)
        if not isinstance(record, dict):
            return LibraryRemovalResult(False, "在线歌曲记录已经不存在。")
        playlists = self.repository.load_playlist_records()
        if playlists.load_error:
            return LibraryRemovalResult(False, playlists.load_error)

        cache_removed = False
        if self.online_audio_cache is not None:
            try:
                cache_result = self.online_audio_cache.delete_cache(
                    self._cache_payload(track)
                )
                cache_removed = bool(cache_result.get("removed"))
            except Exception as error:
                return LibraryRemovalResult(
                    False,
                    f"删除在线音频缓存失败：{error}",
                )

        file_trashed = False
        local_path = str(record.get("local_path") or "").strip()
        if local_path:
            local_file = Path(local_path)
            if local_file.is_file():
                if not self._file_to_trash(local_file):
                    return LibraryRemovalResult(
                        False,
                        "无法将在线歌曲的本地文件移入回收站，记录未修改。",
                        cache_removed=cache_removed,
                    )
                file_trashed = True

        playlists_changed = self._remove_playlist_members(
            playlists.playlists,
            (PlaylistMembership.REMOTE, stable_id),
        )
        updated_tracks = dict(remote_tracks)
        updated_tracks.pop(stable_id, None)
        try:
            self.remote_tracks.save_tracks(updated_tracks)
            if playlists_changed:
                self._write_json(self.repository.playlists_file, playlists.playlists)
        except Exception as error:
            return LibraryRemovalResult(
                False,
                f"在线歌曲记录删除失败：{error}",
                file_trashed=file_trashed,
                cache_removed=cache_removed,
            )
        return LibraryRemovalResult(
            True,
            "在线歌曲及本地音频缓存已删除。",
            file_trashed=file_trashed,
            cache_removed=cache_removed,
        )

    def _load_library(self) -> list[dict] | None:
        try:
            document = json.loads(
                self.repository.library_file.read_text(encoding="utf-8")
            )
        except Exception:
            return None
        if not isinstance(document, list):
            return None
        return [dict(record) for record in document if isinstance(record, dict)]

    @staticmethod
    def _load_json_object(path: Path) -> dict | None:
        if not path.exists():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return dict(document) if isinstance(document, dict) else None

    @staticmethod
    def _normalized_record_path(record: dict) -> str:
        return LibraryRepository.normalize_song_path(str(record.get("path") or ""))

    @staticmethod
    def _remove_playlist_members(
        playlists: dict,
        member: tuple[str, str],
    ) -> bool:
        changed = False
        for playlist in playlists.values():
            if not isinstance(playlist, dict):
                continue
            result = PlaylistMembership.remove_members(
                playlist,
                (member,),
                LibraryRepository.normalize_song_path,
                assume_normalized=True,
            )
            changed = bool(result.get("changed")) or changed
        return changed

    @staticmethod
    def _cache_payload(track: Track) -> dict:
        payload = (
            dict(track.remote_payload)
            if isinstance(track.remote_payload, dict)
            else {}
        )
        playback_source = payload.get("playback_source")
        playback_source = (
            playback_source if isinstance(playback_source, dict) else {}
        )
        source_id = str(
            playback_source.get("source_id")
            or playback_source.get("sourceId")
            or track.source_id
            or ""
        ).strip()
        track_id = str(
            playback_source.get("remote_id")
            or playback_source.get("remoteId")
            or playback_source.get("id")
            or track.remote_track_id
            or track.remote_identity
            or track.id
            or ""
        ).strip()
        payload.update(
            {
                "media_type": "online",
                "source_id": source_id,
                "sourceId": source_id,
                "id": track_id,
                "remote_id": track_id,
                "remote_stable_id": track.stable_identity,
                "quality": str(
                    playback_source.get("quality")
                    or payload.get("quality")
                    or "default"
                ).strip()
                or "default",
            }
        )
        return payload

    @staticmethod
    def _move_to_trash(path: Path) -> bool:
        return bool(QFile.moveToTrash(str(path)))

    @staticmethod
    def _write_json(path: Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
