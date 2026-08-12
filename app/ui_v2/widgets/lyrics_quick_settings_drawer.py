"""Compact bridge-backed settings drawer for immersive lyrics."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.ui_v2.adapters.legacy_settings_bridge import LegacySettingsBridge, SettingsBridgeError
from app.ui_v2.models.settings_edit_session import SettingsEditSession
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.immersive_side_drawer import ImmersiveFloatingPanel
from app.ui_v2.widgets.settings_control_factory import SettingsControlFactory, SliderSpinControl, ThemedComboBox


_BACKGROUND_MODES = (
    ("封面背景", "cover"),
    ("纯色背景", "default"),
    ("半透明背景", "translucent"),
    ("自定义图片", "custom"),
)


class _QuickSettingRow(QFrame):
    """A compact row that leaves room for lyric preview beside the drawer."""

    def __init__(self, title: str, detail: str, control: QWidget, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("lyricsQuickSettingRow")
        self.title_label = QLabel(title, self)
        self.detail_label = QLabel(detail, self)
        self.detail_label.setWordWrap(True)
        labels = QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(2)
        labels.addWidget(self.title_label)
        labels.addWidget(self.detail_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 9, 0, 9)
        layout.setSpacing(12)
        layout.addLayout(labels, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self.setStyleSheet(
            f"QFrame#lyricsQuickSettingRow {{ background: transparent; border-bottom: 1px solid {theme.colors.border}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; font-weight: 500; color: {theme.colors.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"
        )


class LyricsQuickSettingsContent(QWidget):
    """Only the seven established immersive lyrics settings."""

    changed = Signal(str, object)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.controls: dict[str, QWidget] = {}
        self.setObjectName("lyricsQuickSettingsContent")
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("lyricsQuickSettingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setAutoFillBackground(False)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body = QWidget(self.scroll)
        body.setObjectName("lyricsQuickSettingsBody")
        body.setAutoFillBackground(False)
        body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        body.setStyleSheet("QWidget#lyricsQuickSettingsBody { background: transparent; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 0, 18, 12)
        body_layout.setSpacing(0)
        self._add_switch(body_layout, "immersive_auto_hide_ui", "自动隐藏控制层", "播放时静止后隐藏控制层。")
        self._add_combo(body_layout, "immersive_background_mode", "背景模式", "使用当前已保存的背景来源。", _BACKGROUND_MODES)
        self._add_slider(body_layout, "immersive_background_blur", "背景模糊", "保留正式背景模糊范围。", 0, 40, " px")
        self._add_slider(body_layout, "immersive_background_darkness", "背景暗度", "仅影响沉浸背景。", 0, 90, "%")
        self._add_slider(body_layout, "immersive_background_image_opacity", "背景图片不透明度", "仅影响背景图层。", 20, 100, "%")
        self._add_slider(body_layout, "immersive_background_transparency", "背景透明度", "沿用现有透明背景语义。", 0, 85, "%")
        self._add_slider(body_layout, "immersive_lyrics_font_scale", "沉浸歌词字号比例", "实时预览当前歌词大小。", 70, 160, "%")
        body_layout.addStretch(1)
        self.scroll.setWidget(body)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        self.set_theme(theme)

    def _add_switch(self, layout: QVBoxLayout, key: str, title: str, detail: str) -> None:
        control = SettingsControlFactory.switch(False, self._theme, self)
        control.toggled.connect(lambda value, path=key: self.changed.emit(path, bool(value)))
        self.controls[key] = control
        layout.addWidget(_QuickSettingRow(title, detail, control, self._theme, self))

    def _add_combo(self, layout: QVBoxLayout, key: str, title: str, detail: str, items: tuple[tuple[str, str], ...]) -> None:
        control = SettingsControlFactory.combo(items, items[0][1], self._theme, self)
        control.currentIndexChanged.connect(
            lambda _index, path=key, widget=control: self.changed.emit(path, str(widget.currentData()))
        )
        self.controls[key] = control
        layout.addWidget(_QuickSettingRow(title, detail, control, self._theme, self))

    def _add_slider(self, layout: QVBoxLayout, key: str, title: str, detail: str, minimum: int, maximum: int, suffix: str) -> None:
        control = SettingsControlFactory.slider_spin(minimum, maximum, minimum, suffix, self._theme, self)
        control.value_changed.connect(lambda value, path=key: self.changed.emit(path, int(value)))
        self.controls[key] = control
        layout.addWidget(_QuickSettingRow(title, detail, control, self._theme, self))

    def set_values(self, bridge: LegacySettingsBridge, session: SettingsEditSession) -> None:
        for key, control in self.controls.items():
            value = bridge.value(session.working_snapshot, key)
            with QSignalBlocker(control):
                if isinstance(control, QCheckBox):
                    control.setChecked(bool(value))
                elif isinstance(control, ThemedComboBox):
                    control.setCurrentIndex(max(0, control.findData(str(value))))
                elif isinstance(control, SliderSpinControl):
                    control.set_value(int(value))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for row in self.findChildren(_QuickSettingRow):
            row.set_theme(theme)
        for control in self.controls.values():
            if isinstance(control, QCheckBox):
                SettingsControlFactory.style_switch(control, theme)
                control.setStyleSheet(
                    control.styleSheet()
                    + f" QCheckBox:focus::indicator {{ border: 1px solid {theme.colors.focus_ring}; }}"
                )
            elif isinstance(control, ThemedComboBox):
                SettingsControlFactory.style_combo(control, theme)
                control.setStyleSheet(
                    control.styleSheet()
                    + f" QComboBox:focus {{ border: 1px solid {theme.colors.focus_ring}; }}"
                )
            elif isinstance(control, SliderSpinControl):
                control.set_theme(theme)
                control.slider.setStyleSheet(
                    control.slider.styleSheet()
                    + f" QSlider:focus::handle:horizontal {{ border: 2px solid {theme.colors.focus_ring}; }}"
                )
                control.spin.setStyleSheet(
                    control.spin.styleSheet()
                    + f" QSpinBox:focus {{ border: 1px solid {theme.colors.focus_ring}; }}"
                )
        self.scroll.setStyleSheet(
            "QScrollArea { border: 0; background: transparent; } "
            "QAbstractScrollArea::viewport { background: transparent; } "
            "QScrollBar:vertical { width: 8px; background: transparent; } "
            f"QScrollBar::handle:vertical {{ min-height: 28px; border-radius: 4px; background: {theme.colors.border_strong}; }} "
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )


class LyricsQuickSettingsFloatingPanel(ImmersiveFloatingPanel):
    """Stable floating panel with a fresh bridge-backed edit session per opening."""

    saved = Signal(object)

    def __init__(
        self,
        bridge: LegacySettingsBridge,
        theme: Theme,
        *,
        preview_callback: Callable[[dict[str, Any]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("歌词设置", theme, parent)
        self.bridge = bridge
        self._theme = theme
        self._preview_callback = preview_callback
        self._session: SettingsEditSession | None = None
        self.content = LyricsQuickSettingsContent(theme, self.content_host)
        self.set_content(self.content)
        self.content.changed.connect(self._value_changed)
        self.footer = QFrame(self)
        self.footer.setObjectName("lyricsQuickSettingsFooter")
        self.status_label = QLabel(self.footer)
        self.restore_button = QPushButton("恢复", self.footer)
        self.cancel_button = QPushButton("取消", self.footer)
        self.save_button = QPushButton("保存", self.footer)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(18, 10, 18, 10)
        footer_layout.setSpacing(8)
        footer_layout.addWidget(self.status_label, 1)
        footer_layout.addWidget(self.restore_button)
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.save_button)
        self.set_footer(self.footer)
        self.restore_button.clicked.connect(self.restore_open_values)
        self.cancel_button.clicked.connect(self.cancel_and_close)
        self.save_button.clicked.connect(self.save_and_close)
        self.closed.connect(self.cancel_and_close)
        self.set_theme(theme)
        self.hide()

    @property
    def session(self) -> SettingsEditSession | None:
        return self._session

    @property
    def is_dirty(self) -> bool:
        return bool(self._session and self._session.is_dirty)

    def open(self) -> None:  # noqa: A003
        self._session = SettingsEditSession.open(self.bridge.read_snapshot())
        self.content.set_values(self.bridge, self._session)
        self._refresh_state()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _value_changed(self, key: str, value: object) -> None:
        if self._session is None or not self._session.set(key, value):
            return
        self._session.mark_previewed(key)
        if self._preview_callback is not None:
            self._preview_callback(self._session.working_snapshot.to_dict())
        self._refresh_state()

    def restore_open_values(self) -> None:
        if self._session is None:
            return
        original = self._session.cancel()
        self.content.set_values(self.bridge, self._session)
        if self._preview_callback is not None:
            self._preview_callback(original.to_dict())
        self._refresh_state()

    def cancel_and_close(self) -> None:
        if self._session is not None:
            original = self._session.cancel()
            if self._preview_callback is not None:
                self._preview_callback(original.to_dict())
        self.hide()

    def save_and_close(self) -> None:
        if self._session is None:
            return
        errors = self._session.validate(self.bridge.validate)
        if errors:
            self.status_label.setText(next(iter(errors.values())))
            return
        try:
            saved = self.bridge.save_snapshot(self._session.working_snapshot)
        except SettingsBridgeError as error:
            self.status_label.setText(str(error))
            return
        self._session.replace_after_save(saved)
        self.saved.emit(saved)
        self.hide()

    def _refresh_state(self) -> None:
        if self._session is None:
            self.restore_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.status_label.setText("")
            return
        errors = self._session.validate(self.bridge.validate)
        dirty = self._session.is_dirty
        self.restore_button.setEnabled(dirty)
        self.cancel_button.setEnabled(dirty)
        self.save_button.setEnabled(dirty and not errors)
        self.status_label.setText("有未保存修改" if dirty else "")

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        self._theme = theme
        if hasattr(self, "content"):
            self.content.set_theme(theme)
        if not hasattr(self, "footer"):
            return
        self.footer.setStyleSheet(
            f"QFrame#lyricsQuickSettingsFooter {{ border-top: 1px solid {theme.colors.border}; background: rgba(10, 14, 20, 0.36); }}"
        )
        neutral = (
            f"QPushButton {{ min-height: {theme.metrics.control_height - 2}px; padding: 0 10px; "
            f"border: 1px solid {theme.colors.border}; border-radius: {theme.metrics.radius_sm}px; "
            f"background: {theme.colors.input_background}; color: {theme.colors.primary_text}; }} "
            f"QPushButton:hover {{ background: {theme.colors.hover_background}; }} "
            f"QPushButton:focus {{ border-color: {theme.colors.focus_ring}; }} "
            f"QPushButton:disabled {{ color: {theme.colors.disabled_text}; }}"
        )
        self.restore_button.setStyleSheet(neutral)
        self.cancel_button.setStyleSheet(neutral)
        self.save_button.setStyleSheet(
            f"QPushButton {{ min-height: {theme.metrics.control_height - 2}px; padding: 0 12px; border: 0; "
            f"border-radius: {theme.metrics.radius_sm}px; background: {theme.colors.accent}; color: white; font-weight: 600; }} "
            f"QPushButton:hover {{ background: {theme.colors.accent_hover}; }} "
            f"QPushButton:focus {{ border: 1px solid {theme.colors.focus_ring}; }} "
            f"QPushButton:disabled {{ background: {theme.colors.border}; color: {theme.colors.disabled_text}; }}"
        )
        self.status_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"
        )


LyricsQuickSettingsDrawer = LyricsQuickSettingsFloatingPanel
