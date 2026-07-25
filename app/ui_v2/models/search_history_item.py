"""In-memory search history value for the online-search prototype."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SearchHistoryItem:
    query: str
    searched_at: datetime
