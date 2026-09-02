"""Reusable controls and palette-safe ComboBox popup configuration."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractAnimation, QPropertyAnimation, QSize, Signal, QSignalBlocker, Qt, QRectF
from PySide6.QtGui import QColor, QFontMetrics, QPalette, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QPushButton,
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

    def __init__(
        self,
        theme: Theme,
        parent: QWidget | None = None,
        *,
        variant: str = "settings",
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._variant = "toolbar" if variant == "toolbar" else "settings"
        self._popup_open = False
        self.setObjectName("themedComboBox")
        self.setProperty("quietOrbitComboVariant", self._variant)
        self.setProperty("popupOpen", False)
        self.setProperty("focusVisible", False)
        self.setMinimumHeight(max(32, theme.metrics.control_height - 4))

    @property
    def popup_open(self) -> bool:
        return self._popup_open

    @property
    def variant(self) -> str:
        return self._variant

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setMinimumHeight(max(32, theme.metrics.control_height - 4))
        SettingsControlFactory.style_combo(self, theme)
        self.update()

    def showPopup(self) -> None:  # noqa: N802
        if not self.isEnabled():
            return
        self._set_popup_open(True)
        super().showPopup()

    def hidePopup(self) -> None:  # noqa: N802
        super().hidePopup()
        self._set_popup_open(False)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if (
            self._variant == "toolbar"
            and not self._popup_open
            and event.key() in {Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Space}
        ):
            self.showPopup()
            event.accept()
            return
        if self._variant == "toolbar" and self._popup_open and event.key() == Qt.Key.Key_Escape:
            self.hidePopup()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        if self._variant == "toolbar":
            self._set_visual_property("focusVisible", True)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        if self._variant == "toolbar":
            self._set_visual_property("focusVisible", False)

    def paintEvent(self, event) -> None:  # noqa: N802
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.subControls &= ~QStyle.SubControl.SC_ComboBoxArrow
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
        if (
            self._variant == "toolbar"
            and self.isEnabled()
            and (self._popup_open or self.hasFocus() or bool(self.property("focusVisible")))
        ):
            painter.save()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self._theme.colors.focus_ring), 1))
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                self._theme.metrics.radius_md,
                self._theme.metrics.radius_md,
            )
            painter.restore()
        arrow_rect = self.rect().adjusted(
            self.width() - self.arrow_hit_width,
            0,
            -4,
            0,
        )
        state = (
            "disabled"
            if not self.isEnabled()
            else "hover"
            if self._popup_open or self.hasFocus() or self.underMouse()
            else "normal"
        )
        icon("chevron_up" if self._popup_open else "chevron_down", self._theme, state).paint(
            painter,
            arrow_rect,
            Qt.AlignmentFlag.AlignCenter,
        )
        painter.end()

    def _set_popup_open(self, open_: bool) -> None:
        self._popup_open = bool(open_)
        self._set_visual_property("popupOpen", self._popup_open)

    def _set_visual_property(self, name: str, value: bool) -> None:
        self.setProperty(name, bool(value))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class ToolbarComboBox(ThemedComboBox):
    """The shared themed ComboBox tuned for compact action toolbars."""

    arrow_hit_width = 30

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(theme, parent, variant="toolbar")
        self.setObjectName("quietOrbitToolbarComboBox")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        height = max(34, theme.metrics.control_height)
        self.setFixedHeight(height)
        SettingsControlFactory.style_combo(self, theme)
        self.update()


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
            f"QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border: 1px solid {theme.colors.accent}; }}"
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


class SettingsToggle(QCheckBox):
    """Quiet Orbit switch with no native checkbox indicator."""

    def __init__(self, checked: bool, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("")
        self.setChecked(checked)
        self.setFixedSize(40, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._theme = theme
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setToolTip(self.toolTip())
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.0, 2.0, 38.0, 20.0)
        colors = self._theme.colors
        if not self.isEnabled():
            track = QColor(colors.border)
            thumb = QColor(colors.disabled_text)
        elif self.isChecked():
            track = QColor(colors.accent)
            thumb = QColor(colors.surface_elevated)
        else:
            track = QColor(colors.surface_pressed)
            thumb = QColor(colors.text_tertiary)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, 10, 10)
        center_x = 29.0 if self.isChecked() else 11.0
        painter.setBrush(thumb)
        painter.drawEllipse(QRectF(center_x - 7.0, 5.0, 14.0, 14.0))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colors.focus_ring), 1.0))
            painter.drawRoundedRect(QRectF(0.5, 1.5, 39.0, 21.0), 10.5, 10.5)
        painter.end()


class SliderSpinControl(QWidget):
    """A stable Quiet Orbit slider with a readable value label."""

    value_changed = Signal(int)

    def __init__(self, minimum: int, maximum: int, value: int, suffix: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("settingsSliderControl")
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.slider.setRange(minimum, maximum)
        self.value_label = QLabel(self)
        self.value_label.setObjectName("settingsSliderValue")
        self.value_label.setMinimumWidth(52)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._suffix = suffix
        self.slider.valueChanged.connect(self._from_slider)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)
        self.set_value(value)
        self.set_theme(theme)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, value: int) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(value)
        self._refresh_value_label()

    def _from_slider(self, value: int) -> None:
        self._refresh_value_label()
        self.value_changed.emit(value)

    def _refresh_value_label(self) -> None:
        self.value_label.setText(f"{self.slider.value()}{self._suffix}")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.slider.setFixedHeight(18)
        self.slider.setStyleSheet(
            f"QSlider {{ background: transparent; border: 0; padding: 0; }} "
            "QSlider::groove:horizontal { height: 4px; border: 0; border-radius: 2px; background: transparent; } "
            f"QSlider::sub-page:horizontal {{ background: {theme.colors.accent}; border-radius: 2px; }} "
            f"QSlider::add-page:horizontal {{ background: {theme.colors.border}; border: 0; border-radius: 2px; }} "
            f"QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border: 1px solid transparent; border-radius: 7px; background: {theme.colors.accent}; }} "
            f"QSlider::handle:horizontal:hover {{ background: {theme.colors.accent_hover}; }} "
            f"QSlider:disabled::groove:horizontal {{ background: {theme.colors.surface_pressed}; }} "
            f"QSlider:disabled::handle:horizontal {{ background: {theme.colors.disabled_text}; }} "
            f"QSlider:focus {{ background: transparent; border: 0; outline: 0; }} "
            f"QSlider:focus::handle:horizontal {{ border: 1px solid {theme.colors.focus_ring}; }}"
        )
        self.value_label.setStyleSheet(
            f"color: {theme.colors.secondary_text}; font-size: {theme.fonts.numeric}px;"
        )
        self._refresh_value_label()


SettingSlider = SliderSpinControl


class SettingsPathPicker(QWidget):
    """Bounded path display with injected browse/open actions."""

    path_changed = Signal(str)
    browse_requested = Signal()
    open_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._path = ""
        self.path_label = QLabel(self)
        self.path_label.setObjectName("settingsPathValue")
        self.path_label.setMinimumWidth(120)
        self.path_label.setWordWrap(False)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("settingsPathStatus")
        self.browse_button = QToolButton(self)
        self.browse_button.setText("浏览")
        self.browse_button.setToolTip("选择路径")
        self.clear_button = QToolButton(self)
        self.clear_button.setText("清除")
        self.clear_button.setToolTip("清除路径")
        self.clear_button.setAccessibleName("清除路径")
        self.open_button = QToolButton(self)
        self.open_button.setText("打开位置")
        self.open_button.setToolTip("打开路径位置")
        self.browse_button.clicked.connect(self.browse_requested)
        self.clear_button.clicked.connect(lambda: self.set_path(""))
        self.open_button.clicked.connect(self.open_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.path_label, 1)
        layout.addWidget(self.status_label, 0)
        layout.addWidget(self.browse_button, 0)
        layout.addWidget(self.clear_button, 0)
        layout.addWidget(self.open_button, 0)
        self.setMinimumWidth(260)
        self.setMaximumWidth(430)
        self.set_theme(theme)
        self.set_path("")

    def path(self) -> str:
        return self._path

    def set_path(self, path: str) -> None:
        normalized = str(path or "")
        changed = normalized != self._path
        self._path = normalized
        self._refresh_path_label()
        self.path_label.setToolTip(self._path)
        self.status_label.setText("" if not self._path else "路径不可用" if not Path(self._path).exists() else "")
        self.clear_button.setVisible(bool(self._path))
        self.open_button.setEnabled(bool(self._path))
        if changed:
            self.path_changed.emit(self._path)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_path_label()

    def _refresh_path_label(self) -> None:
        text = self._path or "未选择"
        available = max(40, self.path_label.width() - 16)
        self.path_label.setText(QFontMetrics(self.path_label.font()).elidedText(
            text,
            Qt.TextElideMode.ElideMiddle,
            available,
        ))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QLabel#settingsPathValue {{ min-height: {theme.metrics.control_height - 4}px; padding: 0 8px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; }} "
            f"QLabel#settingsPathStatus {{ color: {c.warning}; font-size: {theme.fonts.caption}px; }} "
            f"QToolButton {{ min-height: {theme.metrics.control_height - 4}px; padding: 0 8px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; font-weight: 400; }} "
            f"QToolButton:hover {{ background: {c.hover_background}; }} QToolButton[hushKeyboardFocus=\"true\"]:focus {{ border: 1px solid {c.focus_ring}; }} QToolButton:disabled {{ color: {c.disabled_text}; }}"
        )


class SettingsActionButton(QPushButton):
    """Compact non-primary action used inside a setting section."""

    def __init__(self, text: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(max(32, theme.metrics.control_height - 4))
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        c = theme.colors
        self.setStyleSheet(
            f"QPushButton {{ min-height: {theme.metrics.control_height - 4}px; padding: 0 12px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; font-weight: 400; }} "
            f"QPushButton:hover {{ background: {c.hover_background}; }} QPushButton:pressed {{ background: {c.surface_pressed}; }} QPushButton[hushKeyboardFocus=\"true\"]:focus {{ border: 1px solid {c.focus_ring}; }} QPushButton:disabled {{ color: {c.disabled_text}; }}"
        )


class SettingsDangerAction(SettingsActionButton):
    """Quiet danger action; confirmation is owned by the overlay."""

    def set_theme(self, theme: Theme) -> None:
        c = theme.colors
        self.setStyleSheet(
            f"QPushButton {{ min-height: {theme.metrics.control_height - 4}px; padding: 0 12px; border: 1px solid {c.danger}; border-radius: {theme.metrics.radius_sm}px; background: transparent; color: {c.danger}; font-weight: 400; }} "
            f"QPushButton:hover {{ background: {c.hover_background}; }} QPushButton:pressed {{ background: {c.surface_pressed}; }} QPushButton[hushKeyboardFocus=\"true\"]:focus {{ border: 1px solid {c.focus_ring}; }} QPushButton:disabled {{ color: {c.disabled_text}; border-color: {c.border}; }}"
        )


class SettingsControlFactory:
    """Creates settings controls with a consistent V2 surface and popup palette."""

    @staticmethod
    def switch(checked: bool, theme: Theme, parent: QWidget | None = None) -> SettingsToggle:
        control = SettingsToggle(checked, theme, parent)
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
    def style_switch(control: SettingsToggle, theme: Theme) -> None:
        control.set_theme(theme)

    @staticmethod
    def style_combo(control: QComboBox, theme: Theme) -> None:
        c = theme.colors
        if isinstance(control, ThemedComboBox):
            control._theme = theme
            if control.variant != "toolbar":
                control.setMinimumHeight(max(32, theme.metrics.control_height - 4))
        if isinstance(control, ToolbarComboBox):
            height = max(34, theme.metrics.control_height)
            content_height = height - 2
            radius = theme.metrics.radius_md
            selector = 'QComboBox[quietOrbitComboVariant="toolbar"]'
            control.setStyleSheet(
                f"{selector} {{ min-height: {content_height}px; max-height: {content_height}px; padding: 0 34px 0 {theme.metrics.spacing_md}px; "
                f"border: 1px solid transparent; border-radius: {radius}px; background: {c.surface_secondary}; "
                f"color: {c.primary_text}; font-size: {theme.fonts.control}px; }} "
                f"{selector}:hover {{ border-color: {c.divider}; background: {c.hover_background}; }} "
                f"{selector}:pressed {{ border-color: transparent; background: {c.surface_pressed}; }} "
                f"{selector}:focus, {selector}[focusVisible=\"true\"], {selector}:on, {selector}[popupOpen=\"true\"] {{ border-color: {c.focus_ring}; background: {c.surface_secondary}; }} "
                f"{selector}:disabled {{ border-color: transparent; background: {c.surface_secondary}; color: {c.disabled_text}; }} "
                f"{selector}::drop-down {{ border: 0; width: {control.arrow_hit_width}px; background: transparent; }} "
                f"{selector}::down-arrow {{ image: none; width: 0; height: 0; }}"
            )
        else:
            control.setStyleSheet(
                f"QComboBox {{ min-height: {max(32, theme.metrics.control_height - 4)}px; min-width: 150px; padding: 0 38px 0 8px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; }} "
                f"QComboBox:hover {{ border-color: {c.border_strong}; }} QComboBox:focus {{ border: 1px solid {c.accent}; }} "
                f"QComboBox::drop-down {{ border: 0; width: {ThemedComboBox.arrow_hit_width}px; }} QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}"
            )
        view = control.view()
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, _opaque(c.surface_elevated))
        palette.setColor(QPalette.ColorRole.Window, _opaque(c.surface_elevated))
        palette.setColor(QPalette.ColorRole.Text, _opaque(c.primary_text))
        palette.setColor(QPalette.ColorRole.Highlight, _opaque(c.selected_background))
        palette.setColor(QPalette.ColorRole.HighlightedText, _opaque(c.primary_text))
        view.setPalette(palette)
        view.setAutoFillBackground(True)
        view.setStyleSheet(
            f"QAbstractItemView {{ background: {c.surface_elevated}; color: {c.primary_text}; border: 1px solid {c.border}; selection-background-color: {c.selected_background}; selection-color: {c.primary_text}; outline: 0; }} "
            f"QAbstractItemView::item {{ min-height: {theme.metrics.control_height - 4}px; padding: 0 8px; background: {c.surface_elevated}; }} "
            f"QAbstractItemView::item:hover {{ background: {c.hover_background}; }} "
            f"QAbstractItemView::item:selected {{ background: {c.selected_background}; }} "
            f"QScrollBar:vertical {{ width: 8px; background: {c.surface_elevated}; }} QScrollBar::handle:vertical {{ min-height: 24px; border-radius: 4px; background: {c.border_strong}; }}"
        )


def _opaque(value: str):
    color = QColor(value)
    color.setAlpha(255)
    return color
