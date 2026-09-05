"""Small, failure-tolerant persistence for the UI V2 playback session."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


_LOGGER = logging.getLogger(__name__)
_SESSION_VERSION = 1
_MAX_QUEUE_ITEMS = 10_000
_MAX_POSITION_MS = 31 * 24 * 60 * 60 * 1_000


def _identity(value: object) -> str:
    return str(value or "").strip()[:2_048]


@dataclass(frozen=True, slots=True)
class PlaybackSession:
    """Validated playback context that is safe to resolve against a new library."""

    current_identity: str = ""
    queue_identities: tuple[str, ...] = ()
    position_ms: int = 0
    route: str = "browse"
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, value: object) -> "PlaybackSession | None":
        if not isinstance(value, dict):
            return None
        try:
            version = int(value.get("version", 0))
        except (TypeError, ValueError):
            return None
        if version != _SESSION_VERSION:
            return None
        raw_queue = value.get("queue_identities", ())
        if not isinstance(raw_queue, (list, tuple)):
            raw_queue = ()
        queue: list[str] = []
        seen: set[str] = set()
        for raw_identity in raw_queue[:_MAX_QUEUE_ITEMS]:
            identity = _identity(raw_identity)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            queue.append(identity)
        try:
            position_ms = int(value.get("position_ms", 0))
        except (TypeError, ValueError):
            position_ms = 0
        route = str(value.get("route") or "browse").strip()[:512] or "browse"
        return cls(
            current_identity=_identity(value.get("current_identity")),
            queue_identities=tuple(queue),
            position_ms=max(0, min(_MAX_POSITION_MS, position_ms)),
            route=route,
            updated_at=str(value.get("updated_at") or "").strip()[:128],
        )

    @classmethod
    def create(
        cls,
        *,
        current_identity: object,
        queue_identities: Iterable[object],
        position_ms: object,
        route: object,
    ) -> "PlaybackSession":
        try:
            normalized_position = int(position_ms or 0)
        except (TypeError, ValueError):
            normalized_position = 0
        queue: list[str] = []
        seen: set[str] = set()
        for raw_identity in queue_identities:
            identity = _identity(raw_identity)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            queue.append(identity)
            if len(queue) >= _MAX_QUEUE_ITEMS:
                break
        return cls(
            current_identity=_identity(current_identity),
            queue_identities=tuple(queue),
            position_ms=max(0, min(_MAX_POSITION_MS, normalized_position)),
            route=str(route or "browse").strip()[:512] or "browse",
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "version": _SESSION_VERSION,
            "current_identity": self.current_identity,
            "queue_identities": list(self.queue_identities),
            "position_ms": self.position_ms,
            "route": self.route,
            "updated_at": self.updated_at,
        }


class PlaybackSessionStore:
    """Read and atomically replace one optional playback-session document."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> PlaybackSession | None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, TypeError, ValueError) as error:
            _LOGGER.warning("Ignoring unreadable playback session %s: %s", self.path, error)
            return None
        session = PlaybackSession.from_mapping(document)
        if session is None and document:
            _LOGGER.warning("Ignoring invalid playback session %s", self.path)
        return session

    def save(self, session: PlaybackSession) -> bool:
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as stream:
                json.dump(session.to_mapping(), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                temporary_path = Path(stream.name)
            os.replace(temporary_path, self.path)
            return True
        except (OSError, TypeError, ValueError) as error:
            _LOGGER.warning("Could not save playback session %s: %s", self.path, error)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False
