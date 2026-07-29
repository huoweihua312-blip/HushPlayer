"""Reusable controls and palette-safe ComboBox popup configuration."""

from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation, QPropertyAnimation, QSize, Signal, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QToolButton,
    QWidget,
)

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme


class ThemedComboBox(QComboBox):
    """A V2 ComboBox that paints a shared chevron instead of the native arrow."""

    arrow_hit_width = 34
    native_arrow_suppressed = True

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._popup_open = False
        self.setObjectName("themedComboBox")
        self.setMinimumHeight(max(32, theme.metrics.control_height - 4))

    @property
    def popup_open(self) -> bool:
        return self._popup_open

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setMinimumHeight(max(32, theme.metrics.control_height - 4))
        self.update()

    def showPopup(self) -> None:  # noqa: N802
        self._popup_open = True
        self.update()
        super().showPopup()

    def hidePopup(self) -> None:  # noqa: N802
        super().hidePopup()
        self._popup_open = False
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.subControls &= ~QStyle.SubControl.SC_ComboBoxArrow
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
        arrow_rect = self.rect().adjusted(
            self.width() - self.arrow_hit_width,
            0,
            -4,
            0,
        )
        state = "disabled" if not self.isEnabled() else "hover" if self.underMouse() else "normal"
        icon("chevron_up" if self._popup_open else "chevron_down", self._theme, state).paint(
            painter,
            arrow_rect,
            Qt.AlignmentFlag.AlignCenter,
        )
        painter.end()


class ThemedDisclosureButton(QToolButton):
    """A compact, optionally animated disclosure backed by the V2 chevrons."""

    expanded_changed = Signal(bool)

    def __init__(self, text: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._content: QWidget | None = None
        self._reduce_motion = False
        self._animation = QPropertyAnimation(self)
        self._animation.setPropertyName(b"maximumHeight")
        self._animation.setDuration(130)
        self._animation.finished.connect(self._complete_animation)
        self.setText(text)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._set_expanded)
        self.set_theme(theme)

    @property
    def uses_v2_chevron(self) -> bool:
        return True

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setIcon(icon("chevron_down" if self.isChecked() else "chevron_right", theme))
        self.setIconSize(QSize(14, 14))
        self.setStyleSheet(
            "QToolButton { min-height: 32px; border: 0; border-radius: 5px; padding: 0 6px; "
            f"background: transparent; color: {theme.colors.primary_text}; font-weight: 600; text-align: left; }}"
            f"QToolButton:hover {{ background: {theme.colors.hover_background}; }}"
            f"QToolButton:focus {{ border: 1px solid {theme.colors.accent}; }}"
        )

    def set_reduce_motion(self, enabled: bool) -> None:
        self._reduce_motion = bool(enabled)

    def bind_content(self, content: QWidget) -> None:
        self._content = content
        content.setVisible(self.isChecked())
        content.setMaximumHeight(content.sizeHint().height() if self.isChecked() else 0)

    def _set_expanded(self, expanded: bool) -> None:
        self.setIcon(icon("chevron_down" if expanded else "chevron_right", self._theme))
        content = self._content
        if content is None:
            self.expanded_changed.emit(expanded)
            return
        target = max(1, content.sizeHint().height())
        if self._reduce_motion:
            self._animation.stop()
            content.setVisible(expanded)
            content.setMaximumHeight(target if expanded else 0)
        else:
            self._animation.stop()
            if expanded:
                content.show()
            self._animation.setTargetObject(content)
            self._animation.setStartValue(content.maximumHeight())
            self._animation.setEndValue(target if expanded else 0)
            self._animation.start()
        self.expanded_changed.emit(expanded)

    def _complete_animation(self) -> None:
        if self._content is not None and not self.isChecked():
            self._content.hide()


