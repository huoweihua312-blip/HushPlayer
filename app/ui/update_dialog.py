"""Compatibility import for callers that still reference the old UI package."""

from app.services.app_update_service import (
    AppUpdateService,
    UpdateManifest,
    UpdateReleaseNotesSection,
    select_update_release_notes,
)
from app.ui_v2.dialogs.update_dialog import UpdateDialog

__all__ = [
    "AppUpdateService",
    "UpdateDialog",
    "UpdateManifest",
    "UpdateReleaseNotesSection",
    "select_update_release_notes",
]
