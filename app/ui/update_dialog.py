from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.version import APP_VERSION
from app.services.app_update_service import (
    AppUpdateService,
    UpdateManifest,
    UpdateReleaseNotesSection,
    select_update_release_notes,
)
from app.ui.design_system import UI_SPACING


class UpdateDialog(QDialog):
    def __init__(
        self,
        service: AppUpdateService,
        manifest: UpdateManifest,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.manifest = manifest
        self.setWindowTitle("HushPlayer 更新")
        self.setObjectName("updateDialog")
        self.setMinimumSize(560, 430)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(UI_SPACING["md"])

        title = QLabel(f"发现新版本 {manifest.version}")
        title.setObjectName("settingsDialogTitle")
        self.subtitle = QLabel(
            f"将从 {APP_VERSION} 更新到 {manifest.version}\n"
            f"Windows 版本 {manifest.numeric_version_text} · {manifest.architecture}"
        )
        self.subtitle.setObjectName("settingsDialogSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.subtitle)

        notice = QFrame()
        notice.setObjectName("settingsCard")
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(16, 12, 16, 12)
        notice_layout.setSpacing(UI_SPACING["xs"])
        mandatory_text = (
            "发布者将此版本标记为必须更新，但第一阶段仍由你确认下载和安装。"
            if manifest.mandatory
            else "这是可选更新。你可以现在安装，也可以稍后再处理。"
        )
        mandatory_label = QLabel(mandatory_text)
        mandatory_label.setObjectName("settingsHint")
        mandatory_label.setWordWrap(True)
        notice_layout.addWidget(mandatory_label)
        layout.addWidget(notice)

        notes_title = QLabel("更新日志")
        notes_title.setObjectName("settingsCardTitle")
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMinimumHeight(150)
        self.notes.setMaximumHeight(320)
        self.notes.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.release_note_sections = select_update_release_notes(manifest)
        self.notes.setPlainText(
            self.format_release_notes(self.release_note_sections)
        )
        layout.addWidget(notes_title)
        layout.addWidget(self.notes, 1)

        self.status_label = QLabel("可以下载安装包。校验完成前不会允许安装。")
        self.status_label.setObjectName("settingsHint")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel()
        self.progress_label.setObjectName("settingsHint")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(UI_SPACING["sm"])
        self.download_button = QPushButton("下载安装包")
        self.download_button.setObjectName("settingsPrimaryButton")
        self.download_button.clicked.connect(self.start_download)
        self.cancel_button = QPushButton("取消下载")
        self.cancel_button.setObjectName("settingsSecondaryButton")
        self.cancel_button.clicked.connect(self.service.cancel_download)
        self.cancel_button.setEnabled(False)
        self.install_button = QPushButton("立即安装")
        self.install_button.setObjectName("settingsPrimaryButton")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.install_now)
        close_button = QPushButton("稍后")
        close_button.setObjectName("settingsSecondaryButton")
        close_button.clicked.connect(self.close)
        button_row.addWidget(self.download_button)
        button_row.addWidget(self.cancel_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        button_row.addWidget(self.install_button)
        layout.addLayout(button_row)

        service.downloadStarted.connect(self.on_download_started)
        service.downloadProgress.connect(self.on_download_progress)
        service.downloadFailed.connect(self.on_download_failed)
        service.downloadCancelled.connect(self.on_download_cancelled)
        service.downloadVerified.connect(self.on_download_verified)
        service.installerLaunchFailed.connect(self.on_installer_launch_failed)

        if (
            service.verified_manifest == manifest
            and service.verified_path is not None
            and service.verified_path.is_file()
        ):
            self.on_download_verified(manifest, str(service.verified_path))

    @staticmethod
    def format_release_notes(
        sections: tuple[UpdateReleaseNotesSection, ...],
    ) -> str:
        if not sections:
            return "本次更新没有附加说明。"
        blocks: list[str] = []
        for section in sections:
            heading = section.version
            if section.release_date:
                heading = f"{heading} · {section.release_date}"
            notes = "\n".join(f"• {note}" for note in section.notes)
            blocks.append(f"{heading}\n{notes}" if notes else heading)
        return "\n\n".join(blocks)

    @staticmethod
    def format_bytes(value: int) -> str:
        size = float(max(0, int(value)))
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024.0 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"

    def start_download(self) -> None:
        if self.service.start_download(self.manifest):
            return
        QMessageBox.information(
            self,
            "应用更新",
            "当前有其他更新检查或下载正在进行。",
        )

    def on_download_started(self, _path: str) -> None:
        self.status_label.setText("正在下载并校验完整安装包…")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText(
            f"0 B / {self.format_bytes(self.manifest.setup_size)}"
        )
        self.progress_label.show()
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.install_button.setEnabled(False)

    def on_download_progress(self, received: int, total: int) -> None:
        expected = max(1, int(total or self.manifest.setup_size))
        percent = max(0, min(100, int(received * 100 / expected)))
        self.progress_bar.setValue(percent)
        self.progress_label.setText(
            f"{self.format_bytes(received)} / {self.format_bytes(expected)}"
        )

    def on_download_failed(self, message: str) -> None:
        self.status_label.setText("下载或校验失败。未保留可执行安装包。")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.install_button.setEnabled(False)
        QMessageBox.warning(self, "更新失败", message)

    def on_download_cancelled(self) -> None:
        self.status_label.setText("下载已取消。未完成的临时文件已清理。")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.install_button.setEnabled(False)

    def on_download_verified(self, manifest: object, path: str) -> None:
        if manifest != self.manifest:
            return
        self.status_label.setText(
            "安装包大小和 SHA-256 已校验，可以立即安装或稍后安装。"
        )
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.progress_label.setText(
            f"{self.format_bytes(self.manifest.setup_size)} / "
            f"{self.format_bytes(self.manifest.setup_size)}"
        )
        self.progress_label.show()
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.install_button.setEnabled(bool(path))

    def install_now(self) -> None:
        answer = QMessageBox.question(
            self,
            "立即安装更新",
            "将启动可见的安装向导。确认启动成功后，HushPlayer 会保存状态并安全退出。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText("正在重新校验并启动安装程序…")
        self.install_button.setEnabled(False)
        self.service.launch_verified_installer()

    def on_installer_launch_failed(self, message: str) -> None:
        self.status_label.setText("安装程序未能启动，HushPlayer 将继续运行。")
        self.install_button.setEnabled(
            self.service.verified_manifest == self.manifest
            and self.service.verified_path is not None
        )
        QMessageBox.warning(self, "无法启动安装", message)

    def closeEvent(self, event) -> None:
        if self.service.is_downloading:
            answer = QMessageBox.question(
                self,
                "取消更新下载",
                "关闭窗口会取消当前下载。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.service.cancel_download()
        super().closeEvent(event)