class SliderSpinControl(QWidget):
    """A slider plus spin box with a single value signal and no feedback loop."""

    value_changed = Signal(int)

    def __init__(self, minimum: int, maximum: int, value: int, suffix: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.spin = QSpinBox(self)
        self.slider.setRange(minimum, maximum)
        self.spin.setRange(minimum, maximum)
        self.spin.setSuffix(suffix)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.set_value(value)
        self.set_theme(theme)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, value: int) -> None:
        with QSignalBlocker(self.slider), QSignalBlocker(self.spin):
            self.slider.setValue(value)
            self.spin.setValue(value)

    def _from_slider(self, value: int) -> None:
        with QSignalBlocker(self.spin):
            self.spin.setValue(value)
        self.value_changed.emit(value)

    def _from_spin(self, value: int) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(value)
        self.value_changed.emit(value)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.slider.setStyleSheet(f"QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {theme.colors.border}; }} QSlider::sub-page:horizontal {{ background: {theme.colors.accent}; border-radius: 2px; }} QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border-radius: 7px; background: {theme.colors.accent}; }}")
        self.spin.setStyleSheet(f"min-height: {theme.metrics.control_height - 4}px; min-width: 82px; padding: 0 6px; border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.input_background}; color: {theme.colors.primary_text};")


class SettingsControlFactory:
    """Creates settings controls with a consistent V2 surface and popup palette."""

    @staticmethod
    def switch(checked: bool, theme: Theme, parent: QWidget | None = None) -> QCheckBox:
        control = QCheckBox(parent)
        control.setChecked(checked)
        control.setText("")
        SettingsControlFactory.style_switch(control, theme)
        return control

    @staticmethod
    def combo(items: tuple[tuple[str, str], ...], value: str, theme: Theme, parent: QWidget | None = None) -> ThemedComboBox:
        control = ThemedComboBox(theme, parent)
        for text, data in items:
            control.addItem(text, data)
        position = control.findData(value)
        control.setCurrentIndex(max(0, position))
        SettingsControlFactory.style_combo(control, theme)
        return control

    @staticmethod
    def slider_spin(minimum: int, maximum: int, value: int, suffix: str, theme: Theme, parent: QWidget | None = None) -> SliderSpinControl:
        return SliderSpinControl(minimum, maximum, value, suffix, theme, parent)

    @staticmethod
    def style_switch(control: QCheckBox, theme: Theme) -> None:
        control.setStyleSheet(
            f"QCheckBox::indicator {{ width: 36px; height: 20px; border-radius: 10px; background: {theme.colors.border_strong}; }} "
            f"QCheckBox::indicator:checked {{ background: {theme.colors.accent}; }} "
            f"QCheckBox::indicator:disabled {{ background: {theme.colors.border}; }}"
        )

    @staticmethod
    def style_combo(control: QComboBox, theme: Theme) -> None:
        c = theme.colors
        if isinstance(control, ThemedComboBox):
            control.set_theme(theme)
        control.setStyleSheet(
            f"QComboBox {{ min-height: {max(32, theme.metrics.control_height - 4)}px; min-width: 150px; padding: 0 38px 0 8px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.input_background}; color: {c.primary_text}; }} "
            f"QComboBox:hover {{ border-color: {c.border_strong}; }} QComboBox:focus {{ border: 1px solid {c.accent}; }} "
            f"QComboBox::drop-down {{ border: 0; width: {ThemedComboBox.arrow_hit_width}px; }} QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}"
        )
        view = control.view()
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, _opaque(c.elevated_background))
        palette.setColor(QPalette.ColorRole.Window, _opaque(c.elevated_background))
        palette.setColor(QPalette.ColorRole.Text, _opaque(c.primary_text))
        palette.setColor(QPalette.ColorRole.Highlight, _opaque(c.selected_background))
        palette.setColor(QPalette.ColorRole.HighlightedText, _opaque(c.primary_text))
        view.setPalette(palette)
        view.setAutoFillBackground(True)
        view.setStyleSheet(
            f"QAbstractItemView {{ background: {c.elevated_background}; color: {c.primary_text}; border: 1px solid {c.border}; selection-background-color: {c.selected_background}; selection-color: {c.primary_text}; outline: 0; }} "
            f"QAbstractItemView::item {{ min-height: {theme.metrics.control_height - 4}px; padding: 0 8px; background: {c.elevated_background}; }} "
            f"QAbstractItemView::item:hover {{ background: {c.hover_background}; }} "
            f"QAbstractItemView::item:selected {{ background: {c.selected_background}; }} "
            f"QScrollBar:vertical {{ width: 8px; background: {c.elevated_background}; }} QScrollBar::handle:vertical {{ min-height: 24px; border-radius: 4px; background: {c.border_strong}; }}"
        )


def _opaque(value: str):
    color = QColor(value)
    color.setAlpha(255)
    return color
