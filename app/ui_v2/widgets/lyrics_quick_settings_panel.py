"""Transactional floating settings for the immersive lyrics presentation."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QSlider, QToolButton

from app.ui_v2.adapters.legacy_settings_bridge import (
    IMMERSIVE_BACKGROUND_VISUAL_MODES,
    LegacySettingsBridge,
    normalize_immersive_background_visual_mode,
)
from app.ui_v2.models.settings_edit_session import SettingsEditSession
from app.ui_v2.models.settings_snapshot import SettingsSnapshot
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.immersive_settings_panel import ImmersiveSettingsPanel


class LyricsQuickSettingsFloatingPanel(ImmersiveSettingsPanel):
    """A stable panel that previews existing settings and saves through the bridge."""

    draft_changed = Signal()
    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(
        self,
        theme: Theme,
        parent=None,
        *,
        settings_bridge: LegacySettingsBridge | None = None,
        path_picker: Callable[[], str] | None = None,
    ) -> None:
        self._settings_bridge = settings_bridge
        self._path_picker = path_picker
        self._session: SettingsEditSession | None = None
        self._syncing_session = False
        self._custom_path = ""
        super().__init__(theme, parent)
        self._add_formal_controls()
        self._add_transaction_footer()
        self.changed.connect(self._sync_session_from_controls)
        self.custom_path_button.clicked.connect(self._choose_custom_path)

    def _add_formal_controls(self) -> None:
        form = self.content_widget.layout()
        if not isinstance(form, QFormLayout):
            return
        self._add_section(form, "背景细节")
        self.background_blur_slider = self._slider(0, 100)
        self.background_darkness_slider = self._slider(0, 100)
        self.background_image_opacity_slider = self._slider(0, 100)
        self.background_transparency_slider = self._slider(0, 100)
        self.custom_path_button = QToolButton(self.content_widget)
        self.custom_path_button.setText("选择背景图片")
        self.custom_clear_button = QToolButton(self.content_widget)
        self.custom_clear_button.setText("清除")
        self.custom_clear_button.setToolTip("恢复封面背景")
        self.custom_clear_button.setAccessibleName("清除自定义背景")
        self.custom_clear_button.setEnabled(False)
        self.custom_clear_button.clicked.connect(self._clear_custom_path)
        self.custom_path_label = QLabel("未选择自定义背景", self.content_widget)
        self.custom_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_actions = QHBoxLayout()
        path_actions.setContentsMargins(0, 0, 0, 0)
        path_actions.setSpacing(6)
        path_actions.addWidget(self.custom_path_button)
        path_actions.addWidget(self.custom_clear_button)
        for label, control in (
            ("背景模糊", self._slider_row(self.background_blur_slider, "%")),
            ("背景暗度", self._slider_row(self.background_darkness_slider, "%")),
            ("图片不透明度", self._slider_row(self.background_image_opacity_slider, "%")),
            ("背景透明度", self._slider_row(self.background_transparency_slider, "%")),
            ("自定义图片", path_actions),
            ("图片路径", self.custom_path_label),
        ):
            form.addRow(label, control)
        for slider in (
            self.background_blur_slider,
            self.background_darkness_slider,
            self.background_image_opacity_slider,
            self.background_transparency_slider,
        ):
            slider.valueChanged.connect(self.changed)

    def _add_transaction_footer(self) -> None:
        footer = self.footer_widget.layout()
        if not isinstance(footer, QHBoxLayout):
            return
        self.exit_immersive_button.setVisible(False)
        self.status_label = QLabel("未修改", self.footer_widget)
        self.status_label.setObjectName("immersiveQuickSettingsStatus")
        self.cancel_button = QToolButton(self.footer_widget)
        self.cancel_button.setText("取消")
        self.save_button = QToolButton(self.footer_widget)
        self.save_button.setText("保存")
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.save_button.clicked.connect(self.save_requested)
        footer.insertWidget(0, self.status_label)
        footer.addStretch(1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        self.save_button.setEnabled(False)

    @property
    def session(self) -> SettingsEditSession | None:
        return self._session

    @property
    def is_dirty(self) -> bool:
        return bool(self._session and self._session.is_dirty)

    @property
    def custom_path(self) -> str:
        """Return the full selected path, keeping direct-label integrations working."""

        if self._custom_path:
            return self._custom_path
        label = self.custom_path_label.text().strip()
        return "" if label == "未选择自定义背景" else label

    def begin_session(self, snapshot: SettingsSnapshot | None = None) -> None:
        if snapshot is None and self._settings_bridge is not None:
            snapshot = self._settings_bridge.read_snapshot()
        if snapshot is None:
            self._session = None
            self._set_status("clean")
            return
        self._session = SettingsEditSession.open(snapshot)
        self._load_session_into_controls()
        self._set_status("clean")

    def _load_session_into_controls(self) -> None:
        if self._session is None:
            return
        values = self._session.working_snapshot.to_dict()
        self._syncing_session = True
        try:
            appearance = str(values.get("appearance_mode", "dark"))
            appearance_index = self.theme_combo.findData(appearance if appearance != "system" else "")
            if appearance_index >= 0:
                self.theme_combo.setCurrentIndex(appearance_index)
            mode_value = normalize_immersive_background_visual_mode(
                values.get("immersive_background_visual_mode"),
                values.get("immersive_background_mode", "cover"),
            )
            mode_index = self.background_combo.findData(mode_value)
            if mode_index >= 0:
                self.background_combo.setCurrentIndex(mode_index)
            self.auto_hide_check.setChecked(bool(values.get("immersive_auto_hide_ui", True)))
            for key, control, default in (
                ("immersive_background_blur", self.background_blur_slider, 40),
                ("immersive_background_darkness", self.background_darkness_slider, 68),
                ("immersive_background_image_opacity", self.background_image_opacity_slider, 100),
                ("immersive_background_transparency", self.background_transparency_slider, 38),
                ("immersive_lyrics_font_scale", self.global_lyric_scale_slider, 100),
            ):
                control.setValue(int(values.get(key, default)))
            path = str(values.get("immersive_background_custom_path", "") or "")
            self._set_custom_path(path)
        finally:
            self._syncing_session = False

    def _setting_values(self) -> dict[str, object]:
        mode = str(self.background_combo.currentData() or "artwork")
        if mode not in IMMERSIVE_BACKGROUND_VISUAL_MODES:
            mode = "artwork"
        formal_mode = {"artwork": "cover", "gradient": "default", "solid": "default", "transparent": "translucent", "custom": "custom"}[mode]
        path = self.custom_path
        has_custom_background = mode == "custom" and bool(path)
        return {
            "appearance_mode": self.theme_combo.currentData() or "system",
            "immersive_auto_hide_ui": self.auto_hide_check.isChecked(),
            "immersive_background_mode": "custom" if has_custom_background else formal_mode,
            "immersive_background_visual_mode": mode if has_custom_background or mode != "custom" else "artwork",
            "immersive_background_custom_path": path,
            "immersive_background_blur": self.background_blur_slider.value(),
            "immersive_background_darkness": self.background_darkness_slider.value(),
            "immersive_background_image_opacity": self.background_image_opacity_slider.value(),
            "immersive_background_transparency": self.background_transparency_slider.value(),
            "immersive_lyrics_font_scale": self.global_lyric_scale_slider.value(),
        }

    def _sync_session_from_controls(self) -> None:
        if self._syncing_session or self._session is None:
            return
        for key, value in self._setting_values().items():
            if self._session.set(key, value):
                self._session.mark_previewed(key)
        self._set_status("dirty" if self._session.is_dirty else "clean")
        self.draft_changed.emit()

    def _choose_custom_path(self) -> None:
        path = self._path_picker() if self._path_picker is not None else QFileDialog.getOpenFileName(
            self,
            "选择沉浸背景图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )[0]
        if path:
            self._set_custom_path(str(path))
            custom_index = self.background_combo.findData("custom")
            if custom_index >= 0:
                previous = self.background_combo.blockSignals(True)
                self.background_combo.setCurrentIndex(custom_index)
                self.background_combo.blockSignals(previous)
            self.changed.emit()

    def _set_custom_path(self, path: str) -> None:
        self._custom_path = str(path or "").strip()
        if not self._custom_path:
            self.custom_path_label.setText("未选择自定义背景")
            self.custom_path_label.setToolTip("")
        else:
            available = max(120, self.custom_path_label.width() - 8)
            text = QFontMetrics(self.custom_path_label.font()).elidedText(
                self._custom_path,
                Qt.TextElideMode.ElideMiddle,
                available,
            )
            self.custom_path_label.setText(text)
            self.custom_path_label.setToolTip(self._custom_path)
        self.custom_clear_button.setEnabled(bool(self._custom_path))

    def _clear_custom_path(self) -> None:
        self._set_custom_path("")
        artwork_index = self.background_combo.findData("artwork")
        if artwork_index >= 0:
            previous = self.background_combo.blockSignals(True)
            self.background_combo.setCurrentIndex(artwork_index)
            self.background_combo.blockSignals(previous)
        self.changed.emit()

    def cancel_session(self) -> SettingsSnapshot | None:
        if self._session is None:
            return None
        snapshot = self._session.cancel()
        self._load_session_into_controls()
        self._set_status("clean")
        return snapshot

    def mark_saved(self, snapshot: SettingsSnapshot) -> None:
        if self._session is None:
            self._session = SettingsEditSession.open(snapshot)
        else:
            self._session.replace_after_save(snapshot)
        self._load_session_into_controls()
        self._set_status("success")

    def mark_failed(self, message: str) -> None:
        self._set_status("failed", message)

    def _set_status(self, state: str, detail: str = "") -> None:
        if not hasattr(self, "status_label"):
            return
        text = {
            "clean": "未修改",
            "dirty": "正在预览 · 有未保存修改",
            "success": "已保存",
            "failed": detail or "保存失败",
        }.get(state, state)
        self.status_label.setText(text)
        self.save_button.setEnabled(state == "dirty" and self.is_dirty)
        self.status_label.setProperty("status", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def request_close(self) -> None:
        if self.is_dirty:
            self.cancel_requested.emit()
            return
        super().request_close()

    def set_theme(self, theme: Theme) -> None:
        super().set_theme(theme)
        if hasattr(self, "status_label"):
            self.status_label.setStyleSheet(
                f"font-size: {theme.fonts.caption}px; color: {theme.colors.text_secondary};"
            )
            self.save_button.setStyleSheet(
                f"QToolButton {{ color: {theme.colors.accent}; font-weight: 650; }}"
                f"QToolButton:hover {{ background: {theme.colors.hover_background}; }}"
            )
