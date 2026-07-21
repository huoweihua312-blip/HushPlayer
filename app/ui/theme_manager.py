"""Application-wide appearance selection and Qt theme application."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.design_system import get_theme_tokens, set_active_theme_tokens


APPEARANCE_MODES = ("dark", "light", "system")
DEFAULT_APPEARANCE_MODE = "dark"
_APPLICATION_THEME_MANAGERS: dict[int, "ThemeManager"] = {}


def normalize_appearance_mode(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in APPEARANCE_MODES else DEFAULT_APPEARANCE_MODE


def resolve_system_appearance(app: QApplication | None = None) -> str:
    """Resolve Windows/Qt system appearance to an explicit safe mode."""
    gui_app = app or QGuiApplication.instance()
    if gui_app is None:
        return DEFAULT_APPEARANCE_MODE
    try:
        scheme = gui_app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except (AttributeError, RuntimeError):
        pass
    # Qt may report Unknown on old Windows themes.  Preserve the established
    # dark-first behaviour rather than inferring from an app palette that may
    # already have been themed.
    return DEFAULT_APPEARANCE_MODE


def resolve_appearance_mode(
    mode,
    *,
    system_resolver: Callable[[], str] | None = None,
) -> str:
    normalized = normalize_appearance_mode(mode)
    if normalized != "system":
        return normalized
    resolved = str((system_resolver or resolve_system_appearance)() or "").lower()
    return resolved if resolved in {"dark", "light"} else DEFAULT_APPEARANCE_MODE


def create_application_palette(tokens: dict[str, str] | None = None) -> QPalette:
    t = tokens or get_theme_tokens()
    palette = QPalette()
    role_colors = {
        QPalette.ColorRole.Window: t["window_background"],
        QPalette.ColorRole.WindowText: t["text_primary"],
        QPalette.ColorRole.Base: t["input_background"],
        QPalette.ColorRole.AlternateBase: t["surface_secondary"],
        QPalette.ColorRole.Text: t["text_primary"],
        QPalette.ColorRole.Button: t["surface_secondary"],
        QPalette.ColorRole.ButtonText: t["text_secondary"],
        QPalette.ColorRole.Highlight: t["accent"],
        QPalette.ColorRole.HighlightedText: t["on_accent"],
        QPalette.ColorRole.ToolTipBase: t["surface_secondary"],
        QPalette.ColorRole.ToolTipText: t["text_primary"],
        QPalette.ColorRole.PlaceholderText: t["text_muted"],
        QPalette.ColorRole.Link: t["accent"],
    }
    for role, color in role_colors.items():
        palette.setColor(QPalette.ColorGroup.All, role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["text_disabled"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(t["surface"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(t["window_background"]))
    return palette


def build_dialog_qss(tokens: dict[str, str] | None = None) -> str:
    t = tokens or get_theme_tokens()
    return f"""
    QDialog, QMessageBox, QInputDialog {{ background: {t['window_background']}; color: {t['text_primary']}; font-family: \"Segoe UI\", \"Microsoft YaHei UI\", \"Microsoft YaHei\"; }}
    QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {{ background: transparent; color: {t['text_secondary']}; }}
    QDialog QLabel:disabled, QDialog QCheckBox:disabled, QDialog QRadioButton:disabled {{ color: {t['text_disabled']}; }}
    QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit {{ background: {t['input_background']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 8px 10px; selection-background-color: {t['accent']}; selection-color: {t['on_accent']}; }}
    QDialog QLineEdit:focus, QDialog QTextEdit:focus, QDialog QPlainTextEdit:focus {{ border: 1px solid {t['accent']}; background: {t['surface_secondary']}; }}
    QDialog QLineEdit:disabled, QDialog QTextEdit:disabled, QDialog QPlainTextEdit:disabled {{ background: {t['window_background']}; color: {t['text_disabled']}; border-color: {t['border']}; }}
    QDialog QLineEdit[readOnly=\"true\"], QDialog QTextEdit[readOnly=\"true\"], QDialog QPlainTextEdit[readOnly=\"true\"] {{ background: {t['surface_secondary']}; color: {t['text_muted']}; }}
    QDialog QComboBox {{ background: {t['input_background']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 7px 10px; }}
    QDialog QComboBox:hover, QDialog QComboBox:focus {{ border-color: {t['border_strong']}; }}
    QDialog QComboBox:disabled {{ background: {t['window_background']}; color: {t['text_disabled']}; }}
    QDialog QComboBox QAbstractItemView {{ background: {t['surface_secondary']}; color: {t['text_primary']}; border: 1px solid {t['border_strong']}; outline: none; selection-background-color: {t['selection_background']}; selection-color: {t['selection_text']}; }}
    QDialog QCheckBox, QDialog QRadioButton {{ background: transparent; color: {t['text_secondary']}; spacing: 8px; }}
    QDialog QListWidget, QDialog QTreeWidget, QDialog QTableWidget {{ background: {t['input_background']}; color: {t['text_primary']}; alternate-background-color: {t['surface_secondary']}; border: 1px solid {t['border']}; outline: none; selection-background-color: {t['selection_background']}; selection-color: {t['selection_text']}; }}
    QDialog QListWidget::item:hover, QDialog QTreeWidget::item:hover, QDialog QTableWidget::item:hover {{ background: {t['surface_hover']}; }}
    QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {{ background: {t['surface_secondary']}; color: {t['text_secondary']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 8px 14px; min-width: 72px; }}
    QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{ background: {t['surface_hover']}; color: {t['text_primary']}; border-color: {t['border_strong']}; }}
    QDialog QPushButton:pressed, QMessageBox QPushButton:pressed, QInputDialog QPushButton:pressed {{ background: {t['surface_pressed']}; }}
    QDialog QPushButton:disabled, QMessageBox QPushButton:disabled, QInputDialog QPushButton:disabled {{ background: {t['surface']}; color: {t['text_disabled']}; border-color: {t['border']}; }}
    QPushButton#dangerDialogButton {{ background: {t['danger_soft']}; color: {t['danger']}; border-color: {t['danger']}; }}
    QPushButton#dangerDialogButton:hover {{ background: {t['danger']}; color: {t['on_accent']}; }}
    QDialog QScrollArea, QDialog QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    """


def build_application_fallback_qss(tokens: dict[str, str] | None = None) -> str:
    t = tokens or get_theme_tokens()
    return build_dialog_qss(t) + f"""
    QMenu {{ background: {t['surface_secondary']}; color: {t['text_secondary']}; border: 1px solid {t['border_strong']}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 8px 24px; border-radius: 7px; }}
    QMenu::item:selected {{ background: {t['selection_background']}; color: {t['selection_text']}; }}
    QMenu::item:disabled {{ background: transparent; color: {t['text_disabled']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 6px 8px; }}
    QToolTip {{ background: {t['surface_secondary']}; color: {t['text_primary']}; border: 1px solid {t['border_strong']}; border-radius: 8px; padding: 6px 8px; }}
    QScrollBar:vertical {{ background: {t['scrollbar_background']}; width: 10px; margin: 2px; border-radius: 5px; }}
    QScrollBar::handle:vertical {{ background: {t['scrollbar_handle']}; min-height: 28px; border-radius: 5px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def apply_application_theme(app: QApplication, resolved_mode: str) -> bool:
    """Apply Qt palette/QSS only when the resolved colour scheme changed."""
    resolved_mode = "light" if resolved_mode == "light" else "dark"
    if app.property("hushResolvedAppearance") == resolved_mode:
        return False
    tokens = set_active_theme_tokens(resolved_mode)
    base_qss = app.property("hushApplicationBaseStyleSheet")
    if not isinstance(base_qss, str):
        base_qss = app.styleSheet()
        app.setProperty("hushApplicationBaseStyleSheet", base_qss)
    app.setPalette(create_application_palette(tokens))
    app.setStyleSheet(f"{base_qss}\n{build_application_fallback_qss(tokens)}")
    app.setProperty("hushResolvedAppearance", resolved_mode)
    app.setProperty("hushApplicationThemeApplyCount", int(app.property("hushApplicationThemeApplyCount") or 0) + 1)
    return True


def apply_dialog_style(dialog: QDialog, extra_qss: str = "") -> None:
    app = QApplication.instance()
    mode = app.property("hushResolvedAppearance") if app is not None else "dark"
    tokens = get_theme_tokens("light" if mode == "light" else "dark")
    dialog.setPalette(create_application_palette(tokens))
    dialog.setStyleSheet(f"{build_dialog_qss(tokens)}\n{extra_qss}")


class ThemeManager(QObject):
    """Owns user preference, system resolution and lightweight notifications."""

    themeChanged = Signal(str)
    appearanceModeChanged = Signal(str)

    def __init__(
        self,
        app: QApplication,
        *,
        system_resolver: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(app)
        self.app = app
        self._system_resolver = system_resolver or (lambda: resolve_system_appearance(app))
        self.appearance_mode = DEFAULT_APPEARANCE_MODE
        self.resolved_mode = ""
        self._system_signal_connected = False
        self._connect_system_appearance_signal()
        app.installEventFilter(self)

    def _connect_system_appearance_signal(self) -> None:
        try:
            signal = self.app.styleHints().colorSchemeChanged
            signal.connect(self._on_system_appearance_changed)
            self._system_signal_connected = True
        except (AttributeError, RuntimeError, TypeError):
            # Older Qt bindings have no reliable live system-theme signal.  The
            # application event fallback below safely rechecks on activation.
            self._system_signal_connected = False

    @property
    def system_signal_connected(self) -> bool:
        return self._system_signal_connected

    def resolve(self, mode=None) -> str:
        return resolve_appearance_mode(
            self.appearance_mode if mode is None else mode,
            system_resolver=self._system_resolver,
        )

    def set_appearance_mode(self, mode, *, force: bool = False) -> bool:
        normalized = normalize_appearance_mode(mode)
        resolved = self.resolve(normalized)
        mode_changed = normalized != self.appearance_mode
        resolved_changed = resolved != self.resolved_mode
        self.appearance_mode = normalized
        if not force and not resolved_changed:
            if mode_changed:
                self.appearanceModeChanged.emit(normalized)
            return False
        self.resolved_mode = resolved
        apply_application_theme(self.app, resolved)
        if mode_changed:
            self.appearanceModeChanged.emit(normalized)
        self.themeChanged.emit(resolved)
        return True

    def _on_system_appearance_changed(self, _scheme=None) -> None:
        if self.appearance_mode == "system":
            self.set_appearance_mode("system")

    def eventFilter(self, watched, event) -> bool:
        if watched is self.app and self.appearance_mode == "system":
            # This is a compatibility fallback only. It does not guess a new
            # mode; it reuses Qt's reported scheme when the app is activated or
            # receives a palette/theme change.
            event_types = {QEvent.Type.ApplicationActivate, QEvent.Type.ApplicationPaletteChange}
            theme_change = getattr(QEvent.Type, "ThemeChange", None)
            if theme_change is not None:
                event_types.add(theme_change)
            if event.type() in event_types:
                self.set_appearance_mode("system")
        return super().eventFilter(watched, event)


def get_application_theme_manager(app: QApplication | None = None) -> ThemeManager:
    target = app or QApplication.instance()
    if target is None:
        raise RuntimeError("QApplication must exist before creating ThemeManager")
    key = id(target)
    manager = _APPLICATION_THEME_MANAGERS.get(key)
    if manager is not None and manager.parent() is target:
        return manager
    manager = ThemeManager(target)
    _APPLICATION_THEME_MANAGERS[key] = manager
    return manager
