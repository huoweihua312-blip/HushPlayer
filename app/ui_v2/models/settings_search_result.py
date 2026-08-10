"""Search metadata for settings, independent of their visual rows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SettingsSearchResult:
    """A searchable settings row and the category that owns it."""

    path: str
    category: str
    title: str
    description: str
    keywords: tuple[str, ...] = ()

    def matches(self, query: str) -> bool:
        normalized = " ".join(query.lower().split())
        if not normalized:
            return False
        haystack = " ".join((self.category, self.title, self.description, *self.keywords)).lower()
        return all(part in haystack for part in normalized.split())
