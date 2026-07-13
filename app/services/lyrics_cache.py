from __future__ import annotations

import hashlib
import json
import time
import unicodedata
from pathlib import Path

from app.models.media_item import MediaItem


class LyricsCache:
    """Small atomic JSON cache for online lyric results."""

    VERSION = 1
    NOT_FOUND_TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._loaded = False
        self._entries: dict[str, dict] = {}

    @classmethod
    def key_for(cls, item: MediaItem) -> str:
        if item.source_id and item.track_id:
            identity = f"id\0{item.source_id}\0{item.track_id}"
        else:
            values = [
                cls._normalize(item.title),
                cls._normalize(item.artist),
                cls._normalize(item.album),
                str(max(0, int(item.duration or 0))),
            ]
            identity = "meta\0" + "\0".join(values)
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def get(self, item: MediaItem) -> dict | None:
        self._ensure_loaded()
        entry = self._entries.get(self.key_for(item))
        if not isinstance(entry, dict):
            return None
        if entry.get("not_found"):
            fetched_at = self._safe_int(entry.get("fetched_at"))
            if fetched_at <= 0 or time.time() - fetched_at > self.NOT_FOUND_TTL_SECONDS:
                return None
        return dict(entry)

    def put(self, item: MediaItem, payload: dict) -> None:
        self._ensure_loaded()
        entry = {
            "text": str(payload.get("text") or ""),
            "type": str(payload.get("type") or "none"),
            "source": str(payload.get("source") or "unknown"),
            "fetched_at": self._safe_int(payload.get("fetched_at"), int(time.time())),
            "not_found": bool(payload.get("not_found")),
        }
        self._entries[self.key_for(item)] = entry
        self._save()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        entries = document.get("entries") if isinstance(document, dict) else None
        if isinstance(entries, dict):
            self._entries = {
                str(key): dict(value)
                for key, value in entries.items()
                if isinstance(value, dict)
            }

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    {"version": self.VERSION, "entries": self._entries},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError:
            # Lyrics should still be displayed when a cache directory is
            # temporarily unavailable or read-only.
            return

    @staticmethod
    def _normalize(value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return " ".join(text.split())

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return max(0, int(value or default))
        except (TypeError, ValueError):
            return max(0, int(default))
