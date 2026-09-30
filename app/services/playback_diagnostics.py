"""Small, opt-in-at-runtime diagnostics for online playback projection bugs."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


class PlaybackDiagnostics:
    """Append low-volume playback lifecycle events to a user-writable log.

    The diagnostic file is intentionally separate from startup timing logs so a
    playback repro can be shared without mixing unrelated startup records.
    Values are bounded and URLs are redacted before writing.
    """

    _URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
    _MAX_TEXT_LENGTH = 240

    def __init__(self, log_dir: Path | str | None) -> None:
        self.path = (
            Path(log_dir) / "playback-diagnostics.log"
            if log_dir is not None
            else None
        )

    def record(self, event: str, **fields: Any) -> None:
        """Write one bounded JSONL event; diagnostics must never affect playback."""

        if self.path is None:
            return
        payload = {
            "prefix": "[PLAYBACK-DIAG]",
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "event": str(event or "unknown"),
        }
        payload.update({str(key): self._safe_value(value) for key, value in fields.items()})
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except (OSError, TypeError, ValueError):
            return

    @classmethod
    def _safe_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): cls._safe_value(item)
                for key, item in list(value.items())[:32]
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._safe_value(item) for item in list(value)[:32]]
        if isinstance(value, str):
            text = cls._URL_RE.sub("<redacted-url>", value)
            return text[: cls._MAX_TEXT_LENGTH]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)[: cls._MAX_TEXT_LENGTH]
