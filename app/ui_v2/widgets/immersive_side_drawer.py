"""Shared non-modal floating panel used by immersive player surfaces."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.theme.icons import fluent_settings_interactive_icon
from app.ui_v2.theme.immersive_tokens import IMMERSIVE_GLASS
from app.ui_v2.theme.tokens import Theme


class ImmersiveFloatingPanel(QFrame):
    """A stable floating container with one content surface at a time."""

    closed = Signal()

    def __init__(self, title: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("immersiveFloatingPanel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(410)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("immersiveDrawerTitle")
        self.count_label = QLabel(self)
        self.count_label.setObjectName("immersiveDrawerCount")
        self.close_button = QToolButton(self)
        self.close_button.setObjectName("immersiveDrawerClose")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setToolTip("关闭")
        self.close_button.setAccessibleName("关闭")
        self.close_button.clicked.connect(self.closed)

        header = QHBoxLayout()
        header.setContentsMargins(18, 14, 12, 10)
        header.setSpacing(8)
        header.addWidget(self.title_label)
        header.addWidget(self.count_label)
        header.addStretch(1)
        header.addWidget(self.close_button)

        self.content_host = QWidget(self)
        self.content_host.setObjectName("immersiveDrawerContentHost")
        self._content_layout = QVBoxLayout(self.content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content: QWidget | None = None
        self._footer: QWidget | None = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addLayout(header)
        self._layout.addWidget(self.content_host, 1)
        self.set_theme(theme)

    def set_content(self, content: QWidget) -> None:
        if self._content is content:
            return
        if self._content is not None:
            raise RuntimeError("ImmersiveFloatingPanel content is installed once and remains stable")
        if content.parentWidget() is not self.content_host:
            raise RuntimeError("ImmersiveFloatingPanel content must be created in its content host")
        self._content = content
        self._content_layout.addWidget(content)

    def set_footer(self, footer: QWidget | None) -> None:
        if self._footer is footer:
            return
        if self._footer is not None:
            raise RuntimeError("ImmersiveFloatingPanel footer is installed once and remains stable")
        self._footer = footer
        if footer is not None:
            if footer.parentWidget() is not self:
                raise RuntimeError("ImmersiveFloatingPanel footer must be created in the panel")
            self._layout.addWidget(footer)

    def set_count(self, text: str) -> None:
        self.count_label.setText(str(text or ""))
        self.count_label.setVisible(bool(text))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.setStyleSheet(
            "QFrame#immersiveFloatingPanel { background: rgba(14, 18, 24, 0.88); "
            f"border: 1px solid {IMMERSIVE_GLASS.border}; border-radius: 10px; }}"
            "QWidget#immersiveDrawerContentHost { background: transparent; border: 0; }"
            f"QLabel#immersiveDrawerTitle {{ color: {IMMERSIVE_GLASS.primary_text}; font-size: {theme.fonts.section_title}px; font-weight: 600; }}"
            f"QLabel#immersiveDrawerCount {{ color: {IMMERSIVE_GLASS.secondary_text}; font-size: {theme.fonts.caption}px; }}"
            "QToolButton#immersiveDrawerClose { border: 0; border-radius: 8px; background: transparent; }"
            f"QToolButton#immersiveDrawerClose:hover {{ background: {IMMERSIVE_GLASS.default}; }}"
            f"QToolButton#immersiveDrawerClose:focus {{ border: 1px solid {colors.focus_ring}; }}"
        )
        self.close_button.setIcon(fluent_settings_interactive_icon("dismiss", theme, 18))
        self.close_button.setProperty("fluentIconFamily", "fluent_settings")
        self.close_button.setProperty("fluentIconName", "dismiss")
        self.close_button.setProperty("fluentIconFile", "dismiss_20_regular.svg")


ImmersiveSideDrawer = ImmersiveFloatingPanel
