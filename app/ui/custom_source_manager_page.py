from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.version import APP_USER_AGENT
from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import (
    MAX_SOURCE_BYTES,
    SourceRegistryError,
    SourceRegistryManager,
)


class CustomSourceManagerPage(QFrame):
    """Small UI for managing registered user-owned/open custom source URLs."""

    sourcesChanged = Signal(str)
    backRequested = Signal()

    def __init__(
        self,
        registry: SourceRegistryManager,
        client: OnlineSourceClient,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.client = client
        self.network_manager = QNetworkAccessManager(self)
        self._runtime_sources: dict[str, dict] = {}
        self._operation_errors: dict[str, str] = {}
        self._import_queue: list[dict] = []
        self._active_reply: QNetworkReply | None = None
        self._active_entry: dict | None = None
        self._completed_count = 0
        self._skipped_count = 0
        self._failed_messages: list[str] = []
        self._build_ui()
        self.client.sourceListReceived.connect(self.on_source_list_received)
        self.client.requestFailed.connect(self.on_request_failed)

    def _build_ui(self) -> None:
        self.setObjectName("customSourceManagerPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("自定义来源")
        title.setObjectName("pageTitle")
        subtitle = QLabel("管理你拥有或明确授权开放使用的 .js / .json URL 来源。")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        back_button = QPushButton("返回音乐库")
        back_button.setObjectName("secondaryButton")
        back_button.clicked.connect(self.backRequested.emit)
        refresh_button = QPushButton("刷新状态")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.refresh_sources)
        header.addLayout(title_box, 1)
        header.addWidget(refresh_button)
        header.addWidget(back_button)
        layout.addLayout(header)

        add_card = QFrame()
        add_card.setObjectName("settingsCard")
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(16, 14, 16, 14)
        add_layout.setSpacing(10)
        add_title = QLabel("添加来源")
        add_title.setObjectName("settingsCardTitle")
        self.url_input = QPlainTextEdit()
        self.url_input.setObjectName("sourceUrlBatchInput")
        self.url_input.setPlaceholderText(
            "每行一个 HTTPS URL，例如：\nhttps://example.invalid/open-source.js"
        )
        self.url_input.setFixedHeight(92)
        option_row = QHBoxLayout()
        self.policy_combo = QComboBox()
        self.policy_combo.addItem("内容明确授权开放使用", "open")
        self.policy_combo.addItem("内容由我拥有", "user_owned")
        self.confirm_checkbox = QCheckBox("我确认以上 URL 符合所选内容授权范围")
        option_row.addWidget(self.policy_combo)
        option_row.addWidget(self.confirm_checkbox, 1)
        self.add_button = QPushButton("添加来源")
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self.start_batch_import)
        option_row.addWidget(self.add_button)
        add_layout.addWidget(add_title)
        add_layout.addWidget(self.url_input)
        add_layout.addLayout(option_row)
        layout.addWidget(add_card)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)
        self.source_list = QListWidget()
        self.source_list.setObjectName("customSourceList")
        self.source_list.setMinimumWidth(430)
        self.source_list.currentItemChanged.connect(self.on_selected_source_changed)
        content_row.addWidget(self.source_list, 3)

        detail_card = QFrame()
        detail_card.setObjectName("settingsCard")
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(10)
        detail_title = QLabel("来源详情")
        detail_title.setObjectName("settingsCardTitle")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("来源名称")
        self.source_detail_label = QLabel("选择一个来源查看状态。")
        self.source_detail_label.setObjectName("pageSubtitle")
        self.source_detail_label.setWordWrap(True)
        self.save_name_button = QPushButton("保存名称")
        self.save_name_button.setObjectName("secondaryButton")
        self.save_name_button.clicked.connect(self.save_selected_name)
        self.toggle_button = QPushButton("启用 / 禁用")
        self.toggle_button.setObjectName("secondaryButton")
        self.toggle_button.clicked.connect(self.toggle_selected_source)
        self.update_button = QPushButton("检查并更新")
        self.update_button.setObjectName("secondaryButton")
        self.update_button.clicked.connect(self.update_selected_source)
        self.remove_button = QPushButton("移除来源")
        self.remove_button.setObjectName("dangerButton")
        self.remove_button.clicked.connect(self.remove_selected_source)
        detail_layout.addWidget(detail_title)
        detail_layout.addWidget(self.name_input)
        detail_layout.addWidget(self.save_name_button)
        detail_layout.addWidget(self.source_detail_label)
        detail_layout.addStretch()
        detail_layout.addWidget(self.toggle_button)
        detail_layout.addWidget(self.update_button)
        detail_layout.addWidget(self.remove_button)
        content_row.addWidget(detail_card, 2)
        layout.addLayout(content_row, 1)

        self.status_label = QLabel("尚未读取来源状态。")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._set_detail_enabled(False)
        self.setStyleSheet(
            "QFrame#settingsCard { background: #151922; border: 1px solid rgba(255,255,255,0.07); border-radius: 16px; }"
            "QLabel#settingsCardTitle { color: #f3f4f6; font-size: 16px; font-weight: 800; }"
            "QListWidget#customSourceList { background: #11151d; color: #e8ecf5; border: 1px solid #2a303b; border-radius: 14px; padding: 7px; outline: none; }"
            "QListWidget#customSourceList::item { padding: 10px; border-radius: 10px; margin: 2px 0; }"
            "QListWidget#customSourceList::item:hover { background: rgba(255,255,255,0.06); }"
            "QListWidget#customSourceList::item:selected { background: rgba(59,130,246,0.20); border: 1px solid rgba(96,165,250,0.45); }"
            "QPlainTextEdit#sourceUrlBatchInput, QFrame#customSourceManagerPage QLineEdit, QFrame#customSourceManagerPage QComboBox { background: #10141c; color: #eef2f8; border: 1px solid #303746; border-radius: 10px; padding: 8px; }"
            "QPlainTextEdit#sourceUrlBatchInput:focus, QFrame#customSourceManagerPage QLineEdit:focus { border-color: #60a5fa; }"
        )

    def refresh_sources(self) -> None:
        self.status_label.setText("正在读取来源状态…")
        self.client.list_sources(timeout_ms=8000)

    def prepare_import_urls(self, text: str) -> tuple[list[str], list[str], int]:
        urls: list[str] = []
        errors: list[str] = []
        duplicate_count = 0
        seen: set[str] = set()
        for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
            value = raw_line.strip()
            if not value:
                continue
            try:
                normalized = self.registry.normalize_source_url(value)
                suffix = Path(urlsplit(normalized).path).suffix.lower()
                if suffix not in {".js", ".json"}:
                    raise SourceRegistryError("URL 必须指向 .js 或 .json 文件")
            except SourceRegistryError as error:
                errors.append(f"第 {line_number} 行：{error}")
                continue
            try:
                existing = self.registry.find_by_source_url(normalized)
            except SourceRegistryError as error:
                errors.append(f"第 {line_number} 行：{error}")
                continue
            if normalized in seen or existing is not None:
                duplicate_count += 1
                continue
            seen.add(normalized)
            urls.append(normalized)
        return urls, errors, duplicate_count

    def start_batch_import(self) -> None:
        if self._active_reply is not None or self._import_queue:
            self.status_label.setText("已有来源正在添加，请等待完成。")
            return
        if not self.confirm_checkbox.isChecked():
            self.status_label.setText("添加前必须确认内容所有权或开放授权。")
            return
        urls, errors, duplicate_count = self.prepare_import_urls(self.url_input.toPlainText())
        if errors:
            self.status_label.setText("；".join(errors[:4]))
            return
        if not urls:
            if duplicate_count:
                self.status_label.setText("输入的来源均已注册，没有重复安装。")
            else:
                self.status_label.setText("请输入至少一个 .js 或 .json URL。")
            return
        policy = str(self.policy_combo.currentData() or "")
        self._import_queue = [
            {"url": url, "policy": policy, "updateSourceId": ""} for url in urls
        ]
        self._completed_count = 0
        self._skipped_count = duplicate_count
        self._failed_messages = []
        self._start_next_download()

    def update_selected_source(self) -> None:
        source = self.selected_source()
        if source is None:
            return
        if not self.confirm_checkbox.isChecked():
            self.status_label.setText("更新前必须再次确认内容所有权或开放授权。")
            return
        if self._active_reply is not None or self._import_queue:
            self.status_label.setText("已有来源操作正在进行，请等待完成。")
            return
        source_id = str(source.get("id") or "")
        source_url = str(source.get("sourceUrl") or "")
        if not source_id or not source_url:
            self.status_label.setText("所选来源没有可更新的注册 URL。")
            return
        policy = str(source.get("contentPolicy") or "").strip().lower()
        if policy not in {"open", "user_owned"}:
            policy = str(self.policy_combo.currentData() or "")
        self._import_queue = [
            {
                "url": source_url,
                "policy": policy,
                "updateSourceId": source_id,
            }
        ]
        self._completed_count = 0
        self._skipped_count = 0
        self._failed_messages = []
        self._start_next_download()

    def _start_next_download(self) -> None:
        if not self._import_queue:
            self._finish_import_queue()
            return
        entry = self._import_queue.pop(0)
        self._active_entry = entry
        request = QNetworkRequest(QUrl(str(entry.get("url") or "")))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setRawHeader(
            b"User-Agent",
            f"{APP_USER_AGENT} custom-source-manager".encode("ascii"),
        )
        request.setRawHeader(
            b"Accept",
            b"application/javascript, application/json, text/plain, */*",
        )
        reply = self.network_manager.get(request)
        self._active_reply = reply
        self._set_busy(True)
        remaining = len(self._import_queue) + 1
        self.status_label.setText(f"正在下载并检查来源，剩余 {remaining} 个…")
        reply.downloadProgress.connect(
            lambda received, total, current_reply=reply: self._guard_source_size(
                current_reply, received, total
            )
        )
        reply.finished.connect(
            lambda current_reply=reply: self._finish_source_download(current_reply)
        )

    @staticmethod
    def _guard_source_size(reply: QNetworkReply, received: int, total: int) -> None:
        if received > MAX_SOURCE_BYTES or total > MAX_SOURCE_BYTES:
            reply.setProperty("sourceTooLarge", True)
            reply.abort()

    def _finish_source_download(self, reply: QNetworkReply) -> None:
        if reply is not self._active_reply:
            reply.deleteLater()
            return
        entry = dict(self._active_entry or {})
        self._active_reply = None
        self._active_entry = None
        source_id = str(entry.get("updateSourceId") or "")
        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = "来源文件超过 2 MB" if reply.property("sourceTooLarge") else reply.errorString()
            self._failed_messages.append(message)
            if source_id:
                self._operation_errors[source_id] = "更新失败"
            reply.deleteLater()
            self._start_next_download()
            return
        content = bytes(reply.readAll())
        suggested_name = Path(reply.url().path()).name or "custom_source.js"
        reply.deleteLater()
        try:
            existing = self.registry.get_source(source_id) if source_id else None
            content_sha = hashlib.sha256(content).hexdigest()
            if existing is not None and content_sha == str(existing.get("sha256") or "").casefold():
                self._skipped_count += 1
            else:
                candidate = self.registry.stage_bytes(
                    content,
                    suggested_name,
                    source_url=str(entry.get("url") or ""),
                    content_policy=str(entry.get("policy") or ""),
                    user_installed=True,
                )
                installed = (
                    self.registry.update_candidate(source_id, candidate)
                    if source_id
                    else self.registry.install_candidate(candidate, enabled=True)
                )
                installed_id = str(installed.get("id") or source_id)
                self._operation_errors.pop(installed_id, None)
                self._completed_count += 1
        except SourceRegistryError as error:
            self._failed_messages.append(str(error))
            if source_id:
                self._operation_errors[source_id] = "更新失败"
        self._start_next_download()

    def _finish_import_queue(self) -> None:
        self._set_busy(False)
        if self._completed_count:
            self.client.reload_sources(timeout_ms=10000)
            self.sourcesChanged.emit("")
        parts = [f"成功 {self._completed_count} 个"]
        if self._skipped_count:
            parts.append(f"未变化或重复 {self._skipped_count} 个")
        if self._failed_messages:
            parts.append(f"失败 {len(self._failed_messages)} 个")
        self.status_label.setText("来源处理完成：" + "，".join(parts) + "。")
        self.refresh_sources()

    def on_source_list_received(self, sources: list) -> None:
        selected_id = str((self.selected_source() or {}).get("id") or "")
        custom_sources = [
            dict(source)
            for source in sources
            if isinstance(source, dict)
            and source.get("id")
            and source.get("userInstalled")
            and source.get("sourceUrl")
        ]
        self._runtime_sources = {
            str(source.get("id") or ""): source for source in custom_sources
        }
        self.source_list.blockSignals(True)
        self.source_list.clear()
        target_item = None
        for source in custom_sources:
            source_id = str(source.get("id") or "")
            status = self._source_status(source)
            capabilities = source.get("capabilities")
            capabilities = capabilities if isinstance(capabilities, dict) else {}
            capability_text = " · ".join(
                [
                    f"搜索{'✓' if capabilities.get('search') else '—'}",
                    f"播放{'✓' if capabilities.get('playback') else '—'}",
                    f"下载{'✓' if capabilities.get('download') else '—'}",
                ]
            )
            item = QListWidgetItem(
                f"{source.get('name') or source_id}\n{status} · {capability_text} · {self._display_url(source)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, source)
            item.setToolTip(
                f"来源 ID：{source_id}\n状态：{status}\n能力：{capability_text}"
            )
            self.source_list.addItem(item)
            if source_id == selected_id:
                target_item = item
        self.source_list.blockSignals(False)
        if target_item is not None:
            self.source_list.setCurrentItem(target_item)
        elif self.source_list.count():
            self.source_list.setCurrentRow(0)
        else:
            self.on_selected_source_changed(None, None)
        self.source_list.scrollToTop()
        QTimer.singleShot(0, self.source_list.scrollToTop)
        self.status_label.setText(f"已注册 {len(custom_sources)} 个自定义来源。")

    def on_request_failed(self, _request_id: int, action: str, message: str) -> None:
        if action not in {"listSources", "reloadSource"}:
            return
        self.status_label.setText(f"读取来源状态失败：{message}")

    def selected_source(self) -> dict | None:
        item = self.source_list.currentItem()
        source = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return source if isinstance(source, dict) else None

    def on_selected_source_changed(self, current, _previous) -> None:
        source = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if not isinstance(source, dict):
            self.name_input.clear()
            self.source_detail_label.setText("选择一个来源查看状态。")
            self._set_detail_enabled(False)
            return
        self._set_detail_enabled(True)
        self.name_input.setText(str(source.get("name") or source.get("id") or ""))
        capabilities = source.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        self.source_detail_label.setText(
            f"状态：{self._source_status(source)}\n"
            f"搜索：{'支持' if capabilities.get('search') else '不支持'}\n"
            f"播放：{'支持' if capabilities.get('playback') else '不支持'}\n"
            f"下载：{'支持' if capabilities.get('download') else '不支持'}\n"
            f"来源 ID：{source.get('id') or ''}"
        )
        self.toggle_button.setText("禁用来源" if source.get("enabled") else "启用来源")

    def save_selected_name(self) -> None:
        source = self.selected_source()
        if source is None:
            return
        source_id = str(source.get("id") or "")
        try:
            self.registry.set_name(source_id, self.name_input.text())
        except SourceRegistryError as error:
            self.status_label.setText(f"保存名称失败：{error}")
            return
        self.client.reload_sources(source_id, timeout_ms=10000)
        self.sourcesChanged.emit(source_id)
        self.status_label.setText("来源名称已保存。")

    def toggle_selected_source(self) -> None:
        source = self.selected_source()
        if source is None:
            return
        source_id = str(source.get("id") or "")
        try:
            updated = self.registry.set_enabled(source_id, not bool(source.get("enabled")))
        except SourceRegistryError as error:
            self.status_label.setText(f"更新来源状态失败：{error}")
            return
        self.client.reload_sources(source_id, timeout_ms=10000)
        self.sourcesChanged.emit(source_id)
        state = "启用" if updated.get("enabled") else "禁用"
        self.status_label.setText(f"来源已{state}。")

    def remove_selected_source(self) -> None:
        source = self.selected_source()
        if source is None:
            return
        source_id = str(source.get("id") or "")
        name = str(source.get("name") or source_id)
        answer = QMessageBox.question(
            self,
            "移除自定义来源",
            f"确定移除“{name}”吗？\n已收藏或已加入歌单的远程歌曲记录会继续保留。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.registry.remove_source(source_id)
        except SourceRegistryError as error:
            self.status_label.setText(f"移除来源失败：{error}")
            return
        self._operation_errors.pop(source_id, None)
        self.client.reload_sources(timeout_ms=10000)
        self.sourcesChanged.emit(source_id)
        self.status_label.setText("来源已移除，远程歌曲记录仍然保留。")

    def _source_status(self, source: dict) -> str:
        source_id = str(source.get("id") or "")
        if self._operation_errors.get(source_id):
            return self._operation_errors[source_id]
        if source.get("scanError"):
            return "能力检测失败"
        if not source.get("fileExists", True) or not source.get("enabled"):
            return "不可用"
        capabilities = source.get("capabilities")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        if not any(capabilities.get(key) for key in ("search", "playback", "download")):
            return "能力检测失败"
        return "可用"

    @staticmethod
    def _display_url(source: dict) -> str:
        parts = urlsplit(str(source.get("sourceUrl") or ""))
        filename = Path(parts.path).name
        return f"{parts.hostname or '未知地址'}/{filename or 'source'}"

    def _set_busy(self, busy: bool) -> None:
        self.url_input.setEnabled(not busy)
        self.policy_combo.setEnabled(not busy)
        self.confirm_checkbox.setEnabled(not busy)
        self.source_list.setEnabled(not busy)
        self.add_button.setEnabled(not busy)
        self._set_detail_enabled(not busy and self.selected_source() is not None)

    def _set_detail_enabled(self, enabled: bool) -> None:
        self.name_input.setEnabled(enabled)
        self.save_name_button.setEnabled(enabled)
        self.toggle_button.setEnabled(enabled)
        self.update_button.setEnabled(enabled and self._active_reply is None)
        self.remove_button.setEnabled(enabled)
