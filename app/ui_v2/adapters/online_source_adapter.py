"""Thin source-management view adapter over the mock OnlineAdapter."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.online_adapter import OnlineAdapter


class OnlineSourceAdapter(QObject):
    sources_changed = Signal(object)

    def __init__(self, online: OnlineAdapter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.online = online
        online.source_state_changed.connect(self.sources_changed)

    def sources(self):
        return self.online.sources()

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        self.online.set_source_enabled(source_id, enabled)

    def select_all(self) -> None:
        self.online.set_enabled_sources(source.id for source in self.online.sources())

    def clear_selection(self) -> None:
        self.online.set_enabled_sources(())

    def retry(self) -> bool:
        return self.online.retry()
