from __future__ import annotations

import time
from collections.abc import Callable


class PlaylistMembership:
    """Compatibility layer for playlist membership metadata.

    ``songs`` and ``remoteSongs`` remain the membership source of truth for
    older HushPlayer versions.  ``members`` stores relationship-only metadata
    such as the time a local or remote track joined this particular playlist.
    """

    VERSION = 1
    LOCAL = "local"
    REMOTE = "remote"

    @classmethod
    def normalize_document(
        cls,
        playlists: dict,
        normalize_local: Callable[[str], str],
        anchor_ms: int | None = None,
    ) -> bool:
        if not isinstance(playlists, dict):
            return False
        changed = False
        for playlist in playlists.values():
            if isinstance(playlist, dict):
                changed = cls.normalize_playlist(
                    playlist,
                    normalize_local,
                    anchor_ms=anchor_ms,
                ) or changed
        return changed

    @classmethod
    def normalize_playlist(
        cls,
        playlist: dict,
        normalize_local: Callable[[str], str],
        anchor_ms: int | None = None,
    ) -> bool:
        if not isinstance(playlist, dict):
            return False

        original_songs = playlist.get("songs")
        original_remote = playlist.get("remoteSongs")
        songs, local_ids = cls._normalize_local_entries(
            original_songs,
            normalize_local,
        )
        remote_ids = cls._normalize_ids(
            original_remote,
            lambda value: str(value or "").strip(),
        )
        desired_keys = [
            *((cls.LOCAL, value) for value in local_ids),
            *((cls.REMOTE, value) for value in remote_ids),
        ]
        desired_key_set = set(desired_keys)

        existing: dict[tuple[str, str], int] = {}
        raw_members = playlist.get("members")
        if isinstance(raw_members, list):
            for member in raw_members:
                if not isinstance(member, dict):
                    continue
                kind = str(member.get("kind") or "").strip().casefold()
                identifier = str(member.get("id") or "").strip()
                if kind == cls.LOCAL:
                    identifier = normalize_local(identifier)
                if kind not in {cls.LOCAL, cls.REMOTE} or not identifier:
                    continue
                key = (kind, identifier)
                added_at = cls._positive_int(member.get("added_at"))
                if key in desired_key_set and added_at and key not in existing:
                    existing[key] = added_at

        now_ms = cls._positive_int(anchor_ms) or int(time.time() * 1000)
        if desired_keys and not existing:
            # Old arrays already have a user-visible order. Assign decreasing
            # values so the new newest-first default reproduces that order.
            base = max(now_ms, len(desired_keys) + 1)
            for index, key in enumerate(desired_keys):
                existing[key] = base - index
        else:
            next_added_at = max(
                now_ms,
                max(existing.values(), default=0) + 1,
            )
            for key in desired_keys:
                if key not in existing:
                    existing[key] = next_added_at
                    next_added_at += 1

        members = [
            {"kind": kind, "id": identifier, "added_at": existing[(kind, identifier)]}
            for kind, identifier in desired_keys
        ]
        changed = (
            original_songs != songs
            or original_remote != remote_ids
            or raw_members != members
            or playlist.get("membershipVersion") != cls.VERSION
        )
        playlist["songs"] = songs
        playlist["remoteSongs"] = remote_ids
        playlist["members"] = members
        playlist["membershipVersion"] = cls.VERSION
        return changed

    @classmethod
    def add_member(
        cls,
        playlist: dict,
        kind: str,
        identifier: str,
        normalize_local: Callable[[str], str],
        added_at: int | None = None,
    ) -> bool:
        cls.normalize_playlist(playlist, normalize_local)
        kind, identifier = cls._normalize_member(kind, identifier, normalize_local)
        if not identifier:
            return False
        target_key = "songs" if kind == cls.LOCAL else "remoteSongs"
        already_present = (
            any(normalize_local(value) == identifier for value in playlist[target_key])
            if kind == cls.LOCAL
            else identifier in playlist[target_key]
        )
        if already_present:
            return False
        playlist[target_key].append(identifier)
        timestamp = max(
            cls._positive_int(added_at) or int(time.time() * 1000),
            max(
                (cls._positive_int(member.get("added_at")) for member in playlist["members"]),
                default=0,
            )
            + 1,
        )
        playlist["members"].append(
            {"kind": kind, "id": identifier, "added_at": timestamp}
        )
        return True

    @classmethod
    def remove_member(
        cls,
        playlist: dict,
        kind: str,
        identifier: str,
        normalize_local: Callable[[str], str],
    ) -> bool:
        cls.normalize_playlist(playlist, normalize_local)
        kind, identifier = cls._normalize_member(kind, identifier, normalize_local)
        if not identifier:
            return False
        target_key = "songs" if kind == cls.LOCAL else "remoteSongs"
        already_present = (
            any(normalize_local(value) == identifier for value in playlist[target_key])
            if kind == cls.LOCAL
            else identifier in playlist[target_key]
        )
        if not already_present:
            return False
        if kind == cls.LOCAL:
            playlist[target_key] = [
                value
                for value in playlist[target_key]
                if normalize_local(value) != identifier
            ]
        else:
            playlist[target_key] = [
                value for value in playlist[target_key] if value != identifier
            ]
        playlist["members"] = [
            member
            for member in playlist["members"]
            if not (
                member.get("kind") == kind
                and str(member.get("id") or "") == identifier
            )
        ]
        return True

    @classmethod
    def added_at(
        cls,
        playlist: dict,
        kind: str,
        identifier: str,
        normalize_local: Callable[[str], str],
    ) -> int:
        cls.normalize_playlist(playlist, normalize_local)
        kind, identifier = cls._normalize_member(kind, identifier, normalize_local)
        for member in playlist.get("members", []):
            if (
                member.get("kind") == kind
                and str(member.get("id") or "") == identifier
            ):
                return cls._positive_int(member.get("added_at"))
        return 0

    @classmethod
    def signature(
        cls,
        playlist: dict,
        normalize_local: Callable[[str], str],
    ) -> tuple[tuple[str, str, int], ...]:
        cls.normalize_playlist(playlist, normalize_local)
        return tuple(
            (
                str(member.get("kind") or ""),
                str(member.get("id") or ""),
                cls._positive_int(member.get("added_at")),
            )
            for member in playlist.get("members", [])
            if isinstance(member, dict)
        )

    @classmethod
    def _normalize_member(
        cls,
        kind: str,
        identifier: str,
        normalize_local: Callable[[str], str],
    ) -> tuple[str, str]:
        kind = str(kind or "").strip().casefold()
        if kind not in {cls.LOCAL, cls.REMOTE}:
            return "", ""
        identifier = str(identifier or "").strip()
        if kind == cls.LOCAL:
            identifier = normalize_local(identifier)
        return kind, identifier

    @staticmethod
    def _normalize_ids(values, normalizer: Callable[[object], str]) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            identifier = str(normalizer(value) or "").strip()
            if identifier and identifier not in normalized:
                normalized.append(identifier)
        return normalized

    @staticmethod
    def _normalize_local_entries(
        values,
        normalize_local: Callable[[str], str],
    ) -> tuple[list[str], list[str]]:
        if not isinstance(values, list):
            return [], []
        stored_values: list[str] = []
        normalized_ids: list[str] = []
        for value in values:
            stored_value = str(value or "").strip()
            identifier = str(normalize_local(stored_value) or "").strip()
            if not identifier or identifier in normalized_ids:
                continue
            stored_values.append(stored_value)
            normalized_ids.append(identifier)
        return stored_values, normalized_ids

    @staticmethod
    def _positive_int(value) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0
