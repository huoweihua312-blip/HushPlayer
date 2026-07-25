"""Independent top-level window for the UI V2 first-phase preview."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from app.ui_v2.adapters.library_adapter import LibraryAdapter
from app.ui_v2.pages.library_page import LibraryPage
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme, get_theme


class PreviewWindow(QMainWindow):
    """Loads mock data only and has no dependency on the production MainWindow."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = get_theme("dark")
        self.adapter = LibraryAdapter(parent=self)
        self.adapter.load_mock_tracks(1000)
        self.library_page = LibraryPage(self.adapter, self._theme, self)
        self.library_page.theme_changed.connect(self.set_theme)
        self.root = QWidget(self)
        self.root.setObjectName("uiV2Root")
        layout = QVBoxLayout(self.root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.library_page)
        self.setCentralWidget(self.root)
        self.setWindowTitle("HushPlayer UI V2 Preview")
        self.setMinimumSize(800, 540)
        self.resize(1100, 700)
        self.set_theme(self._theme.mode)

    @property
    def theme(self) -> Theme:
        return self._theme

    def set_theme(self, mode: str) -> None:
        self._theme = get_theme(mode)
        self.root.setStyleSheet(build_stylesheet(self._theme))
        self.library_page.set_theme(self._theme)
