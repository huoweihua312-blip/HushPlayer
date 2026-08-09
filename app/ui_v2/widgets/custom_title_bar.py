"""Approved frameless normal-window title bar for the first V2 migration phase."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLineEdit, QToolButton, QWidget

from app.ui_v2.theme.icons import fluent_settings_interactive_icon, icon
from app.ui_v2.theme.tokens import Theme


class CustomTitleBar(QFrame):
    """A quiet 59px chrome row with content-centred search and native actions."""

    back_requested = Signal()
    forward_requested = Signal()
    settings_requested = Signal()
    theme_toggle_requested = Signal()
    view_options_requested = Signal()
    search_text_changed = Signal(str)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self._compact = False
        self.setObjectName("customTitleBar")
        self.setFixedHeight(theme.metrics.title_bar_height)

        self.back_button = self._button("back", "返回", self)
        self.forward_button = self._button("forward", "前进", self)
        self.back_button.clicked.connect(self.back_requested)
        self.forward_button.clicked.connect(self.forward_requested)

        self.search_icon = self._button("search", "搜索", self)
        self.search_icon.setEnabled(False)
        self.search_input = QLineEdit(self)
        self.search_input.setObjectName("titleBarSearchInput")
        self.search_input.setPlaceholderText("搜索")
        self.search_input.textChanged.connect(self.search_text_changed)
        self.search_box = QWidget(self)
        self.search_box.setObjectName("titleBarSearchBox")
        self.search_box.setFixedSize(460, 36)
        search_layout = QHBoxLayout(self.search_box)
        search_layout.setContentsMargins(4, 0, 8, 0)
        search_layout.setSpacing(0)
        search_layout.addWidget(self.search_icon)
        search_layout.addWidget(self.search_input, 1)

        self.settings_button = self._button("settings", "设置", self)
        self.settings_button.setAccessibleName("设置")
        self.theme_button = self._button(
            "moon" if theme.mode == "dark" else "sun",
            "切换主题",
            self,
        )
        self.theme_button.setAccessibleName("主题切换")
        self.view_options_button = self._button("more", "视图选项（暂不可用）", self)
        self.view_options_button.setAccessibleName("视图选项")
        self.view_options_button.setEnabled(False)
        # Compatibility handles remain available for older shell tests and
        # integrations, but are not part of the approved Q1 utility surface.
        self.notifications_button = self._button("notification", "通知", self)
        self.notifications_button.setVisible(False)
        self.avatar_button = self._button("user", "用户", self)
        self.avatar_button.setVisible(False)
        self.settings_button.clicked.connect(self.settings_requested)
        self.theme_button.clicked.connect(self.theme_toggle_requested)
        self.view_options_button.clicked.connect(self.view_options_requested)

        self.minimize_button = self._button("window_minimize", "最小化", self, window_control=True)
        self.maximize_button = self._button("window_maximize", "最大化", self, window_control=True)
        self.close_button = self._button("window_close", "关闭", self, window_control=True)
        self.close_button.setObjectName("titleBarClose")
        self.minimize_button.clicked.connect(self._minimize_window)
        self.maximize_button.clicked.connect(self._toggle_maximized)
        self.close_button.clicked.connect(self._close_window)

        history = QWidget(self)
        history_layout = QHBoxLayout(history)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(5)
        history_layout.addWidget(self.back_button)
        history_layout.addWidget(self.forward_button)

        utility = QWidget(self)
        utility_layout = QHBoxLayout(utility)
        utility_layout.setContentsMargins(0, 0, 0, 0)
        utility_layout.setSpacing(2)
        utility_layout.setSpacing(4)
        utility_layout.addWidget(self.settings_button)
        utility_layout.addWidget(self.theme_button)
        utility_layout.addWidget(self.view_options_button)

        window_controls = QWidget(self)
        controls_layout = QHBoxLayout(window_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        controls_layout.addWidget(self.minimize_button)
        controls_layout.addWidget(self.maximize_button)
        controls_layout.addWidget(self.close_button)

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(0)
        self._layout.setVerticalSpacing(0)
        self._sidebar_spacer = QWidget(self)
        self._sidebar_spacer.setFixedWidth(theme.metrics.sidebar_width)
        self._layout.addWidget(self._sidebar_spacer, 0, 0)
        self._layout.addWidget(history, 0, 1)
        self._layout.addWidget(self.search_box, 0, 3, Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(utility, 0, 5)
        self._layout.addWidget(window_controls, 0, 6)
        self._layout.setColumnMinimumWidth(1, 64)
        self._layout.setColumnMinimumWidth(3, 460)
        self._layout.setColumnMinimumWidth(5, 60)
        self._layout.setColumnMinimumWidth(6, 84)
        self._layout.setColumnStretch(2, 13)
        self._layout.setColumnStretch(4, 10)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setFixedHeight(theme.metrics.title_bar_height)
        self.setStyleSheet(
            f"QFrame#customTitleBar {{ background: {c.titlebar_background}; border: 0; border-bottom: 1px solid {c.divider}; }}"
            f"QToolButton#titleBarButton {{ border: 0; border-radius: 5px; background: transparent; color: {c.text_secondary}; }}"
            f"QToolButton#titleBarButton:hover {{ background: {c.surface_hover}; color: {c.text_primary}; }}"
            f"QToolButton#titleBarButton:disabled {{ background: transparent; color: {c.text_disabled}; }}"
            f"QToolButton#titleBarWindowControl {{ border: 0; background: transparent; color: {c.text_secondary}; }}"
            f"QToolButton#titleBarWindowControl:hover {{ background: {c.surface_hover}; color: {c.text_primary}; }}"
            f"QToolButton#titleBarClose:hover {{ background: {c.danger}; color: {c.text_primary}; }}"
            f"QWidget#titleBarSearchBox {{ border-radius: 9px; background: {c.surface_secondary}; border: 1px solid {c.divider}; }}"
            f"QLineEdit#titleBarSearchInput {{ border: 0; background: transparent; color: {c.text_primary}; font-size: {theme.fonts.body}px; }}"
            f"QLineEdit#titleBarSearchInput:focus {{ border: 0; }}"
        )
        for button, name in (
            (self.back_button, "back"), (self.forward_button, "forward"),
            (self.search_icon, "search"), (self.notifications_button, "notification"),
            (self.avatar_button, "user"),
            (self.minimize_button, "window_minimize"),
            (self.maximize_button, "window_restore" if self._window().isMaximized() else "window_maximize"),
            (self.close_button, "window_close"),
        ):
            button.setIcon(icon(name, theme))
            button.setIconSize(QSize(self._icon_size(name), self._icon_size(name)))
        self.settings_button.setIcon(fluent_settings_interactive_icon("general", theme, 18))
        self.settings_button.setIconSize(QSize(18, 18))
        theme_icon = "moon" if theme.mode == "dark" else "sun"
        self.theme_button.setIcon(icon(theme_icon, theme))
        self.theme_button.setIconSize(QSize(18, 18))
        self.view_options_button.setIcon(icon("more", theme))
        self.view_options_button.setIconSize(QSize(18, 18))
        target = "浅色模式" if theme.mode == "dark" else "深色模式"
        self.theme_button.setToolTip(f"切换到{target}")

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self._sidebar_spacer.setFixedWidth(
            self._theme.metrics.compact_sidebar_width if compact else self._theme.metrics.sidebar_width
        )
        self.search_box.setFixedSize(340 if compact else 460, 36)
        self._layout.setColumnMinimumWidth(3, 340 if compact else 460)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._window().isMaximized():
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = self._window().pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and self._window_origin is not None:
            self._window().move(self._window_origin + event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self._window_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _button(self, icon_name: str, tooltip: str, parent: QWidget, *, window_control: bool = False) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName("titleBarWindowControl" if window_control else "titleBarButton")
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFixedSize(28, self._theme.metrics.title_bar_height if window_control else 28)
        button.setIcon(icon(icon_name, self._theme))
        icon_size = self._icon_size(icon_name)
        button.setIconSize(QSize(icon_size, icon_size))
        return button

    @staticmethod
    def _icon_size(icon_name: str) -> int:
        if icon_name in {"settings", "sun", "moon", "notification", "user", "more"}:
            return 17
        if icon_name in {"back", "forward", "search"}:
            return 16
        return 15

    def _window(self):
        return self.window()

    def _minimize_window(self) -> None:
        self._window().showMinimized()

    def _toggle_maximized(self) -> None:
        window = self._window()
        window.showNormal() if window.isMaximized() else window.showMaximized()
        self.set_theme(self._theme)

    def _close_window(self) -> None:
        self._window().close()
