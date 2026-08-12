"""Formal remote-track actions shared by the V2 discovery surface."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import QObject, Signal

from app.services.library_repository import LibraryRepository
from app.services.playlist_membership import PlaylistMembership
from app.services.remote_track_store import RemoteTrackStore


class OnlineDiscoveryBridge(QObject):
    """Persist remote discovery actions without owning a second data store."""

    REPLACED = "replaced"
    SOURCE_UPDATED = "source_updated"
    NOT_FOUND = "not_found"
    FAILED = "failed"

    action_succeeded = Signal(str, str)
    action_failed = Signal(str, str)

    def __init__(
        self,
        repository: LibraryRepository,
        remote_tracks: RemoteTrackStore,
        parent: QObject | None = None,
        *,
        source_url_resolver: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.remote_tracks = remote_tracks
        self._source_url_resolver = source_url_resolver

    @property
    def playlists_path(self) -> Path:
        return self.repository.playlists_file

    def persist_track(self, track: dict) -> tuple[str, dict]:
        payload = dict(track or {})
        source_id = str(payload.get("source_id") or payload.get("sourceId") or "").strip()
        source_url = str(payload.get("source_url") or payload.get("sourceUrl") or "").strip()
        if not source_url and self._source_url_resolver is not None:
            source_url = str(self._source_url_resolver(source_id) or "").strip()
        existing_tracks = self.remote_tracks.load_tracks()
        stable_id, record = RemoteTrackStore.build_record(
            payload,
            source_url,
            existing_tracks.get(RemoteTrackStore.stable_id_for_track(payload)),
        )
        if existing_tracks.get(stable_id) != record:
            updated = dict(existing_tracks)
            updated[stable_id] = record
            self.remote_tracks.save_tracks(updated)
        return stable_id, record

    def set_favorite(self, track: dict, liked: bool) -> bool:
        payload = dict(track or {})
        try:
            stable_id, _record = self.persist_track(payload)
            changed = self._set_member(
                "liked",
                PlaylistMembership.REMOTE,
                stable_id,
                bool(liked),
            )
        except Exception as error:
            self.action_failed.emit("favorite", str(error))
            return False
        message = "已收藏到“我喜欢”。" if liked else "已取消收藏该在线歌曲。"
        self.action_succeeded.emit("favorite", message)
        return True

    def add_to_playlist(self, track: dict, playlist_id: str) -> bool:
        payload = dict(track or {})
        target = str(playlist_id or "").strip()
        if not target:
            self.action_failed.emit("playlist", "目标歌单不存在。")
            return False
        try:
            stable_id, _record = self.persist_track(payload)
            changed = self._set_member(
                target,
                PlaylistMembership.REMOTE,
                stable_id,
                True,
            )
        except Exception as error:
            self.action_failed.emit("playlist", str(error))
            return False
        if not changed:
            self.action_succeeded.emit("playlist", "该歌曲已经在目标歌单中。")
            return True
        self.action_succeeded.emit("playlist", "在线歌曲已加入歌单。")
        return True

    def replace_track_memberships(
        self,
        old_member: tuple[str, str],
        replacement_track: dict,
    ) -> str:
        """Replace one track member in every playlist while preserving order."""

        old_key = self._normalize_member_key(old_member)
        if old_key is None or not isinstance(replacement_track, dict):
            return self.FAILED
        records = self.repository.load_playlist_records()
        if records.load_error:
            return self.FAILED
        playlists = deepcopy(records.playlists)
        has_membership = any(
            self._playlist_has_member(playlist, old_key)
            for playlist in playlists.values()
            if isinstance(playlist, dict)
        )
        remote_tracks_before = self.remote_tracks.load_tracks()
        has_remote_record = (
            old_key[0] == PlaylistMembership.REMOTE
            and old_key[1] in remote_tracks_before
        )
        if not has_membership and not has_remote_record:
            return self.NOT_FOUND

        try:
            stable_id, _record = self.persist_track(replacement_track)
            new_key = (PlaylistMembership.REMOTE, stable_id)
            if old_key[0] == PlaylistMembership.REMOTE and old_key[1] != stable_id:
                remote_tracks_after = self.remote_tracks.load_tracks()
                old_record = dict(remote_tracks_after.get(old_key[1], {}))
                if old_record:
                    old_record["replaced_by"] = stable_id
                    old_record["replaced_at"] = int(time.time())
                    remote_tracks_after[old_key[1]] = old_record
                    self.remote_tracks.save_tracks(remote_tracks_after)
            for playlist in playlists.values():
                if isinstance(playlist, dict):
                    self._replace_playlist_member(playlist, old_key, new_key)
            self._save_playlists(playlists)
        except Exception as error:
            try:
                self.remote_tracks.save_tracks(remote_tracks_before)
            except Exception:
                pass
            self.action_failed.emit("replace", str(error))
            return self.FAILED
        self.action_succeeded.emit("replace", "已将失效歌曲替换为在线版本。")
        return self.REPLACED

    def set_playback_source(
        self,
        old_member: tuple[str, str],
        replacement_track: dict,
    ) -> str:
        """Persist a new playback source without changing memberships.

        The original remote-track record remains the library and playlist
        identity.  The selected online source is stored as a nested override
        so playback can use it while favorites and playlist positions remain
        attached to the original record.
        """

        old_key = self._normalize_member_key(old_member)
        if (
            old_key is None
            or old_key[0] != PlaylistMembership.REMOTE
            or not isinstance(replacement_track, dict)
        ):
            return self.NOT_FOUND
        try:
            tracks_before = self.remote_tracks.load_tracks()
            old_record = tracks_before.get(old_key[1])
            if not isinstance(old_record, dict):
                return self.NOT_FOUND
            source_url = str(
                replacement_track.get("source_url")
                or replacement_track.get("sourceUrl")
                or ""
            ).strip()
            if not source_url and self._source_url_resolver is not None:
                source_url = str(
                    self._source_url_resolver(
                        str(
                            replacement_track.get("source_id")
                            or replacement_track.get("sourceId")
                            or ""
                        ).strip()
                    )
                    or ""
                ).strip()
            source_stable_id, source_record = RemoteTrackStore.build_record(
                replacement_track,
                source_url,
            )
            source_record["stable_id"] = source_stable_id
            source_record["source_name"] = str(
                replacement_track.get("source_name")
                or replacement_track.get("sourceName")
                or source_record.get("source_id")
                or ""
            ).strip()
            updated_record = dict(old_record)
            updated_record["playback_source"] = source_record
            # Records written by the previous membership-replacement flow can
            # be made visible again once the user selects a source-only fix.
            updated_record.pop("replaced_by", None)
            updated_record.pop("replaced_at", None)
            updated_tracks = dict(tracks_before)
            updated_tracks[old_key[1]] = updated_record
            self.remote_tracks.save_tracks(updated_tracks)
        except Exception as error:
            self.action_failed.emit("playback_source", str(error))
            return self.FAILED
        self.action_succeeded.emit("playback_source", "已更新在线播放来源。")
        return self.SOURCE_UPDATED

    def playlist_choices(self) -> tuple[tuple[str, str], ...]:
        records = self.repository.load_playlist_records()
        if records.load_error:
            return ()
        values: list[tuple[str, str]] = []
        for playlist_id, playlist in records.playlists.items():
            if not isinstance(playlist, dict) or playlist.get("fixed"):
                continue
            name = str(playlist.get("name") or "未命名歌单").strip()
            values.append((str(playlist_id), name or "未命名歌单"))
        return tuple(values)

    def create_playlist(
        self,
        playlist_id: str,
        name: str,
        description: str = "",
        created_at_ms: int | None = None,
    ) -> bool:
        """Create one ordinary playlist in the existing playlist document."""

        target = str(playlist_id or "").strip()
        title = str(name or "").strip()
        if not target or target == "liked" or not title:
            return False
        records = self.repository.load_playlist_records()
        if records.load_error or target in records.playlists:
            return False
        now_ms = max(0, int(created_at_ms or time.time() * 1000))
        records.playlists[target] = {
            "name": title,
            "description": str(description or "").strip(),
            "songs": [],
            "remoteSongs": [],
            "members": [],
            "membershipVersion": PlaylistMembership.VERSION,
            "fixed": False,
            "created_at": now_ms,
        }
        self._save_playlists(records.playlists)
        return True

    def rename_playlist(self, playlist_id: str, name: str) -> bool:
        """Rename an ordinary playlist while preserving its other fields."""

        target = str(playlist_id or "").strip()
        title = str(name or "").strip()
        if not target or target == "liked" or not title:
            return False
        records = self.repository.load_playlist_records()
        playlist = records.playlists.get(target)
        if records.load_error or not isinstance(playlist, dict) or playlist.get("fixed"):
            return False
        playlist["name"] = title
        self._save_playlists(records.playlists)
        return True

    def delete_playlist(self, playlist_id: str) -> bool:
        """Delete an ordinary playlist without touching any track document."""

        target = str(playlist_id or "").strip()
        if not target or target == "liked":
            return False
        records = self.repository.load_playlist_records()
        playlist = records.playlists.get(target)
        if records.load_error or not isinstance(playlist, dict) or playlist.get("fixed"):
            return False
        del records.playlists[target]
        self._save_playlists(records.playlists)
        return True

    def add_playlist_members(
        self,
        playlist_id: str,
        members: Iterable[tuple[str, str]],
    ) -> int:
        """Persist local or remote members through the shared membership contract."""

        return self._mutate_playlist_members(playlist_id, members, present=True)

    def remove_playlist_members(
        self,
        playlist_id: str,
        members: Iterable[tuple[str, str]],
    ) -> int:
        """Remove local or remote members without rewriting unknown fields."""

        return self._mutate_playlist_members(playlist_id, members, present=False)

    def _mutate_playlist_members(
        self,
        playlist_id: str,
        members: Iterable[tuple[str, str]],
        *,
        present: bool,
    ) -> int:
        target = str(playlist_id or "").strip()
        normalized = [
            {
                "kind": str(kind or "").strip(),
                "id": str(identifier or "").strip(),
            }
            for kind, identifier in members
            if str(kind or "").strip() and str(identifier or "").strip()
        ]
        if not target or not normalized:
            return 0
        records = self.repository.load_playlist_records()
        playlist = records.playlists.get(target)
        if records.load_error or not isinstance(playlist, dict):
            return 0
        if present:
            result = PlaylistMembership.add_members(
                playlist,
                normalized,
                LibraryRepository.normalize_song_path,
                assume_normalized=True,
            )
        else:
            result = PlaylistMembership.remove_members(
                playlist,
                normalized,
                LibraryRepository.normalize_song_path,
                assume_normalized=True,
            )
        changed = int(result.get("added", 0) or 0) if present else int(result.get("removed", 0) or 0)
        if changed:
            self._save_playlists(records.playlists)
        return changed

    def _set_member(
        self,
        playlist_id: str,
        kind: str,
        identifier: str,
        present: bool,
    ) -> bool:
        records = self.repository.load_playlist_records()
        if records.load_error:
            raise RuntimeError(records.load_error)
        playlists = records.playlists
        playlist = playlists.get(playlist_id)
        if not isinstance(playlist, dict):
            raise RuntimeError("目标歌单不存在。")
        member = (kind, str(identifier or "").strip())
        current = {
            (str(item.get("kind") or ""), str(item.get("id") or ""))
            for item in playlist.get("members", [])
            if isinstance(item, dict)
        }
        if (member in current) == bool(present):
            return False
        if present:
            result = PlaylistMembership.add_members(
                playlist,
                [member],
                LibraryRepository.normalize_song_path,
                assume_normalized=True,
            )
        else:
            result = PlaylistMembership.remove_members(
                playlist,
                [member],
                LibraryRepository.normalize_song_path,
                assume_normalized=True,
            )
        if not result.get("changed"):
            return False
        self._save_playlists(playlists)
        return True

    @classmethod
    def _normalize_member_key(cls, member) -> tuple[str, str] | None:
        if not isinstance(member, (tuple, list)) or len(member) < 2:
            return None
        kind = str(member[0] or "").strip().casefold()
        identifier = str(member[1] or "").strip()
        if kind == PlaylistMembership.LOCAL:
            identifier = LibraryRepository.normalize_song_path(identifier)
        if kind not in {PlaylistMembership.LOCAL, PlaylistMembership.REMOTE} or not identifier:
            return None
        return kind, identifier

    @staticmethod
    def _playlist_has_member(playlist: dict, key: tuple[str, str]) -> bool:
        return any(
            isinstance(member, dict)
            and (
                str(member.get("kind") or "").strip().casefold(),
                str(member.get("id") or "").strip(),
            )
            == key
            for member in playlist.get("members", ())
        )

    @classmethod
    def _replace_playlist_member(
        cls,
        playlist: dict,
        old_key: tuple[str, str],
        new_key: tuple[str, str],
    ) -> bool:
        members = [member for member in playlist.get("members", ()) if isinstance(member, dict)]
        old_indexes = [
            index
            for index, member in enumerate(members)
            if (
                str(member.get("kind") or "").strip().casefold(),
                str(member.get("id") or "").strip(),
            )
            == old_key
        ]
        if not old_indexes:
            return False
        if old_key == new_key:
            return True
        new_present = any(
            (
                str(member.get("kind") or "").strip().casefold(),
                str(member.get("id") or "").strip(),
            )
            == new_key
            for member in members
        )
        first_old_index = old_indexes[0]
        if not new_present:
            replacement = dict(members[first_old_index])
            replacement.update({"kind": new_key[0], "id": new_key[1]})
            members[first_old_index] = replacement
            for index in reversed(old_indexes[1:]):
                del members[index]
        else:
            members = [
                member
                for member in members
                if (
                    str(member.get("kind") or "").strip().casefold(),
                    str(member.get("id") or "").strip(),
                )
                != old_key
            ]
        playlist["members"] = members

        old_kind, old_id = old_key
        new_kind, new_id = new_key
        if old_kind == PlaylistMembership.LOCAL:
            playlist["songs"] = [
                value
                for value in playlist.get("songs", ())
                if LibraryRepository.normalize_song_path(value) != old_id
            ]
        else:
            playlist["remoteSongs"] = [
                value for value in playlist.get("remoteSongs", ()) if str(value) != old_id
            ]
        if new_key != old_key and not new_present:
            if new_kind == PlaylistMembership.REMOTE:
                remote_values = [str(value) for value in playlist.get("remoteSongs", ())]
                if new_id not in remote_values:
                    remote_before = sum(
                        1
                        for member in members[:first_old_index]
                        if str(member.get("kind") or "").strip().casefold()
                        == PlaylistMembership.REMOTE
                    )
                    remote_values.insert(min(remote_before, len(remote_values)), new_id)
                    playlist["remoteSongs"] = remote_values
            else:
                songs = list(playlist.get("songs", ()))
                if new_id not in songs:
                    songs.append(new_id)
                playlist["songs"] = songs
        return True

    def _save_playlists(self, playlists: dict) -> None:
        path = self.playlists_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(playlists, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
