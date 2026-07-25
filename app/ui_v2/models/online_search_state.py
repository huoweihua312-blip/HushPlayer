"""Explicit search-page state emitted by the mock OnlineAdapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OnlineSearchState:
    phase: str
    query: str
    progress: int = 0
    message: str = ""
    generation: int = 0
