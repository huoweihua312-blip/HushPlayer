"""Small themed dialogs for ordinary playlist management."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.theme.system_surfaces import button_stylesheet, dialog_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.line_edit import apply_optical_vertical_center


class PlaylistNameDialog(QDialog):
    """Frameless Quiet Orbit input dialog for create and rename actions."""

    def __init__(
        self,
        theme: Theme,
        title: str,
        *,
        initial_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("playlistNameDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(260)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("playlistDialogTitle")
        self.name_input = QLineEdit(self)
        self.name_input.setObjectName("playlistNameInput")
        apply_optical_vertical_center(self.name_input)
        self.name_input.setAccessibleName("歌单名称")
        self.name_input.setPlaceholderText("输入歌单名称")
        self.name_input.setText(str(initial_name or ""))
        self.error_label = QLabel(self)
        self.error_label.setObjectName("playlistDialogError")
        self.error_label.setText("歌单名称不能为空。")
        self.error_label.hide()

        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.setObjectName("playlistDialogCancel")
        self.cancel_button.setAccessibleName("取消")
        self.confirm_button = QPushButton("确认", self)
        self.confirm_button.setObjectName("playlistDialogConfirm")
        self.confirm_button.setAccessibleName("确认")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        self.name_input.returnPressed.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 28, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(self.title_label)
        name_label = QLabel("歌单名称", self)
        name_label.setBuddy(self.name_input)
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)
        self.set_theme(theme)
        self.name_input.selectAll()

    @property
    def name(self) -> str:
        return self.name_input.text().strip()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(dialog_stylesheet(theme))
        self.cancel_button.setStyleSheet(button_stylesheet(theme, "secondary"))
        self.confirm_button.setStyleSheet(button_stylesheet(theme, "primary"))

    def accept(self) -> None:  # noqa: D401
        """Accept only a non-empty, trimmed playlist name."""

        if not self.name:
            self.error_label.show()
            self.name_input.setFocus()
            return
        self.error_label.hide()
        super().accept()


class PlaylistConfirmDialog(QDialog):
    """Themed destructive confirmation for ordinary playlist deletion."""

    def __init__(
        self,
        theme: Theme,
        title: str,
        message: str,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("playlistConfirmDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(260)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("playlistDialogTitle")
        self.message_label = QLabel(message, self)
        self.message_label.setObjectName("playlistDialogMessage")
        self.message_label.setWordWrap(True)
        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.setObjectName("playlistDialogCancel")
        self.cancel_button.setAccessibleName("取消")
        self.confirm_button = QPushButton("删除歌单", self)
        self.confirm_button.setObjectName("playlistDialogDelete")
        self.confirm_button.setAccessibleName("删除歌单")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 28, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        layout.addLayout(buttons)
        self.set_theme(theme)
        self.cancel_button.setFocus()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(dialog_stylesheet(theme))
        self.cancel_button.setStyleSheet(button_stylesheet(theme, "secondary"))
        self.confirm_button.setStyleSheet(button_stylesheet(theme, "danger"))
