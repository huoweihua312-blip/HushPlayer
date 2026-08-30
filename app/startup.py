"""Shared Qt application startup helpers for formal entrypoints."""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from app.core.app_paths import APP_NAME, APP_VERSION, AppPaths
from app.startup_diagnostics import StartupDiagnostics


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


def apply_ui_theme(
    app: QApplication,
    *,
    settings_path: str | None = None,
) -> None:
    """Install the UI V2 theme before constructing its MainWindow."""

    from app.ui_v2.theme.styles import build_application_palette, build_stylesheet
    from app.ui_v2.adapters.legacy_settings_bridge import load_settings_document
    from app.ui_v2.theme.tokens import get_theme, resolve_font_family

    resolved_settings_path = settings_path or os.environ.get(
        "HUSHPLAYER_UI_V2_SETTINGS_PATH", ""
    )
    if not resolved_settings_path:
        resolved_settings_path = str(AppPaths.resolve().data_dir / "settings.json")
    values = load_settings_document(Path(resolved_settings_path))
    appearance = str(values.get("appearance_mode", "dark")).casefold()
    theme = get_theme("light" if appearance == "light" else "dark")
    ui_font = QFont(resolve_font_family(), 10)
    ui_font.setStyleHint(QFont.StyleHint.SansSerif)
    ui_font.setStyleStrategy(
        QFont.StyleStrategy.PreferQuality | QFont.StyleStrategy.PreferAntialias
    )
    ui_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(ui_font)
    app.setPalette(build_application_palette(theme))
    app.setStyleSheet(build_stylesheet(theme))
    app.setProperty("hushUiFlavor", UI_FLAVOR_V2)
    app.setProperty("hushUiV2ThemeMode", theme.mode)


def create_application_context(
    argv: Sequence[str] | None = None,
    *,
    startup_started_at: float | None = None,
    settings_path: str | None = None,
    startup_diagnostics: StartupDiagnostics | None = None,
) -> ApplicationContext:
    """Create or reuse the one QApplication used by the UI V2 entrypoint."""

    configure_process_metadata()
    configure_qt_runtime()
    if startup_diagnostics is not None:
        startup_diagnostics.mark("process_metadata_and_qt_runtime")
    paths = AppPaths.resolve()
    if startup_diagnostics is not None:
        startup_diagnostics.mark("app_paths.resolve")
    app = QApplication.instance()
    created = False
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
        created = True
    if startup_diagnostics is not None:
        startup_diagnostics.mark("qapplication.create_or_reuse")
    if not isinstance(app, QApplication):
        raise RuntimeError("HushPlayer requires a QApplication for UI startup.")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_ui_theme(app, settings_path=settings_path)
    if startup_diagnostics is not None:
        startup_diagnostics.mark("ui_theme_and_settings")
    icon = QIcon(str(paths.resource_path("assets", "icons", "HushPlayer.ico")))
    app.setWindowIcon(icon)
    if startup_started_at is not None:
        app.setProperty("hushStartupStartedAt", startup_started_at)
    return ApplicationContext(app=app, icon=icon, paths=paths, created_application=created)
