from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import MAX_SOURCE_BYTES, SourceRegistryError, SourceRegistryManager


def _format_duration(value) -> str:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        seconds = 0

    if seconds <= 0:
        return "未知"

    return f"{seconds // 60}:{seconds % 60:02d}"


class OnlineSearchPage(QFrame):
    play_requested = Signal(dict)
    download_requested = Signal(dict)
    

    def __init__(self, client: OnlineSourceClient, parent=None) -> None:
        super().__init__(parent)
        self.client = client
        self.current_search_request = 0
        self.current_detail_request = 0
        self.sources_by_id: dict[str, dict] = {}
        self._last_play_key = ""
        self._last_play_at = 0.0
        self.setObjectName("onlineSearchPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(16)

        title = QLabel("在线搜索")
        title.setObjectName("pageTitle")
        subtitle = QLabel("在线能力由独立 Node 音源进程提供；播放和下载仅对开放内容或用户自有内容启用。")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        
        url_layout = QHBoxLayout()
        self.url_mode_checkbox = QCheckBox("使用自定义 URL")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入 .js 或 .json 音源链接")
        self.url_input.setEnabled(False)
        self.url_mode_checkbox.toggled.connect(self.url_input.setEnabled)
        url_layout.addWidget(self.url_mode_checkbox)
        url_layout.addWidget(self.url_input, 1)
        layout.addLayout(url_layout)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(190)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入歌曲、歌手或专辑")
        self.keyword_input.returnPressed.connect(self.start_search)
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.start_search)
        refresh_button = QPushButton("刷新音源")
        refresh_button.clicked.connect(self.refresh_sources)
        search_row.addWidget(self.source_combo)
        search_row.addWidget(self.keyword_input, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(refresh_button)
        layout.addLayout(search_row)

        self.status_label = QLabel("正在连接音源服务…")
        self.status_label.setObjectName("onlineSourceStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.result_list = QListWidget()
        self.result_list.setObjectName("onlineSearchResults")
        self.result_list.setUniformItemSizes(True)
        self.result_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.result_list.itemSelectionChanged.connect(self.update_detail_buttons)
        self.result_list.itemDoubleClicked.connect(self.request_playback)
        layout.addWidget(self.result_list, 1)

        action_row = QHBoxLayout()
        self.metadata_button = QPushButton("读取元数据")
        self.metadata_button.setEnabled(False)
        self.metadata_button.clicked.connect(self.request_metadata)
        self.lyric_button = QPushButton("读取歌词")
        self.lyric_button.setEnabled(False)
        self.lyric_button.clicked.connect(self.request_lyric)
        self.download_button = QPushButton("下载")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.request_download)
        action_row.addWidget(self.metadata_button)
        action_row.addWidget(self.lyric_button)
        action_row.addWidget(self.download_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setObjectName("onlineSourceDetail")
        self.detail_view.setReadOnly(True)
        self.detail_view.setMaximumHeight(190)
        self.detail_view.setPlaceholderText("选择搜索结果后，可读取元数据或歌词。")
        layout.addWidget(self.detail_view)

        self.client.sourceReady.connect(self.on_source_ready)
        self.client.sourceListReceived.connect(self.on_source_list_received)
        self.client.searchFinished.connect(self.on_search_finished)
        self.client.metadataFinished.connect(self.on_metadata_finished)
        self.client.lyricFinished.connect(self.on_lyric_finished)
        self.client.requestFailed.connect(self.on_request_failed)
        self.client.processError.connect(self.on_process_error)

    def refresh_sources(self) -> None:
        self.status_label.setText("正在读取音源列表…")
        self.client.list_sources()

    def on_source_ready(self, data: dict) -> None:
        self.status_label.setText(
            f"音源服务已连接 · {data.get('protocol', 'JSONL')}"
        )

    def on_source_list_received(self, sources: list) -> None:
        self.sources_by_id = {
            str(source.get("id") or ""): source
            for source in sources
            if isinstance(source, dict) and source.get("id")
        }
        previous_id = self.source_combo.currentData()
        self.source_combo.blockSignals(True)
        self.source_combo.clear()

        for source in sources:
            capabilities = source.get("capabilities") or {}

            if (
                not source.get("enabled")
                or not capabilities.get("search")
                or source.get("scanError")
                or not source.get("fileExists", True)
            ):
                continue

            label = str(source.get("name") or source.get("id") or "未知音源")

            if source.get("experimental"):
                label += "（实验性）"

            self.source_combo.addItem(label, source.get("id"))
            index = self.source_combo.count() - 1
            self.source_combo.setItemData(index, source, Qt.ItemDataRole.UserRole + 1)

        target_index = self.source_combo.findData(previous_id or "netease")

        if target_index >= 0:
            self.source_combo.setCurrentIndex(target_index)

        self.source_combo.blockSignals(False)
        self.status_label.setText(
            f"可搜索音源：{self.source_combo.count()} 个。双击可试播已合规启用播放能力的结果。"
        )

    def start_search(self) -> None:
        if self.url_mode_checkbox.isChecked():
            source_id = self.url_input.text().strip()
            if not source_id.startswith(("http://", "https://")):
                self.status_label.setText("请输入有效的 HTTPS/HTTP 地址。")
                return
        else:
            source_id = str(self.source_combo.currentData() or "")
            if not source_id:
                self.status_label.setText("没有可用音源，请先到“音源管理”检查启用状态。")
                return

        keyword = self.keyword_input.text().strip()
        if not keyword:
            self.status_label.setText("请输入搜索关键词。")
            return

        self.search_button.setEnabled(False)
        self.result_list.clear()
        self.detail_view.clear()
        self.status_label.setText("正在异步搜索，请稍候…")
        self.current_search_request = self.client.search(source_id, keyword)

    def on_search_finished(self, request_id: int, source_id: str, results: list) -> None:
        if request_id != self.current_search_request:
            return

        self.search_button.setEnabled(True)

        for result in results:
            title = str(result.get("title") or "未知歌曲")
            artist = str(result.get("artist") or "未知艺术家")
            album = str(result.get("album") or "未知专辑")
            source_name = str(result.get("sourceName") or source_id)
            duration = _format_duration(result.get("duration"))
            item = QListWidgetItem(f"{title}\n{artist} · {album}   |   {source_name}   |   {duration}")
            item.setData(Qt.ItemDataRole.UserRole, result)
            item.setToolTip(f"歌曲：{title}\n歌手：{artist}\n专辑：{album}\n来源：{source_name}")
            item.setSizeHint(QSize(0, 52))
            self.result_list.addItem(item)

        if results:
            self.status_label.setText(f"搜索完成，共 {len(results)} 条结果。单击浏览，双击试播可播放结果。")
        else:
            self.status_label.setText("没有找到匹配结果。")

    def selected_result(self) -> dict | None:
        item = self.result_list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return data if isinstance(data, dict) else None

    def update_detail_buttons(self) -> None:
        result = self.selected_result()
        enabled = result is not None
        self.metadata_button.setEnabled(enabled)
        self.lyric_button.setEnabled(enabled)
        capabilities = self._result_capabilities(result)
        self.download_button.setEnabled(enabled and capabilities.get("download") is True)

    def request_metadata(self) -> None:
        result = self.selected_result()

        if result is None:
            return

        self.status_label.setText("正在读取元数据…")
        self.current_detail_request = self.client.get_metadata(str(result.get("sourceId") or ""), result)

    def request_lyric(self) -> None:
        result = self.selected_result()

        if result is None:
            return

        self.status_label.setText("正在读取歌词…")
        self.current_detail_request = self.client.get_lyric(str(result.get("sourceId") or ""), result)

    def on_metadata_finished(self, request_id: int, _source_id: str, data: dict) -> None:
        if request_id != self.current_detail_request:
            return

        self.detail_view.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self.status_label.setText("元数据读取完成。")

    def on_lyric_finished(self, request_id: int, _source_id: str, data: dict) -> None:
        if request_id != self.current_detail_request:
            return

        lyric = str(data.get("rawLrc") or "").strip()
        self.detail_view.setPlainText(lyric or "该音源没有返回歌词。")
        self.status_label.setText("歌词接口请求完成。")

    def _result_capabilities(self, result: dict | None) -> dict:
        if not isinstance(result, dict):
            return {}
        capabilities = result.get("capabilities")
        if isinstance(capabilities, dict):
            return capabilities
        source = self.sources_by_id.get(str(result.get("sourceId") or ""), {})
        return source.get("capabilities") if isinstance(source.get("capabilities"), dict) else {}

    def request_playback(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, dict):
            return
        if self._result_capabilities(result).get("playback") is not True:
            self.status_label.setText("该音源未启用播放能力。")
            return

        request_key = f"{result.get('sourceId')}:{result.get('id')}:{result.get('songmid')}"
        now = time.monotonic()
        if request_key == self._last_play_key and now - self._last_play_at < 0.6:
            return
        self._last_play_key = request_key
        self._last_play_at = now
        self.status_label.setText("正在获取播放地址…")
        self.play_requested.emit(dict(result))

    def request_download(self) -> None:
        result = self.selected_result()
        if result is None:
            return
        if self._result_capabilities(result).get("download") is not True:
            self.status_label.setText("该音源未启用下载能力。")
            return
        self.status_label.setText("正在获取下载地址…")
        self.download_requested.emit(dict(result))

    def set_online_status(self, message: str) -> None:
        self.status_label.setText(str(message))

    def on_request_failed(self, request_id: int, _action: str, message: str) -> None:
        if request_id not in {self.current_search_request, self.current_detail_request}:
            return

        self.search_button.setEnabled(True)
        self.status_label.setText(f"请求失败：{message}")

    def on_process_error(self, message: str) -> None:
        self.search_button.setEnabled(True)
        self.status_label.setText(f"音源服务错误：{message}")


class SourceManagerPage(QFrame):
    def __init__(
        self,
        client: OnlineSourceClient,
        registry: SourceRegistryManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.registry = registry
        self.current_test_request = 0
        self.current_test_source_id = ""
        self._download_reply: QNetworkReply | None = None
        self.network_manager = QNetworkAccessManager(self)
        self.sources_by_id: dict[str, dict] = {}
        self.setObjectName("sourceManagerPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 26)
        layout.setSpacing(14)

        title = QLabel("音源管理")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "音源在独立 Node 进程中运行。新音源默认禁用；静态扫描不能替代完整安全沙箱。"
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入 HTTPS/HTTP 的 .js 或 .json 音源地址")
        self.import_url_button = QPushButton("导入 URL")
        self.import_url_button.clicked.connect(self.import_from_url)
        self.import_file_button = QPushButton("选择本地文件")
        self.import_file_button.clicked.connect(self.import_local_file)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.import_url_button)
        url_row.addWidget(self.import_file_button)
        layout.addLayout(url_row)

        self.status_label = QLabel("正在读取音源注册表…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.source_tree = QTreeWidget()
        self.source_tree.setObjectName("sourceManagerTree")
        self.source_tree.setHeaderLabels(["音源", "版本", "状态", "能力", "上次测试"])
        self.source_tree.setRootIsDecorated(False)
        self.source_tree.setAlternatingRowColors(True)
        self.source_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.source_tree.itemSelectionChanged.connect(self.update_action_buttons)
        self.source_tree.header().setStretchLastSection(True)
        layout.addWidget(self.source_tree, 1)

        action_row = QHBoxLayout()
        self.toggle_button = QPushButton("启用 / 禁用")
        self.toggle_button.setEnabled(False)
        self.toggle_button.clicked.connect(self.toggle_selected_source)
        self.test_button = QPushButton("测试音源")
        self.test_button.setEnabled(False)
        self.test_button.clicked.connect(self.test_selected_source)
        self.delete_button = QPushButton("删除音源")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected_source)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh_sources)
        action_row.addWidget(self.toggle_button)
        action_row.addWidget(self.test_button)
        action_row.addWidget(self.delete_button)
        action_row.addWidget(refresh_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.test_output = QPlainTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setMaximumHeight(210)
        self.test_output.setPlaceholderText("选择音源并点击“测试音源”，这里会显示加载、搜索、元数据和歌词结果。")
        layout.addWidget(self.test_output)

        self.client.sourceListReceived.connect(self.on_source_list_received)
        self.client.sourceTestFinished.connect(self.on_source_test_finished)
        self.client.requestFailed.connect(self.on_request_failed)
        self.client.processError.connect(self.on_process_error)

    def refresh_sources(self) -> None:
        self.status_label.setText("正在刷新音源列表…")
        self.client.list_sources()

    def on_source_list_received(self, sources: list) -> None:
        selected_id = self.selected_source_id()
        self.sources_by_id = {
            str(source.get("id")): source
            for source in sources
            if isinstance(source, dict) and source.get("id")
        }
        self.source_tree.clear()

        for source in sources:
            source_id = str(source.get("id") or "")

            if not source_id:
                continue

            capabilities = source.get("capabilities") or {}
            features = " / ".join(
                label
                for key, label in (
                    ("search", "搜索"),
                    ("metadata", "元数据"),
                    ("lyrics", "歌词"),
                    ("playback", "播放"),
                    ("download", "下载"),
                )
                if capabilities.get(key)
            ) or "未识别"
            state = "已启用" if source.get("enabled") else "已禁用"

            if source.get("experimental"):
                state += " · 实验性"

            if source.get("scanError"):
                state += " · 扫描失败"

            item = QTreeWidgetItem(
                [
                    str(source.get("name") or source_id),
                    str(source.get("version") or "未知"),
                    state,
                    features,
                    str(source.get("lastTestStatus") or "未测试"),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, source_id)
            item.setToolTip(0, str(source.get("sourceUrl") or source.get("filename") or ""))
            self.source_tree.addTopLevelItem(item)

            if source_id == selected_id:
                self.source_tree.setCurrentItem(item)

        for column in range(4):
            self.source_tree.resizeColumnToContents(column)

        self.status_label.setText(
            f"已安装 {len(self.sources_by_id)} 个音源。播放/下载能力需通过内容策略与运行时接口双重校验。"
        )
        self.update_action_buttons()

    def selected_source_id(self) -> str:
        item = self.source_tree.currentItem()
        return str(item.data(0, Qt.ItemDataRole.UserRole) or "") if item is not None else ""

    def update_action_buttons(self) -> None:
        enabled = bool(self.selected_source_id())
        self.toggle_button.setEnabled(enabled)
        self.test_button.setEnabled(enabled and not self.current_test_request)
        self.delete_button.setEnabled(enabled and not self.current_test_request)

    def import_local_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择音源文件",
            str(Path.home()),
            "音源文件 (*.js *.json)",
        )

        if not filename:
            return

        try:
            candidate = self.registry.stage_local_file(Path(filename))
        except SourceRegistryError as error:
            QMessageBox.warning(self, "音源导入失败", str(error))
            return

        self.confirm_candidate(candidate)

    def import_from_url(self) -> None:
        url = QUrl(self.url_input.text().strip())

        if not url.isValid() or url.scheme().lower() not in {"https", "http"}:
            QMessageBox.information(self, "导入音源", "请输入有效的 HTTPS 或 HTTP 地址。")
            return

        if self._download_reply is not None:
            QMessageBox.information(self, "导入音源", "已有一个音源正在下载。")
            return

        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"HushPlayer/1.0 source-manager")
        request.setRawHeader(b"Accept", b"application/javascript, application/json, text/plain, */*")
        self.import_url_button.setEnabled(False)
        self.status_label.setText("正在异步下载到 staging…")
        reply = self.network_manager.get(request)
        self._download_reply = reply
        reply.downloadProgress.connect(
            lambda received, total, current_reply=reply: self.guard_download_size(
                current_reply,
                received,
                total,
            )
        )
        reply.readyRead.connect(
            lambda current_reply=reply: self.guard_download_size(
                current_reply,
                current_reply.bytesAvailable(),
                -1,
            )
        )
        reply.finished.connect(lambda current_reply=reply: self.finish_url_import(current_reply))

    @staticmethod
    def guard_download_size(reply: QNetworkReply, received: int, total: int) -> None:
        if received > MAX_SOURCE_BYTES or total > MAX_SOURCE_BYTES:
            reply.setProperty("sourceTooLarge", True)
            reply.abort()

    def finish_url_import(self, reply: QNetworkReply) -> None:
        self.import_url_button.setEnabled(True)
        self._download_reply = None
        url_text = reply.url().toString()

        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = (
                "音源文件超过 2 MB，已停止下载。"
                if reply.property("sourceTooLarge")
                else reply.errorString()
            )
            reply.deleteLater()
            QMessageBox.warning(self, "音源下载失败", message)
            self.status_label.setText(f"下载失败：{message}")
            return

        content = bytes(reply.readAll())
        suggested_name = Path(reply.url().path()).name or "remote_source.js"
        reply.deleteLater()

        try:
            candidate = self.registry.stage_bytes(content, suggested_name, source_url=url_text)
        except SourceRegistryError as error:
            QMessageBox.warning(self, "音源导入失败", str(error))
            self.status_label.setText(f"导入失败：{error}")
            return

        self.confirm_candidate(candidate)

    def confirm_candidate(self, candidate: dict) -> None:
        description = self.registry.describe_candidate(candidate)
        answer = QMessageBox.question(
            self,
            "确认安装音源",
            f"{description}\n\n确认安装到独立音源目录吗？安装后默认禁用。",
        )

        if answer != QMessageBox.StandardButton.Yes:
            self.status_label.setText("音源保留在 staging，尚未安装。")
            return

        try:
            installed = self.registry.install_candidate(candidate)
        except SourceRegistryError as error:
            QMessageBox.warning(self, "音源安装失败", str(error))
            self.status_label.setText(f"安装失败：{error}")
            return

        self.status_label.setText(f"已安装“{installed.get('name')}”，默认处于禁用状态。")
        self.client.reload_sources()

    def toggle_selected_source(self) -> None:
        source_id = self.selected_source_id()
        source = self.sources_by_id.get(source_id)

        if source is None:
            return

        new_enabled = not bool(source.get("enabled"))

        if new_enabled:
            answer = QMessageBox.question(
                self,
                "启用不可信音源",
                "该音源代码不属于 HushPlayer。静态扫描不能提供完整沙箱保护，确认启用吗？",
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            self.registry.set_enabled(source_id, new_enabled)
        except SourceRegistryError as error:
            QMessageBox.warning(self, "更新失败", str(error))
            return

        self.status_label.setText("启用状态已保存，正在重载 Node 音源缓存…")
        self.client.reload_sources(source_id)

    def delete_selected_source(self) -> None:
        source_id = self.selected_source_id()
        source = self.sources_by_id.get(source_id)
        if source is None:
            return

        source_name = str(source.get("name") or source_id)
        answer = QMessageBox.warning(
            self,
            "删除音源",
            f"确定删除“{source_name}”吗？\n\n"
            "该音源会从注册表移除。HushPlayer 管理目录中的文件会移入 backups，"
            "外部文件只移除注册记录，不会删除原文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.delete_button.setEnabled(False)
        try:
            result = self.registry.remove_source(source_id)
        except SourceRegistryError as error:
            QMessageBox.warning(self, "删除音源失败", str(error))
            self.status_label.setText(f"删除失败：{error}")
            self.update_action_buttons()
            return

        backup_path = str(result.get("backupPath") or "")
        if backup_path:
            message = f"已删除“{source_name}”，原音源文件已备份到：{backup_path}"
        elif result.get("externalFilePreserved"):
            message = f"已删除“{source_name}”的注册记录，外部源文件保持不变。"
        else:
            message = f"已删除“{source_name}”的注册记录。"
        self.status_label.setText(message)
        self.test_output.clear()
        self.sources_by_id.pop(source_id, None)
        current_item = self.source_tree.currentItem()
        if current_item is not None:
            item_index = self.source_tree.indexOfTopLevelItem(current_item)
            if item_index >= 0:
                self.source_tree.takeTopLevelItem(item_index)
        self.update_action_buttons()
        self.client.reload_sources(source_id)

    def test_selected_source(self) -> None:
        source_id = self.selected_source_id()

        if not source_id:
            return

        self.current_test_source_id = source_id
        self.test_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.test_output.setPlainText("正在独立 Node 进程中测试加载、搜索、元数据和歌词…\n不会测试播放地址。")
        self.current_test_request = self.client.test_source(source_id)

    def on_source_test_finished(self, request_id: int, source_id: str, data: dict) -> None:
        if request_id != self.current_test_request:
            return

        self.current_test_request = 0
        self.test_button.setEnabled(True)
        self.update_action_buttons()
        statuses = [
            str((data.get(name) or {}).get("status") or "skipped")
            for name in ("load", "search", "metadata", "lyric")
        ]
        overall_status = "passed" if all(status in {"passed", "skipped"} for status in statuses) else "failed"

        try:
            self.registry.record_test_result(source_id, overall_status)
        except SourceRegistryError:
            pass

        self.test_output.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self.status_label.setText(f"音源测试完成：{overall_status}。播放接口未测试。")
        self.client.reload_sources(source_id)

    def on_request_failed(self, request_id: int, action: str, message: str) -> None:
        if request_id != self.current_test_request and action not in {"listSources", "reloadSource"}:
            return

        if request_id == self.current_test_request:
            self.current_test_request = 0
            self.test_button.setEnabled(True)
            self.update_action_buttons()
            self.test_output.setPlainText(f"测试失败：{message}")

        self.status_label.setText(f"音源操作失败：{message}")

    def on_process_error(self, message: str) -> None:
        self.status_label.setText(f"Node runner 错误：{message}")
