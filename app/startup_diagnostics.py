"""Low-cost startup timing diagnostics that never block application startup."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time
from typing import Any


class StartupDiagnostics:
    """Collect named startup marks and write one human-readable run report."""

    def __init__(self, started_at: float | None = None) -> None:
        self.started_at = float(started_at if started_at is not None else time.perf_counter())
        self._last_mark = self.started_at
        self._marks: list[tuple[str, float, float, str]] = []

    def mark(self, name: str, *, lane: str = "main") -> None:
        """Record one stage without doing any filesystem work."""

        now = time.perf_counter()
        self._marks.append(
            (
                str(name or "unnamed"),
                (now - self.started_at) * 1000.0,
                (now - self._last_mark) * 1000.0,
                str(lane or "main"),
            )
        )
        self._last_mark = now

    def write(self, log_dir: Path | str | None) -> bool:
        """Append the latest report; logging failures are intentionally ignored."""

        if log_dir is None:
            return False
        try:
            target_dir = Path(log_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / "startup-performance.log"
            slowest = max(self._marks, key=lambda item: item[2], default=None)
            lines = [
                "",
                f"[{datetime.now().astimezone().isoformat(timespec='milliseconds')}] HushPlayer startup",
                f"total_elapsed_ms={(time.perf_counter() - self.started_at) * 1000.0:.1f}",
            ]
            if slowest is not None:
                lines.append(
                    f"slowest_stage={slowest[0]} duration_ms={slowest[2]:.1f} lane={slowest[3]}"
                )
            for name, elapsed, duration, lane in self._marks:
                lines.append(
                    f"stage={name} elapsed_ms={elapsed:.1f} duration_ms={duration:.1f} lane={lane}"
                )
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n".join(lines) + "\n")
            return True
        except (OSError, TypeError, ValueError):
            return False

    @property
    def marks(self) -> tuple[dict[str, Any], ...]:
        """Expose immutable-friendly data for focused tests and diagnostics."""

        return tuple(
            {
                "name": name,
                "elapsed_ms": elapsed,
                "duration_ms": duration,
                "lane": lane,
            }
            for name, elapsed, duration, lane in self._marks
        )
