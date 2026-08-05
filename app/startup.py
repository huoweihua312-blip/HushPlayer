"""Shared Qt application startup helpers for formal entrypoints."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from app.core.app_paths import APP_NAME, APP_VERSION, AppPaths


UI_FLAVOR_LEGACY = "legacy"
UI_FLAVOR_V2 = "ui-v2"


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    app: QApplication
    icon: QIcon
    paths: AppPaths
    created_application: bool


def configure_process_metadata() -> None:
    """Apply the app identity before resolving Qt paths or creating windows."""

    QCoreApplication.setOrganizationName(APP_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "HushPlayer.Desktop.0.5"
        )


def configure_qt_runtime() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def apply_ui_theme(app: QApplication, ui_flavor: str) -> None:
    """Install the selected shell theme before constructing its MainWindow."""

    flavor = str(ui_flavor or UI_FLAVOR_LEGACY).strip().casefold()
    if flavor == UI_FLAVOR_V2:
        from app.ui_v2.theme.styles import build_application_palette, build_stylesheet
        from app.ui_v2.theme.tokens import get_theme

        theme = get_theme("dark")
        app.setPalette(build_application_palette(theme))
        app.setStyleSheet(build_stylesheet(theme))
        app.setProperty("hushUiFlavor", UI_FLAVOR_V2)
        app.setProperty("hushUiV2ThemeMode", theme.mode)
        return
    if flavor != UI_FLAVOR_LEGACY:
        raise ValueError(f"Unsupported UI flavor: {ui_flavor!r}")
    # The legacy entrypoint installs its established theme immediately after
    # this shared context is created. Clear a V2 sheet when tests reuse one
    # QApplication, without changing the legacy theme manager's palette path.
    if app.property("hushUiFlavor") == UI_FLAVOR_V2:
        app.setStyleSheet("")
    app.setProperty("hushUiFlavor", UI_FLAVOR_LEGACY)


def create_application_context(
    argv: Sequence[str] | None = None,
    *,
    startup_started_at: float | None = None,
    ui_flavor: str = UI_FLAVOR_LEGACY,
) -> ApplicationContext:
    """Create or reuse the one QApplication used by either UI entrypoint."""

    configure_process_metadata()
    configure_qt_runtime()
    paths = AppPaths.resolve()
    app = QApplication.instance()
    created = False
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
        created = True
    if not isinstance(app, QApplication):
        raise RuntimeError("HushPlayer requires a QApplication for UI startup.")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_ui_theme(app, ui_flavor)
    icon = QIcon(str(paths.resource_path("assets", "icons", "HushPlayer.ico")))
    app.setWindowIcon(icon)
    if startup_started_at is not None:
        app.setProperty("hushStartupStartedAt", startup_started_at)
    return ApplicationContext(app=app, icon=icon, paths=paths, created_application=created)
