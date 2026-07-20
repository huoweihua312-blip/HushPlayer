from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.version import APP_USER_AGENT
from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import MAX_SOURCE_BYTES, SourceRegistryError, SourceRegistryManager
from app.ui.design_system import UI_CONTROL_SIZES, UI_SPACING
from app.ui.track_list_view import (
    OnlineTrackDelegate,
    OnlineTrackHeader,
    OnlineTrackListWidget,
)


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
    like_requested = Signal(dict)
    unlike_requested = Signal(dict)
    add_to_playlist_requested = Signal(dict, str)
    info_requested = Signal(dict)
    sources_changed = Signal(str)

    def __init__(
        self,
        client: OnlineSourceClient,
        registry: SourceRegistryManager | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.registry = registry
        self.current_search_request = 0
        self.current_detail_request = 0
        self.current_reload_request = 0
        self.sources_by_id: dict[str, dict] = {}
        self.network_manager = QNetworkAccessManager(self)
        self._source_download_reply: QNetworkReply | None = None
        self._pending_source_url = ""
        self._pending_keyword = ""
        self._pending_source_id = ""
        self._pending_update_source_id = ""
        self._pending_reload_completion = ""
        self.collection_state_provider = lambda _track: {}
        self.playlist_provider = lambda: []
        self._last_play_key = ""
        self._last_play_at = 0.0
        self.setObjectName("onlineSearchPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(UI_SPACING["md"])

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
        self.content_policy_checkbox = QCheckBox("我确认该 URL 仅提供开放内容或我拥有的内容")
        self.content_policy_checkbox.setEnabled(False)
        self.url_mode_checkbox.toggled.connect(self._set_url_mode_enabled)
        url_layout.addWidget(self.url_mode_checkbox)
        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.content_policy_checkbox)
        layout.addLayout(url_layout)

        search_row = QHBoxLayout()
        search_row.setSpacing(UI_SPACING["sm"])
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(190)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入歌曲、歌手或专辑")
        self.keyword_input.returnPressed.connect(self.start_search)
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self.start_search)
        refresh_button = QPushButton("刷新音源")
        refresh_button.clicked.connect(self.refresh_sources_or_update)
        search_row.addWidget(self.source_combo)
        search_row.addWidget(self.keyword_input, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(refresh_button)
        layout.addLayout(search_row)

        self.status_label = QLabel("正在连接音源服务…")
        self.status_label.setObjectName("onlineSourceStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.result_list = OnlineTrackListWidget()
        self.result_list.setObjectName("onlineSearchResults")
        self.result_list.setItemDelegate(OnlineTrackDelegate(parent=self.result_list))
        self.result_list.setUniformItemSizes(True)
        self.result_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_list.itemSelectionChanged.connect(self.update_detail_buttons)
        self.result_list.itemDoubleClicked.connect(self.request_playback)
        self.result_list.likeToggleRequested.connect(self._toggle_result_like)
        self.result_list.moreRequested.connect(
            lambda _track, position: self.show_result_context_menu(position)
        )
        self.result_list.customContextMenuRequested.connect(self.show_result_context_menu)
        self.result_header = OnlineTrackHeader(self)
        layout.addWidget(self.result_header)
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
        self.client.responseReceived.connect(self.on_response_received)
        self.client.requestFailed.connect(self.on_request_failed)
        self.client.processError.connect(self.on_process_error)

    def _set_url_mode_enabled(self, enabled: bool) -> None:
        self.url_input.setEnabled(enabled)
        self.content_policy_checkbox.setEnabled(enabled)

    def refresh_sources(self) -> None:
        self.status_label.setText("正在读取音源列表…")
        self.client.list_sources()

    def refresh_sources_or_update(self) -> None:
        if not self.url_mode_checkbox.isChecked() or not self.url_input.text().strip():
            self.refresh_sources()
            return
        if self.registry is None or not self.content_policy_checkbox.isChecked():
            self.status_label.setText("更新前请确认该 URL 仅用于开放内容或你拥有的内容。")
            return
        try:
            source_url = self.registry.normalize_source_url(self.url_input.text())
            existing = self.registry.find_by_source_url(source_url)
        except SourceRegistryError as error:
            self.status_label.setText(str(error))
            return
        if existing is None:
            self.status_label.setText("该 URL 尚未注册，请输入关键词并点击搜索完成首次注册。")
            return
        self._start_source_download(
            source_url,
            "",
            update_source_id=str(existing.get("id") or ""),
        )

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
                not source.get("userInstalled")
                or not source.get("sourceUrl")
                or not source.get("enabled")
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

        target_index = self.source_combo.findData(previous_id)

        if target_index >= 0:
            self.source_combo.setCurrentIndex(target_index)

        self.source_combo.blockSignals(False)
        self.status_label.setText(
            f"已注册自定义音源：{self.source_combo.count()} 个。双击可播放合规来源的结果。"
        )

    def start_search(self) -> None:
        keyword = self.keyword_input.text().strip()
        if not keyword:
            self.status_label.setText("请输入搜索关键词。")
            return

        if self.url_mode_checkbox.isChecked():
            if self.registry is None:
                self.status_label.setText("音源注册服务不可用。")
                return
            if not self.content_policy_checkbox.isChecked():
                self.status_label.setText("请先确认该 URL 仅用于开放内容或你拥有的内容。")
                return
            try:
                source_url = self.registry.normalize_source_url(self.url_input.text())
                existing = self.registry.find_by_source_url(source_url)
            except SourceRegistryError as error:
                self.status_label.setText(str(error))
                return
            if existing is not None:
                source_id = str(existing.get("id") or "")
                try:
                    self.registry.authorize_user_source(source_id, "user_owned")
                except SourceRegistryError as error:
                    self.status_label.setText(f"更新来源授权失败：{error}")
                    return
                self.sources_changed.emit(source_id)
                self._reload_then_search(source_id, keyword, "正在重载已注册来源…")
                return
            self._start_source_download(source_url, keyword)
            return
        else:
            source_id = str(self.source_combo.currentData() or "")
            if not source_id:
                self.status_label.setText("没有已注册的自定义来源；可勾选“使用自定义 URL”添加。")
                return

        self._begin_search(source_id, keyword)

    def _begin_search(self, source_id: str, keyword: str) -> None:
        self.search_button.setEnabled(False)
        self.result_list.clear()
        self.detail_view.clear()
        self.status_label.setText("正在异步搜索，请稍候…")
        self.current_search_request = self.client.search(source_id, keyword)

    def _reload_then_search(self, source_id: str, keyword: str, message: str) -> None:
        self.search_button.setEnabled(False)
        self._pending_source_id = source_id
        self._pending_keyword = keyword
        self.status_label.setText(message)
        self.current_reload_request = self.client.reload_sources(source_id)

    def _start_source_download(
        self,
        source_url: str,
        keyword: str,
        update_source_id: str = "",
    ) -> None:
        if self._source_download_reply is not None:
            self.status_label.setText("已有一个自定义来源正在注册，请稍候。")
            return
        self.search_button.setEnabled(False)
        self._pending_source_url = source_url
        self._pending_keyword = keyword
        self._pending_update_source_id = update_source_id
        request = QNetworkRequest(QUrl(source_url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        request.setRawHeader(
            b"User-Agent",
            f"{APP_USER_AGENT} custom-source-register".encode("ascii"),
        )
        request.setRawHeader(b"Accept", b"application/javascript, application/json, text/plain, */*")
        reply = self.network_manager.get(request)
        self._source_download_reply = reply
        self.status_label.setText("正在下载自定义来源并执行静态检查…")
        reply.downloadProgress.connect(
            lambda received, total, current_reply=reply: self._guard_source_size(
                current_reply, received, total
            )
        )
        reply.finished.connect(lambda current_reply=reply: self._finish_source_download(current_reply))

    @staticmethod
    def _guard_source_size(reply: QNetworkReply, received: int, total: int) -> None:
        if received > MAX_SOURCE_BYTES or total > MAX_SOURCE_BYTES:
            reply.setProperty("sourceTooLarge", True)
            reply.abort()

    def _finish_source_download(self, reply: QNetworkReply) -> None:
        if reply is not self._source_download_reply:
            reply.deleteLater()
            return
        self._source_download_reply = None
        source_url = self._pending_source_url
        keyword = self._pending_keyword
        update_source_id = self._pending_update_source_id
        self._pending_source_url = ""
        self._pending_update_source_id = ""
        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = "音源文件超过 2 MB。" if reply.property("sourceTooLarge") else reply.errorString()
            reply.deleteLater()
            self.search_button.setEnabled(True)
            self.status_label.setText(f"自定义来源注册失败：{message}")
            return
        content = bytes(reply.readAll())
        suggested_name = Path(reply.url().path()).name or "custom_source.js"
        reply.deleteLater()
        if self.registry is None:
            self.search_button.setEnabled(True)
            self.status_label.setText("音源注册服务不可用。")
            return
        try:
            existing = self.registry.get_source(update_source_id) if update_source_id else None
            content_sha = hashlib.sha256(content).hexdigest()
            if existing is not None and content_sha == str(existing.get("sha256") or "").casefold():
                self.search_button.setEnabled(True)
                self.status_label.setText("自定义来源内容未变化，无需更新。")
                return
            candidate = self.registry.stage_bytes(
                content,
                suggested_name,
                source_url=source_url,
                content_policy="user_owned",
                user_installed=True,
            )
            installed = (
                self.registry.update_candidate(update_source_id, candidate)
                if update_source_id
                else self.registry.install_candidate(candidate, enabled=True)
            )
        except SourceRegistryError as error:
            if update_source_id:
                self.search_button.setEnabled(True)
                self.status_label.setText(f"自定义来源更新失败：{error}")
                return
            existing = self.registry.find_by_source_url(source_url)
            if existing is None:
                self.search_button.setEnabled(True)
                self.status_label.setText(f"自定义来源注册失败：{error}")
                return
            installed = existing
        completion = (
            f"已安全更新“{installed.get('name') or installed.get('id')}”。"
            if update_source_id
            else f"已安全注册“{installed.get('name') or installed.get('id')}”。"
        )
        self.sources_changed.emit(str(installed.get("id") or update_source_id or ""))
        self._pending_reload_completion = completion
        self._reload_then_search(
            str(installed.get("id") or ""),
            keyword,
            f"{completion} 正在重载…",
        )

    def on_response_received(self, request_id: int, action: str, _data) -> None:
        if request_id != self.current_reload_request or action != "reloadSource":
            return
        self.current_reload_request = 0
        source_id = self._pending_source_id
        keyword = self._pending_keyword
        self._pending_source_id = ""
        self._pending_keyword = ""
        if keyword:
            self._pending_reload_completion = ""
            self._begin_search(source_id, keyword)
        else:
            self.search_button.setEnabled(True)
            self.status_label.setText(self._pending_reload_completion or "自定义来源已重载。")
            self._pending_reload_completion = ""

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
            item.setSizeHint(QSize(0, UI_CONTROL_SIZES["track_row_height"]))
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

    def set_collection_providers(self, state_provider, playlist_provider) -> None:
        self.collection_state_provider = state_provider or (lambda _track: {})
        self.playlist_provider = playlist_provider or (lambda: [])
        self.result_list.set_like_state_provider(self.collection_state_provider)

    def _toggle_result_like(self, result: dict) -> None:
        try:
            liked = bool((self.collection_state_provider(result) or {}).get("liked"))
        except Exception:
            liked = False
        signal = self.unlike_requested if liked else self.like_requested
        signal.emit(dict(result))

    def refresh_like_identity(self, identity: str) -> int:
        return self.result_list.refresh_like_identity(identity)

    def show_result_context_menu(self, position) -> None:
        item = self.result_list.itemAt(position)
        if item is None:
            return
        self.result_list.setCurrentItem(item)
        result = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, dict):
            return
        capabilities = self._result_capabilities(result)
        try:
            state = self.collection_state_provider(result) or {}
        except Exception:
            state = {}
        menu = QMenu(self)
        play_action = menu.addAction("播放")
        play_action.setEnabled(capabilities.get("playback") is True)
        play_action.triggered.connect(
            lambda checked=False, selected_item=item: self.request_playback(selected_item)
        )
        download_action = menu.addAction("下载")
        download_action.setEnabled(capabilities.get("download") is True)
        download_action.triggered.connect(self.request_download)
        menu.addSeparator()
        if state.get("liked"):
            like_action = menu.addAction("取消收藏")
            like_action.triggered.connect(
                lambda checked=False, track=dict(result): self.unlike_requested.emit(track)
            )
        else:
            like_action = menu.addAction("收藏到“我喜欢”")
            like_action.triggered.connect(
                lambda checked=False, track=dict(result): self.like_requested.emit(track)
            )
        playlist_menu = menu.addMenu("添加到歌单")
        try:
            playlists = list(self.playlist_provider() or [])
        except Exception:
            playlists = []
        if not playlists:
            empty_action = playlist_menu.addAction("暂无自定义歌单")
            empty_action.setEnabled(False)
        for playlist_id, playlist_name in playlists:
            action = playlist_menu.addAction(str(playlist_name))
            action.triggered.connect(
                lambda checked=False, track=dict(result), target_id=str(playlist_id):
                self.add_to_playlist_requested.emit(track, target_id)
            )
        menu.addSeparator()
        info_action = menu.addAction("查看歌曲信息")
        info_action.triggered.connect(
            lambda checked=False, track=dict(result): self.info_requested.emit(track)
        )
        menu.exec(self.result_list.mapToGlobal(position))

    def set_online_status(self, message: str) -> None:
        self.status_label.setText(str(message))

    def on_request_failed(self, request_id: int, _action: str, message: str) -> None:
        if request_id not in {
            self.current_search_request,
            self.current_detail_request,
            self.current_reload_request,
        }:
            return

        if request_id == self.current_reload_request:
            self.current_reload_request = 0
            self._pending_source_id = ""
            self._pending_keyword = ""
        self.search_button.setEnabled(True)
        self.status_label.setText(f"请求失败：{message}")

    def on_process_error(self, message: str) -> None:
        self.search_button.setEnabled(True)
        self.status_label.setText(f"音源服务错误：{message}")
