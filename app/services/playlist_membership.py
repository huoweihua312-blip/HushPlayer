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
    def add_members(
        cls,
        playlist: dict,
        members,
        normalize_local: Callable[[str], str],
    ) -> dict:
        """Add one normalized input batch without repeatedly scanning a playlist."""
        raw_members = list(members or [])
        result = cls._batch_result(len(raw_members))
        if not raw_members:
            return result

        cached_normalize_local = cls._cached_normalizer(normalize_local)
        result["normalized_changed"] = cls.normalize_playlist(
            playlist,
            cached_normalize_local,
        )

        existing_keys: set[tuple[str, str]] = set()
        max_added_at = 0
        existing_local_members: list[dict] = []
        existing_remote_members: list[dict] = []
        for member in playlist["members"]:
            kind = str(member.get("kind") or "")
            key = (kind, str(member.get("id") or ""))
            existing_keys.add(key)
            max_added_at = max(
                max_added_at,
                cls._positive_int(member.get("added_at")),
            )
            if kind == cls.LOCAL:
                existing_local_members.append(member)
            else:
                existing_remote_members.append(member)

        input_keys: set[tuple[str, str]] = set()
        new_local_members: list[dict] = []
        new_remote_members: list[dict] = []
        for raw_member in raw_members:
            kind, identifier, requested_added_at = cls._normalize_member_input(
                raw_member,
                cached_normalize_local,
            )
            if not identifier:
                result["invalid"] += 1
                continue

            key = (kind, identifier)
            if key in input_keys:
                result["skipped_duplicate"] += 1
                result["skipped"] += 1
                continue
            input_keys.add(key)

            if key in existing_keys:
                result["skipped_existing"] += 1
                result["skipped"] += 1
                continue

            target_key = "songs" if kind == cls.LOCAL else "remoteSongs"
            playlist[target_key].append(identifier)
            timestamp = max(
                requested_added_at or int(time.time() * 1000),
                max_added_at + 1,
            )
            new_member = {
                "kind": kind,
                "id": identifier,
                "added_at": timestamp,
            }
            if kind == cls.LOCAL:
                new_local_members.append(new_member)
            else:
                new_remote_members.append(new_member)
            existing_keys.add(key)
            max_added_at = timestamp
            result["added"] += 1

        if result["added"]:
            playlist["members"] = [
                *existing_local_members,
                *new_local_members,
                *existing_remote_members,
                *new_remote_members,
            ]
        result["changed"] = result["added"] > 0
        return result

    @classmethod
    def remove_members(
        cls,
        playlist: dict,
        members,
        normalize_local: Callable[[str], str],
    ) -> dict:
        """Remove one normalized input batch with order-preserving filters."""
        raw_members = list(members or [])
        result = cls._batch_result(len(raw_members))
        if not raw_members:
            return result

        cached_normalize_local = cls._cached_normalizer(normalize_local)
        result["normalized_changed"] = cls.normalize_playlist(
            playlist,
            cached_normalize_local,
        )

        existing_keys: set[tuple[str, str]] = set()
        local_ids: list[str] = []
        for member in playlist["members"]:
            kind = str(member.get("kind") or "")
            identifier = str(member.get("id") or "")
            existing_keys.add((kind, identifier))
            if kind == cls.LOCAL:
                local_ids.append(identifier)

        input_keys: set[tuple[str, str]] = set()
        removal_keys: set[tuple[str, str]] = set()
        for raw_member in raw_members:
            kind, identifier, _requested_added_at = cls._normalize_member_input(
                raw_member,
                cached_normalize_local,
            )
            if not identifier:
                result["invalid"] += 1
                continue

            key = (kind, identifier)
            if key in input_keys:
                result["skipped_duplicate"] += 1
                result["skipped"] += 1
                continue
            input_keys.add(key)

            if key not in existing_keys:
                result["skipped_missing"] += 1
                result["skipped"] += 1
                continue
            removal_keys.add(key)

        if not removal_keys:
            return result

        local_removals = {
            identifier
            for kind, identifier in removal_keys
            if kind == cls.LOCAL
        }
        remote_removals = {
            identifier
            for kind, identifier in removal_keys
            if kind == cls.REMOTE
        }
        if local_removals:
            playlist["songs"] = [
                stored_value
                for stored_value, identifier in zip(playlist["songs"], local_ids)
                if identifier not in local_removals
            ]
        if remote_removals:
            playlist["remoteSongs"] = [
                identifier
                for identifier in playlist["remoteSongs"]
                if identifier not in remote_removals
            ]
        playlist["members"] = [
            member
            for member in playlist["members"]
            if (
                str(member.get("kind") or ""),
                str(member.get("id") or ""),
            )
            not in removal_keys
        ]
        result["removed"] = len(removal_keys)
        result["changed"] = True
        return result

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
    def member_index(
        cls,
        playlist: dict,
        normalize_local: Callable[[str], str],
    ) -> dict[tuple[str, str], int]:
        """Return one normalized O(1) lookup table for a playlist view pass."""
        cls.normalize_playlist(playlist, normalize_local)
        return {
            (
                str(member.get("kind") or ""),
                str(member.get("id") or ""),
            ): cls._positive_int(member.get("added_at"))
            for member in playlist.get("members", [])
            if isinstance(member, dict)
        }

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

    @classmethod
    def _normalize_member_input(
        cls,
        member,
        normalize_local: Callable[[str], str],
    ) -> tuple[str, str, int]:
        if isinstance(member, dict):
            kind = member.get("kind")
            identifier = member.get("id")
            added_at = member.get("added_at")
        elif isinstance(member, (list, tuple)) and len(member) >= 2:
            kind = member[0]
            identifier = member[1]
            added_at = member[2] if len(member) >= 3 else None
        else:
            return "", "", 0
        kind, identifier = cls._normalize_member(
            kind,
            identifier,
            normalize_local,
        )
        return kind, identifier, cls._positive_int(added_at)

    @staticmethod
    def _cached_normalizer(
        normalizer: Callable[[str], str],
    ) -> Callable[[str], str]:
        cache: dict[str, str] = {}

        def normalize_once(value: str) -> str:
            cache_key = str(value or "")
            if cache_key not in cache:
                cache[cache_key] = normalizer(value)
            return cache[cache_key]

        return normalize_once

    @staticmethod
    def _batch_result(input_count: int) -> dict:
        return {
            "input_count": max(0, int(input_count or 0)),
            "added": 0,
            "removed": 0,
            "skipped": 0,
            "skipped_existing": 0,
            "skipped_missing": 0,
            "skipped_duplicate": 0,
            "invalid": 0,
            "failed": 0,
            "changed": False,
            "normalized_changed": False,
        }

    @staticmethod
    def _normalize_ids(values, normalizer: Callable[[object], str]) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            identifier = str(normalizer(value) or "").strip()
            if identifier and identifier not in seen:
                normalized.append(identifier)
                seen.add(identifier)
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
        seen: set[str] = set()
        for value in values:
            stored_value = str(value or "").strip()
            identifier = str(normalize_local(stored_value) or "").strip()
            if not identifier or identifier in seen:
                continue
            stored_values.append(stored_value)
            normalized_ids.append(identifier)
            seen.add(identifier)
        return stored_values, normalized_ids

    @staticmethod
    def _positive_int(value) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0
