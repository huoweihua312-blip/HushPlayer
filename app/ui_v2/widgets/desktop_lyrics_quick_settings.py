"""Compact right-click settings for the desktop lyrics surface."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QPoint, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.models.desktop_lyrics_settings import (
    DESKTOP_LYRICS_COLORS,
    normalize_desktop_lyrics_font,
)
from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES, Theme
from app.ui_v2.widgets.settings_control_factory import (
    SettingSlider,
    SettingsActionButton,
    SettingsControlFactory,
    SettingsToggle,
)


_COLOR_LABELS = {
    "white": "白色",
    "black": "黑色",
    "yellow": "黄色",
    "blue": "蓝色",
    "green": "绿色",
    "pink": "粉色",
    "purple": "紫色",
}


class DesktopLyricsQuickSettingsPopover(QFrame):
    """Single-surface editor that emits normalized desktop-lyrics values."""

    value_changed = Signal(str, object)
    reset_position_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._theme = theme
        self._color_buttons: dict[str, QToolButton] = {}
        self.setObjectName("desktopLyricsQuickSettings")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(340)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build_ui()
        self.set_theme(theme)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("桌面歌词", self)
        self.title_label.setObjectName("desktopLyricsQuickSettingsTitle")
        self.close_button = QToolButton(self)
        self.close_button.setObjectName("desktopLyricsQuickSettingsClose")
        self.close_button.setText("×")
        self.close_button.setToolTip("关闭")
        self.close_button.setAccessibleName("关闭桌面歌词设置")
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setColumnMinimumWidth(0, 54)
        form.setColumnStretch(1, 1)

        color_label = self._label("颜色")
        self.color_row = QWidget(self)
        color_layout = QHBoxLayout(self.color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(6)
        for name in DESKTOP_LYRICS_COLORS:
            button = QToolButton(self.color_row)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedSize(28, 28)
            label = _COLOR_LABELS.get(name, name)
            button.setToolTip(label)
            button.setAccessibleName(f"歌词颜色：{label}")
            button.clicked.connect(
                lambda checked=False, color=name: self._select_color(color, checked)
            )
            self._color_buttons[name] = button
            color_layout.addWidget(button)
        color_layout.addStretch(1)
        form.addWidget(color_label, 0, 0)
        form.addWidget(self.color_row, 0, 1)

        self.font_combo = SettingsControlFactory.combo(
            tuple((family, family) for family in OPEN_FONT_FAMILIES),
            OPEN_FONT_FAMILIES[0],
            self._theme,
            self,
        )
        self.font_combo.setAccessibleName("桌面歌词字体")
        self.font_combo.currentIndexChanged.connect(self._font_changed)
        form.addWidget(self._label("字体"), 1, 0)
        form.addWidget(self.font_combo, 1, 1)

        self.font_size_slider = self._slider(22, 84, 42, " px", "桌面歌词字号")
        self.opacity_slider = self._slider(20, 100, 100, "%", "桌面歌词不透明度")
        self.width_slider = self._slider(420, 1600, 980, " px", "桌面歌词宽度")
        for row, (title, key, control) in enumerate(
            (
                ("字号", "floating_lyrics_font_size", self.font_size_slider),
                ("透明度", "floating_lyrics_opacity", self.opacity_slider),
                ("宽度", "floating_lyrics_width", self.width_slider),
            ),
            start=2,
        ):
            control.value_changed.connect(
                lambda value, setting=key: self.value_changed.emit(setting, int(value))
            )
            form.addWidget(self._label(title), row, 0)
            form.addWidget(control, row, 1)
        layout.addLayout(form)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.setSpacing(10)
        self.passthrough_toggle = SettingsControlFactory.switch(True, self._theme, self)
        self.passthrough_toggle.setAccessibleName("默认鼠标穿透")
        self.passthrough_toggle.toggled.connect(
            lambda checked: self.value_changed.emit(
                "floating_lyrics_passthrough", bool(checked)
            )
        )
        self.passthrough_label = QLabel("鼠标穿透", self)
        self.passthrough_label.setObjectName("desktopLyricsQuickSettingsLabel")
        self.reset_button = SettingsActionButton("恢复默认位置", self._theme, self)
        self.reset_button.clicked.connect(self.reset_position_requested)
        footer.addWidget(self.passthrough_toggle)
        footer.addWidget(self.passthrough_label)
        footer.addStretch(1)
        footer.addWidget(self.reset_button)
        layout.addLayout(footer)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("desktopLyricsQuickSettingsError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("desktopLyricsQuickSettingsLabel")
        return label

    def _slider(
        self,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str,
        accessible_name: str,
    ) -> SettingSlider:
        slider = SettingsControlFactory.slider_spin(
            minimum,
            maximum,
            value,
            suffix,
            self._theme,
            self,
        )
        slider.setAccessibleName(accessible_name)
        return slider

    def set_values(self, values: Mapping[str, object]) -> None:
        """Synchronize controls without emitting edit requests."""

        color = str(values.get("floating_lyrics_color", "white") or "white").casefold()
        if color not in DESKTOP_LYRICS_COLORS:
            color = "white"
        with QSignalBlocker(self.font_combo):
            family = normalize_desktop_lyrics_font(
                values.get("floating_lyrics_font_family")
            )
            self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(family)))
        self.font_size_slider.set_value(
            self._bounded_int(values, "floating_lyrics_font_size", 42, 22, 84)
        )
        self.opacity_slider.set_value(
            self._bounded_int(values, "floating_lyrics_opacity", 100, 20, 100)
        )
        self.width_slider.set_value(
            self._bounded_int(values, "floating_lyrics_width", 980, 420, 1600)
        )
        with QSignalBlocker(self.passthrough_toggle):
            self.passthrough_toggle.setChecked(
                bool(values.get("floating_lyrics_passthrough", True))
            )
        for name, button in self._color_buttons.items():
            with QSignalBlocker(button):
                button.setChecked(name == color)
        self._refresh_color_buttons()
        self.show_error("")

    @staticmethod
    def _bounded_int(
        values: Mapping[str, object], key: str, default: int, low: int, high: int
    ) -> int:
        try:
            value = int(values.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(low, min(high, value))

    def _select_color(self, color: str, checked: bool) -> None:
        if not checked or color not in DESKTOP_LYRICS_COLORS:
            return
        self._refresh_color_buttons()
        self.value_changed.emit("floating_lyrics_color", color)

    def _font_changed(self, _index: int) -> None:
        self.value_changed.emit(
            "floating_lyrics_font_family",
            normalize_desktop_lyrics_font(self.font_combo.currentData()),
        )

    def _refresh_color_buttons(self) -> None:
        for name, button in self._color_buttons.items():
            button.setText("")
            color = QColor(DESKTOP_LYRICS_COLORS[name])
            button.setStyleSheet(
                f"QToolButton {{ background: {color.name()}; "
                "border: 2px solid transparent; border-radius: 14px; font-weight: 700; }}"
                f"QToolButton:checked {{ border: 3px solid {self._theme.colors.primary_text}; }}"
                f"QToolButton:focus {{ border-color: {self._theme.colors.focus_ring}; }}"
            )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        colors = theme.colors
        self.setStyleSheet(
            f"QFrame#desktopLyricsQuickSettings {{ background: {colors.surface_elevated}; "
            f"border: 1px solid {colors.border}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QLabel#desktopLyricsQuickSettingsTitle {{ color: {colors.primary_text}; "
            f"font-size: {theme.fonts.section_title}px; font-weight: 650; }}"
            f"QLabel#desktopLyricsQuickSettingsLabel {{ color: {colors.secondary_text}; "
            f"font-size: {theme.fonts.control}px; }}"
            f"QLabel#desktopLyricsQuickSettingsError {{ color: {colors.danger}; "
            f"font-size: {theme.fonts.caption}px; }}"
            "QToolButton#desktopLyricsQuickSettingsClose { background: transparent; border: 0; "
            f"border-radius: 14px; color: {colors.secondary_text}; font-size: 18px; }}"
            f"QToolButton#desktopLyricsQuickSettingsClose:hover {{ background: {colors.hover_background}; "
            f"color: {colors.primary_text}; }}"
            f"QToolButton#desktopLyricsQuickSettingsClose:focus {{ border: 1px solid {colors.focus_ring}; }}"
        )
        self.font_combo.set_theme(theme)
        self.font_size_slider.set_theme(theme)
        self.opacity_slider.set_theme(theme)
        self.width_slider.set_theme(theme)
        self.passthrough_toggle.set_theme(theme)
        self.reset_button.set_theme(theme)
        self._refresh_color_buttons()

    def show_error(self, message: str) -> None:
        text = str(message or "").strip()
        self.error_label.setText(text)
        self.error_label.setVisible(bool(text))
        if self.isVisible():
            self.adjustSize()

    def show_anchored(self, anchor: QWidget) -> None:
        """Place the popup above the button and clamp it to the active screen."""

        self.adjustSize()
        anchor_top_left = anchor.mapToGlobal(QPoint(0, 0))
        anchor_bottom_right = anchor.mapToGlobal(
            QPoint(anchor.width() - 1, anchor.height() - 1)
        )
        screen = QGuiApplication.screenAt(anchor_top_left) or QGuiApplication.primaryScreen()
        x = anchor_bottom_right.x() - self.width() + 1
        y = anchor_top_left.y() - self.height() - 8
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left() + 8, min(x, available.right() - self.width() - 7))
            if y < available.top() + 8:
                y = anchor_bottom_right.y() + 9
            y = max(available.top() + 8, min(y, available.bottom() - self.height() - 7))
        self.move(x, y)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)
