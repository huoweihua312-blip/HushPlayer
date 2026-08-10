"""Shared empty and inline-error states for Q3 content pages."""

from __future__ import annotations

from PySide6.QtCore import Signal

from app.ui_v2.widgets.empty_state import EmptyState


class InlineErrorState(EmptyState):
    """A non-modal, retryable error surface kept near the affected content."""

    retry_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.empty_icon_name = "missing"
        self.set_state("error")
        self.set_action("重试")
        self.action_requested.connect(self.retry_requested)
