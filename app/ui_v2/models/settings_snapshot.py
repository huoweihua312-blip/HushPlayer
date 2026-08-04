"""Immutable-shaped snapshots used by the UI V2 settings edit session."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    """A complete settings document, including unknown legacy keys."""

    values: dict[str, Any]

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None) -> "SettingsSnapshot":
        return cls(deepcopy(values) if isinstance(values, dict) else {})

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)

    def get(self, key: str, default: Any = None) -> Any:
        return deepcopy(self.values.get(str(key), default))

    def with_updates(self, updates: dict[str, Any]) -> "SettingsSnapshot":
        values = self.to_dict()
        for key, value in (updates or {}).items():
            values[str(key)] = deepcopy(value)
        return SettingsSnapshot(values)

