"""Update dialog owned by the active UI V2 shell."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
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
from app.ui_v2.theme.styles import build_dialog_stylesheet
from app.ui_v2.theme.tokens import get_theme


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

        app = QApplication.instance()
        theme_mode = (
            str(app.property("hushUiV2ThemeMode") or "dark")
            if app is not None
            else "dark"
        )
        theme = get_theme(theme_mode)
        if app is not None and app.property("hushUiFlavor") == "ui-v2":
            self.setStyleSheet(build_dialog_stylesheet(theme))
        metrics = theme.metrics

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(metrics.spacing_md)

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
        notice_layout.setSpacing(metrics.spacing_xs)
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
        self.notes.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.release_note_sections = select_update_release_notes(manifest)
        self.notes.setPlainText(self.format_release_notes(self.release_note_sections))
        layout.addWidget(notes_title)
        layout.addWidget(self.notes, 1)

        self.status_label = QLabel(
            "可以下载应用内更新包。校验完成前不会允许更新。"
            if manifest.has_in_app_package
            else "可以下载安装包。校验完成前不会允许安装。"
        )
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
        button_row.setSpacing(metrics.spacing_sm)
        self.download_button = QPushButton(
            "下载应用内更新" if manifest.has_in_app_package else "下载安装包"
        )
        self.download_button.setObjectName("settingsPrimaryButton")
        self.download_button.setProperty("role", "primary")
        self.download_button.setAccessibleName("下载更新")
        self.download_button.clicked.connect(self.start_download)
        self.cancel_button = QPushButton("取消下载")
        self.cancel_button.setObjectName("settingsSecondaryButton")
        self.cancel_button.clicked.connect(self.service.cancel_download)
        self.cancel_button.setEnabled(False)
        self.install_button = QPushButton(
            "立即更新" if manifest.has_in_app_package else "立即安装"
        )
        self.install_button.setObjectName("settingsPrimaryButton")
        self.install_button.setProperty("role", "primary")
        self.install_button.setAccessibleName(
            "立即更新" if manifest.has_in_app_package else "立即安装"
        )
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.install_now)
        self.fallback_install_button: QPushButton | None = None
        if manifest.has_in_app_package:
            self.fallback_install_button = QPushButton("下载完整安装包")
            self.fallback_install_button.setObjectName("settingsSecondaryButton")
            self.fallback_install_button.setAccessibleName("使用完整安装包更新")
            self.fallback_install_button.clicked.connect(self.install_with_installer)
        close_button = QPushButton("稍后")
        close_button.setObjectName("settingsSecondaryButton")
        close_button.clicked.connect(self.close)
        button_row.addWidget(self.download_button)
        button_row.addWidget(self.cancel_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        if self.fallback_install_button is not None:
            button_row.addWidget(self.fallback_install_button)
        button_row.addWidget(self.install_button)
        layout.addLayout(button_row)

        service.downloadStarted.connect(self.on_download_started)
        service.downloadProgress.connect(self.on_download_progress)
        service.downloadFailed.connect(self.on_download_failed)
        service.downloadCancelled.connect(self.on_download_cancelled)
        service.downloadVerified.connect(self.on_download_verified)
        service.installerLaunchFailed.connect(self.on_installer_launch_failed)

        verified_path = None
        if (
            service.verified_package_manifest == manifest
            and service.verified_package_path is not None
            and service.verified_package_path.is_file()
        ):
            verified_path = service.verified_package_path
        elif (
            service.verified_installer_manifest == manifest
            and service.verified_installer_path is not None
            and service.verified_installer_path.is_file()
        ):
            verified_path = service.verified_installer_path
        elif (
            service.verified_manifest == manifest
            and service.verified_path is not None
            and service.verified_path.is_file()
        ):
            verified_path = service.verified_path
        if verified_path is not None:
            self.on_download_verified(manifest, str(verified_path))

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
        QMessageBox.information(self, "应用更新", "当前有其他更新检查或下载正在进行。")

    def _package_ready(self) -> bool:
        return (
            self.service.verified_package_manifest == self.manifest
            and self.service.verified_package_path is not None
            and self.service.verified_package_path.is_file()
        )

    def _installer_ready(self) -> bool:
        return (
            self.service.verified_installer_manifest == self.manifest
            and self.service.verified_installer_path is not None
            and self.service.verified_installer_path.is_file()
        )

    def on_download_started(self, _path: str) -> None:
        download_name = (
            "完整安装包" if self.service.download_kind == "installer" else "应用内更新包"
        )
        self.status_label.setText(f"正在下载并校验{download_name}…")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.setText(f"0 B / {self.format_bytes(self.manifest.download_size)}")
        self.progress_label.show()
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.install_button.setEnabled(False)
        if self.fallback_install_button is not None:
            self.fallback_install_button.setEnabled(False)

    def on_download_progress(self, received: int, total: int) -> None:
        fallback_total = (
            self.manifest.setup_size
            if self.service.download_kind == "installer"
            else self.manifest.download_size
        )
        expected = max(1, int(total or fallback_total))
        percent = max(0, min(100, int(received * 100 / expected)))
        self.progress_bar.setValue(percent)
        self.progress_label.setText(
            f"{self.format_bytes(received)} / {self.format_bytes(expected)}"
        )

    def on_download_failed(self, message: str) -> None:
        self.status_label.setText("下载或校验失败。未保留可用的更新文件。")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.install_button.setEnabled(
            self._package_ready()
            or (not self.manifest.has_in_app_package and self._installer_ready())
        )
        if self.fallback_install_button is not None:
            self.fallback_install_button.setEnabled(True)
        QMessageBox.warning(self, "更新失败", message)

    def on_download_cancelled(self) -> None:
        self.status_label.setText("下载已取消。未完成的临时文件已清理。")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.install_button.setEnabled(
            self._package_ready()
            or (not self.manifest.has_in_app_package and self._installer_ready())
        )
        if self.fallback_install_button is not None:
            self.fallback_install_button.setEnabled(True)

    def on_download_verified(self, manifest: object, path: str) -> None:
        del path
        if manifest != self.manifest:
            return
        package_ready = self._package_ready()
        installer_ready = self._installer_ready()
        if (
            self.manifest.has_in_app_package
            and self.service.last_download_kind == "installer"
        ):
            self.status_label.setText(
                "完整安装包大小和 SHA-256 已校验，可以使用外部安装方式更新。"
            )
        elif self.manifest.has_in_app_package:
            self.status_label.setText(
                "应用内更新包大小和 SHA-256 已校验，更新完成后 HushPlayer 会自动重启。"
            )
        else:
            self.status_label.setText("安装包大小和 SHA-256 已校验，可以立即安装或稍后安装。")
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.progress_label.setText(
            f"{self.format_bytes(self.manifest.download_size)} / "
            f"{self.format_bytes(self.manifest.download_size)}"
        )
        self.progress_label.show()
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.install_button.setEnabled(
            package_ready if self.manifest.has_in_app_package else installer_ready
        )
        if self.fallback_install_button is not None:
            self.fallback_install_button.setText(
                "立即使用安装包更新" if installer_ready else "下载完整安装包"
            )
            self.fallback_install_button.setEnabled(True)

    def install_now(self) -> None:
        if self.manifest.has_in_app_package:
            title = "立即应用更新"
            message = (
                "HushPlayer 将关闭当前窗口，由更新助手替换程序文件并自动重启。\n"
                "用户数据和音乐库不会被删除。是否继续？"
            )
        else:
            title = "立即安装更新"
            message = "将启动可见的安装向导。确认启动成功后，HushPlayer 会保存状态并安全退出。"
        answer = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText(
            "正在重新校验并启动应用内更新助手…"
            if self.manifest.has_in_app_package
            else "正在重新校验并启动安装程序…"
        )
        self.install_button.setEnabled(False)
        self.service.launch_verified_update()

    def install_with_installer(self) -> None:
        if not self._installer_ready():
            if self.service.start_installer_download(self.manifest):
                self.status_label.setText("正在下载并校验完整安装包…")
                return
            QMessageBox.information(self, "应用更新", "当前有其他更新检查或下载正在进行。")
            return

        answer = QMessageBox.question(
            self,
            "使用安装包更新",
            "将启动可见的安装向导，并更新到当前 HushPlayer 安装目录。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText("正在重新校验并启动安装程序…")
        if self.fallback_install_button is not None:
            self.fallback_install_button.setEnabled(False)
        self.service.launch_verified_installer()

    def on_installer_launch_failed(self, message: str) -> None:
        self.status_label.setText("更新程序未能启动，HushPlayer 将继续运行。")
        self.install_button.setEnabled(
            self._package_ready()
            if self.manifest.has_in_app_package
            else self._installer_ready()
        )
        if self.fallback_install_button is not None:
            self.fallback_install_button.setEnabled(True)
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
