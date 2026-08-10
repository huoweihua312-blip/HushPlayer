"""Thin source-management view adapter over the mock OnlineAdapter."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.online_adapter import OnlineAdapter


class OnlineSourceAdapter(QObject):
    sources_changed = Signal(object)

    def __init__(self, online: OnlineAdapter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.online = online
        discovery = online.discovery
        self.importer = getattr(discovery, "source_importer", None)
        online.source_state_changed.connect(self.sources_changed)
        if self.importer is not None:
            self.importer.sources_changed.connect(online.refresh_sources)

    def sources(self):
        return self.online.sources()

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if self.importer is not None and self.importer.set_enabled(source_id, enabled):
            self.online.set_source_enabled(source_id, enabled)
            return
        self.online.set_source_enabled(source_id, enabled)

    def remove(self, source_id: str) -> bool:
        if self.importer is None:
            return False
        return self.importer.remove_source(source_id)

    def select_all(self) -> None:
        self.online.set_enabled_sources(source.id for source in self.online.sources())

    def clear_selection(self) -> None:
        self.online.set_enabled_sources(())

    def retry(self) -> bool:
        return self.online.retry()
