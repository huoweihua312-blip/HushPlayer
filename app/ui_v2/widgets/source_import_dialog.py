"""Quiet Orbit dialogs for importing and removing online sources."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.services.online_source_importer import OnlineSourceImporter
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.settings_control_factory import SettingsControlFactory, SettingsToggle


class SourceImportDialog(QDialog):
    """Modal import surface backed by the existing URL source safety checks."""

    def __init__(
        self,
        importer: OnlineSourceImporter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.importer = importer
        self._theme = theme
        self.setObjectName("sourceImportDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(520)

        self.title_label = QLabel("添加在线来源", self)
        self.detail_label = QLabel(
            "每行填写一个 .js 或 .json URL。只添加你拥有或明确获授权使用的来源。",
            self,
        )
        self.detail_label.setWordWrap(True)
        self.url_input = QPlainTextEdit(self)
        self.url_input.setObjectName("sourceImportUrls")
        self.url_input.setAccessibleName("在线来源 URL")
        self.url_input.setPlaceholderText(
            "例如：\nhttps://example.invalid/open-source.js"
        )
        self.url_input.setMinimumHeight(112)
        self.policy_combo = SettingsControlFactory.combo(
            (("内容明确授权开放使用", "open"), ("内容由我拥有", "user_owned")),
            "open",
            theme,
            self,
        )
        self.policy_combo.setAccessibleName("来源内容授权范围")
        self.confirm_toggle = SettingsToggle(False, theme, self)
        self.confirm_toggle.setAccessibleName("确认来源授权范围")
        self.confirm_label = QLabel("我确认以上 URL 符合所选授权范围", self)
        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.cancel_button = QToolButton(self)
        self.cancel_button.setText("取消")
        self.cancel_button.setAccessibleName("取消")
        self.import_button = QToolButton(self)
        self.import_button.setText("添加来源")
        self.import_button.setAccessibleName("添加来源")
        self.cancel_button.clicked.connect(self.reject)
        self.import_button.clicked.connect(self._start_import)

        policy_row = QHBoxLayout()
        policy_row.setContentsMargins(0, 0, 0, 0)
        policy_row.setSpacing(8)
        policy_row.addWidget(self.policy_combo)
        policy_row.addWidget(self.confirm_toggle)
        policy_row.addWidget(self.confirm_label, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 10, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.import_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.url_input)
        layout.addLayout(policy_row)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

        importer.status_changed.connect(self._set_status)
        importer.completed.connect(self._on_completed)
        importer.failed.connect(self._on_failed)
        importer.busy_changed.connect(self._set_busy)
        self.set_theme(theme)
        self.url_input.setFocus()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        m = theme.metrics
        self.setStyleSheet(
            f"QDialog#sourceImportDialog {{ background: {c.surface_elevated}; border: 1px solid {c.border_strong}; border-radius: {m.radius_lg}px; }}"
            f"QLabel {{ color: {c.primary_text}; }}"
            f"QPlainTextEdit#sourceImportUrls {{ min-height: 112px; padding: 10px; border: 1px solid {c.border}; border-radius: {m.radius_sm}px; background: {c.input_background}; color: {c.primary_text}; }}"
            f"QPlainTextEdit#sourceImportUrls:focus {{ border-color: {c.focus_ring}; }}"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {c.primary_text};"
        )
        self.detail_label.setStyleSheet(
            f"font-size: {theme.fonts.body}px; color: {c.secondary_text};"
        )
        self.confirm_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {c.secondary_text};"
        )
        self.status_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {c.secondary_text};"
        )
        self._style_button(self.cancel_button, theme, primary=False)
        self._style_button(self.import_button, theme, primary=True)

    @staticmethod
    def _style_button(button: QToolButton, theme: Theme, *, primary: bool) -> None:
        c = theme.colors
        if primary:
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 0; border-radius: {theme.metrics.radius_sm}px; background: {c.accent}; color: {c.content_background}; font-weight: 600; }}"
                f"QToolButton:hover {{ background: {c.accent_hover}; }}"
            )
        else:
            button.setStyleSheet(
                f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; }}"
                f"QToolButton:hover {{ background: {c.hover_background}; }}"
            )

    def _start_import(self) -> None:
        if not self.confirm_toggle.isChecked():
            self._on_failed("添加前必须确认内容所有权或开放授权。")
            return
        self.importer.import_urls(
            self.url_input.toPlainText(),
            str(self.policy_combo.currentData() or ""),
        )

    def _set_busy(self, busy: bool) -> None:
        self.import_button.setEnabled(not busy)
        self.cancel_button.setText("停止" if busy else "取消")

    def _set_status(self, message: str) -> None:
        self.status_label.setText(str(message or ""))
        self.status_label.setStyleSheet(
            f"font-size: {self._theme.fonts.caption}px; color: {self._theme.colors.secondary_text};"
        )

    def _on_completed(self, message: str) -> None:
        self._set_status(message)
        self.status_label.setStyleSheet(
            f"font-size: {self._theme.fonts.caption}px; color: {self._theme.colors.success};"
        )

    def _on_failed(self, message: str) -> None:
        self._set_status(message)
        self.status_label.setStyleSheet(
            f"font-size: {self._theme.fonts.caption}px; color: {self._theme.colors.danger};"
        )

    def reject(self) -> None:
        if self.importer.busy:
            self.importer.cancel()
            self._set_status("已停止添加来源。")
            return
        super().reject()


class SourceRemoveConfirmDialog(QDialog):
    """Themed confirmation for removing a user-installed source."""

    confirmed = Signal()

    def __init__(self, source_name: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("sourceRemoveConfirmDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(420)
        title = QLabel("移除在线来源", self)
        title.setObjectName("sourceRemoveTitle")
        message = QLabel(
            f"确定移除“{str(source_name or '该来源').strip()}”吗？\n移除来源不会删除已经加入歌单的歌曲。",
            self,
        )
        message.setWordWrap(True)
        cancel = QToolButton(self)
        cancel.setText("取消")
        confirm = QToolButton(self)
        confirm.setText("移除来源")
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self._confirm)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 10, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(message)
        layout.addLayout(buttons)
        self._buttons = (cancel, confirm)
        self.set_theme(theme)
        cancel.setFocus()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QDialog#sourceRemoveConfirmDialog {{ background: {c.surface_elevated}; border: 1px solid {c.border_strong}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QLabel#sourceRemoveTitle {{ color: {c.primary_text}; font-size: {theme.fonts.section_title}px; font-weight: 600; }}"
            f"QLabel {{ color: {c.secondary_text}; font-size: {theme.fonts.body}px; }}"
        )
        self._buttons[0].setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 1px solid {c.border}; border-radius: {theme.metrics.radius_sm}px; background: {c.surface_secondary}; color: {c.primary_text}; }}"
            f"QToolButton:hover {{ background: {c.hover_background}; }}"
        )
        self._buttons[1].setStyleSheet(
            f"QToolButton {{ min-height: {theme.metrics.control_height}px; padding: 0 {theme.metrics.spacing_md}px; border: 1px solid {c.danger}; border-radius: {theme.metrics.radius_sm}px; background: transparent; color: {c.danger}; }}"
            f"QToolButton:hover {{ background: {c.danger}; color: {c.content_background}; }}"
        )

    def _confirm(self) -> None:
        self.confirmed.emit()
        self.accept()
