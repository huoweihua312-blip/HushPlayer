"""Draft lifecycle for the formal UI V2 Settings Overlay."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from app.ui_v2.models.settings_snapshot import SettingsSnapshot


Validator = Callable[[dict[str, Any]], dict[str, str]]


@dataclass(slots=True)
class SettingsEditSession:
    """Keeps working values separate from the persisted settings snapshot."""

    original_snapshot: SettingsSnapshot
    working_snapshot: SettingsSnapshot
    dirty_fields: set[str] = field(default_factory=set)
    previewed_fields: set[str] = field(default_factory=set)
    validation_errors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def open(cls, snapshot: SettingsSnapshot) -> "SettingsEditSession":
        original = SettingsSnapshot.from_mapping(snapshot.to_dict())
        return cls(original, SettingsSnapshot.from_mapping(original.to_dict()))

    def get(self, key: str, default: Any = None) -> Any:
        return self.working_snapshot.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        key = str(key)
        if self.get(key) == value:
            return False
        self.working_snapshot = self.working_snapshot.with_updates({key: value})
        if self.original_snapshot.get(key) == value:
            self.dirty_fields.discard(key)
        else:
            self.dirty_fields.add(key)
        return True

    def mark_previewed(self, key: str) -> None:
        self.previewed_fields.add(str(key))

    def validate(self, validator: Validator) -> dict[str, str]:
        self.validation_errors = dict(validator(self.working_snapshot.to_dict()) or {})
        return dict(self.validation_errors)

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_fields)

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors

    def replace_after_save(self, snapshot: SettingsSnapshot) -> None:
        self.original_snapshot = SettingsSnapshot.from_mapping(snapshot.to_dict())
        self.working_snapshot = SettingsSnapshot.from_mapping(snapshot.to_dict())
        self.dirty_fields.clear()
        self.previewed_fields.clear()
        self.validation_errors.clear()

    def cancel(self) -> SettingsSnapshot:
        original = SettingsSnapshot.from_mapping(self.original_snapshot.to_dict())
        self.working_snapshot = SettingsSnapshot.from_mapping(original.to_dict())
        self.dirty_fields.clear()
        self.previewed_fields.clear()
        self.validation_errors.clear()
        return original

