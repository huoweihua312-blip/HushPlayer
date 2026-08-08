"""A compact, opaque settings sheet for the formal immersive lyrics page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QScrollArea, QSlider, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_control_factory import SettingsControlFactory, ThemedComboBox, ThemedDisclosureButton


class ImmersiveSettingsPanel(QFrame):
    """A persistent panel whose surfaces never inherit the artwork alpha."""

    changed = Signal()
    exit_requested = Signal()
    closed = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._value_labels: dict[QSlider, QLabel] = {}
        self.setObjectName("immersiveSettingsPanel")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.header_widget = QWidget(self)
        self.header_widget.setObjectName("immersiveSettingsHeader")
        self.title_label = QLabel("沉浸歌词", self.header_widget)
        self.close_button = QToolButton(self.header_widget)
        self.close_button.setText("关闭")
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(14, 12, 10, 10)
        header.setSpacing(8)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.close_button)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("immersiveSettingsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setObjectName("immersiveSettingsViewport")
        self.scroll_area.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.content_widget = QWidget(self.scroll_area)
        self.content_widget.setObjectName("immersiveSettingsContent")
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        form = QFormLayout(self.content_widget)
        form.setContentsMargins(14, 8, 14, 12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.theme_combo = self._combo((("跟随窗口", ""), ("深色", "dark"), ("浅色", "light")))
        self.background_combo = self._combo((("封面背景", "artwork"), ("渐变背景", "gradient"), ("纯色背景", "solid"), ("透明背景", "transparent")))
        self.background_opacity_slider = self._slider(0, 100)
        self.overlay_strength_slider = self._slider(15, 85)
        self.control_surface_opacity_slider = self._slider(20, 80)
        self.global_lyric_scale_slider = self._slider(75, 160)
        self.active_font_slider = self._slider(28, 72)
        self.normal_font_slider = self._slider(18, 52)
        self.translation_font_slider = self._slider(11, 30)
        self.romanization_font_slider = self._slider(11, 30)
        self.inactive_opacity_slider = self._slider(40, 92)
        self.weight_combo = self._combo((("Regular", "Regular"), ("Medium", "Medium"), ("Semibold", "Semibold"), ("Bold", "Bold")))
        self.text_protection_combo = self._combo((("无", "无"), ("轻微阴影", "轻微阴影"), ("柔和描边", "柔和描边")))
        self.auto_hide_check = QToolButton(self.content_widget)
        self.auto_hide_check.setText("自动隐藏控制层")
        self.auto_hide_check.setCheckable(True)
        self._add_section(form, "外观")
        for label, control in (
            ("主题", self.theme_combo),
            ("背景", self.background_combo),
            ("背景透明度", self._slider_row(self.background_opacity_slider, "%")),
            ("遮罩强度", self._slider_row(self.overlay_strength_slider, "%")),
            ("控制层透明度", self._slider_row(self.control_surface_opacity_slider, "%")),
        ):
            form.addRow(label, control)
        self._add_section(form, "歌词")
        for label, control in (
            ("整体歌词大小", self._slider_row(self.global_lyric_scale_slider, "%")),
            ("非当前歌词", self._slider_row(self.inactive_opacity_slider, "%")),
            ("字重", self.weight_combo),
            ("文字保护", self.text_protection_combo),
            ("控制层", self.auto_hide_check),
        ):
            form.addRow(label, control)
        self.advanced_disclosure = ThemedDisclosureButton("高级字号", theme, self.content_widget)
        self.advanced_disclosure.setObjectName("immersiveAdvancedFontDisclosure")
        self.advanced_content = QWidget(self.content_widget)
        self.advanced_content.setObjectName("immersiveAdvancedFontContent")
        advanced_form = QFormLayout(self.advanced_content)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_form.setHorizontalSpacing(12)
        advanced_form.setVerticalSpacing(10)
        for label, control in (
            ("当前歌词", self._slider_row(self.active_font_slider, " px")),
            ("普通歌词", self._slider_row(self.normal_font_slider, " px")),
            ("翻译", self._slider_row(self.translation_font_slider, " px")),
            ("罗马音", self._slider_row(self.romanization_font_slider, " px")),
        ):
            advanced_form.addRow(label, control)
        form.addRow(self.advanced_disclosure)
        form.addRow(self.advanced_content)
        self.advanced_disclosure.bind_content(self.advanced_content)
        self.scroll_area.setWidget(self.content_widget)
        self.footer_widget = QWidget(self)
        self.footer_widget.setObjectName("immersiveSettingsFooter")
        self.exit_immersive_button = QToolButton(self.footer_widget)
        self.exit_immersive_button.setText("退出沉浸")
        footer = QHBoxLayout(self.footer_widget)
        footer.setContentsMargins(14, 8, 14, 12)
        footer.addWidget(self.exit_immersive_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header_widget)
        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(self.footer_widget)
        self.close_button.clicked.connect(self.request_close)
        self.exit_immersive_button.clicked.connect(self.exit_requested)
        for combo in (self.theme_combo, self.background_combo, self.weight_combo, self.text_protection_combo):
            combo.currentIndexChanged.connect(self.changed)
        for slider in (
            self.background_opacity_slider,
            self.overlay_strength_slider,
            self.control_surface_opacity_slider,
            self.global_lyric_scale_slider,
            self.active_font_slider,
            self.normal_font_slider,
            self.translation_font_slider,
            self.romanization_font_slider,
            self.inactive_opacity_slider,
        ):
            slider.valueChanged.connect(self.changed)
        self.auto_hide_check.toggled.connect(self.changed)
        self.setMinimumWidth(320)
        self.setMaximumWidth(380)
        self.set_theme(theme)

    @property
    def surface_alpha(self) -> int:
        return 255

    def _combo(self, items: tuple[tuple[str, str], ...]) -> QComboBox:
        combo = ThemedComboBox(self._theme, self)
        for label, value in items:
            combo.addItem(label, value)
        view = combo.view()
        view.setObjectName("immersiveSettingsComboPopup")
        view.setAutoFillBackground(True)
        view.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        view.viewport().setAutoFillBackground(True)
        view.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        return combo

    def _slider(self, low: int, high: int) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(low, high)
        return slider

    def _slider_row(self, slider: QSlider, suffix: str) -> QWidget:
        host = QWidget(self.content_widget)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        value_label = QLabel(host)
        value_label.setObjectName("immersiveSettingsValue")
        value_label.setMinimumWidth(42)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label)
        self._value_labels[slider] = value_label
        slider.valueChanged.connect(lambda value, label=value_label, unit=suffix: label.setText(f"{value}{unit}"))
        value_label.setText(f"{slider.value()}{suffix}")
        return host

    def _add_section(self, form: QFormLayout, title: str) -> None:
        label = QLabel(title, self.content_widget)
        label.setObjectName("immersiveSettingsSection")
        form.addRow(label)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        surface = QColor(c.elevated_background)
        input_surface = QColor(c.input_background)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, surface)
        palette.setColor(QPalette.ColorRole.Base, surface)
        palette.setColor(QPalette.ColorRole.AlternateBase, surface)
        palette.setColor(QPalette.ColorRole.Text, QColor(c.primary_text))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(c.primary_text))
        palette.setColor(QPalette.ColorRole.Button, surface)
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(c.primary_text))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(c.selected_background))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c.primary_text))
        for widget in (self, self.header_widget, self.scroll_area, self.scroll_area.viewport(), self.content_widget, self.footer_widget):
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
        self.setStyleSheet(
            f"QFrame#immersiveSettingsPanel {{ background: {c.elevated_background}; border: 1px solid {c.border}; border-radius: 8px; }}"
            f"QWidget#immersiveSettingsHeader {{ background: {c.elevated_background}; border-bottom: 1px solid {c.border}; }}"
            f"QWidget#immersiveSettingsFooter {{ background: {c.elevated_background}; border-top: 1px solid {c.border}; }}"
            f"QScrollArea#immersiveSettingsScrollArea, QScrollArea#immersiveSettingsScrollArea QWidget#immersiveSettingsViewport, QWidget#immersiveSettingsContent {{ background: {c.elevated_background}; color: {c.primary_text}; border: 0; }}"
            f"QLabel {{ background: transparent; color: {c.secondary_text}; font-size: {theme.fonts.caption}px; }}"
            f"QLabel#immersiveSettingsSection {{ padding-top: 10px; color: {c.primary_text}; font-size: {theme.fonts.secondary}px; font-weight: 600; }}"
            f"QLabel#immersiveSettingsValue {{ color: {c.subtle_text}; }}"
            f"QToolButton {{ min-height: 30px; border: 0; border-radius: 6px; padding: 0 8px; color: {c.secondary_text}; background: transparent; }}"
            f"QToolButton:hover {{ background: {c.hover_background}; color: {c.primary_text}; }}"
            f"QToolButton:checked {{ color: {c.accent}; }}"
            f"QComboBox {{ min-height: 28px; padding: 0 8px; border: 1px solid {c.border}; border-radius: 5px; background: {c.input_background}; color: {c.primary_text}; }}"
            f"QComboBox:hover {{ border-color: {c.border_strong}; }}"
            f"QComboBox:disabled, QToolButton:disabled {{ color: {c.disabled_text}; }}"
            f"QSlider::groove:horizontal {{ height: 3px; border: 0; border-radius: 1px; background: {c.border_strong}; }}"
            f"QSlider::sub-page:horizontal {{ border-radius: 1px; background: {c.accent}; }}"
            f"QSlider::handle:horizontal {{ width: 10px; margin: -4px 0; border: 0; border-radius: 5px; background: {c.primary_text}; }}"
            "QScrollBar:vertical { width: 8px; border: 0; background: transparent; margin: 4px 2px; }"
            f"QScrollBar::handle:vertical {{ min-height: 28px; border-radius: 4px; background: {c.border_strong}; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {c.secondary_text}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {c.primary_text};")
        self.advanced_disclosure.set_theme(theme)
        for combo in (self.theme_combo, self.background_combo, self.weight_combo, self.text_protection_combo):
            SettingsControlFactory.style_combo(combo, theme)
            view = combo.view()
            popup_palette = QPalette(palette)
            popup_palette.setColor(QPalette.ColorRole.Base, surface)
            popup_palette.setColor(QPalette.ColorRole.Window, surface)
            popup_palette.setColor(QPalette.ColorRole.Text, QColor(c.primary_text))
            popup_palette.setColor(QPalette.ColorRole.Highlight, QColor(c.selected_background))
            popup_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c.primary_text))
            view.setPalette(popup_palette)
            view.viewport().setPalette(popup_palette)
            view.setAutoFillBackground(True)
            view.viewport().setAutoFillBackground(True)
            view.setStyleSheet(
                f"QAbstractItemView#immersiveSettingsComboPopup {{ background: {surface.name()}; color: {c.primary_text}; border: 1px solid {c.border}; outline: 0; }}"
                f"QAbstractItemView#immersiveSettingsComboPopup::item {{ min-height: 28px; padding: 0 8px; background: {surface.name()}; color: {c.primary_text}; }}"
                f"QAbstractItemView#immersiveSettingsComboPopup::item:hover {{ background: {c.hover_background}; }}"
                f"QAbstractItemView#immersiveSettingsComboPopup::item:selected {{ background: {c.selected_background}; color: {c.primary_text}; }}"
                "QScrollBar:vertical { width: 8px; background: transparent; }"
                f"QScrollBar::handle:vertical {{ min-height: 24px; border-radius: 4px; background: {c.border_strong}; }}"
            )

    def set_reduce_motion(self, enabled: bool) -> None:
        self.advanced_disclosure.set_reduce_motion(enabled)

    def request_close(self) -> None:
        self.hide()
        self.closed.emit()

    def any_popup_open(self) -> bool:
        return any(combo.view().isVisible() for combo in (self.theme_combo, self.background_combo, self.weight_combo, self.text_protection_combo))

    def close_popup(self) -> bool:
        for combo in (self.theme_combo, self.background_combo, self.weight_combo, self.text_protection_combo):
            if combo.view().isVisible():
                combo.hidePopup()
                return True
        return False
