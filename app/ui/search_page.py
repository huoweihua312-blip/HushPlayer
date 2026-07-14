from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.models.media_item import MediaItem
from app.ui.track_list_view import TrackListView
from app.ui.unified_search_panel import UnifiedSearchResultsPanel


class SearchPage(QFrame):
    backRequested = Signal()
    localOnlyChanged = Signal(bool)
    localBrowseRequested = Signal(dict)
    localPlayRequested = Signal(dict)
    localQueueNextRequested = Signal(dict)
    localLikeRequested = Signal(dict)
    localUnlikeRequested = Signal(dict)
    localAddToPlaylistRequested = Signal(dict, str)
    localRemoveFromCurrentPlaylistRequested = Signal(dict)
    localOpenFolderRequested = Signal(dict)
    localRemoveRequested = Signal(dict)
    localInfoRequested = Signal(dict)

    def __init__(self, local_only: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchPage")
        self._keyword = ""
        self._local_results: list[dict] = []
        self.local_state_provider = lambda _track: {}
        self.playlist_provider = lambda: []
        self._build_ui(local_only)

    def _build_ui(self, local_only: bool) -> None:
        layout = QVBoxLayout(self)
        self.page_layout = layout
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(16)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title_label = QLabel("搜索")
        self.title_label.setObjectName("pageTitle")
        self.title_label.setWordWrap(True)
        self.subtitle_label = QLabel("本地结果立即显示；在线结果会在停止输入后异步加载。")
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        self.local_only_checkbox = QCheckBox("仅搜索本地")
        self.local_only_checkbox.setChecked(bool(local_only))
        self.local_only_checkbox.toggled.connect(self.localOnlyChanged)
        self.back_button = QPushButton("返回音乐库")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.backRequested)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.local_only_checkbox)
        header.addWidget(self.back_button)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)
        self.local_tab = QPushButton("本地结果")
        self.online_tab = QPushButton("在线结果")
        for button in (self.local_tab, self.online_tab):
            button.setObjectName("searchTabButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.local_tab.clicked.connect(lambda checked=False: self.show_tab("local"))
        self.online_tab.clicked.connect(lambda checked=False: self.show_tab("online"))
        tab_row.addWidget(self.local_tab)
        tab_row.addWidget(self.online_tab)
        tab_row.addStretch()

        self.results_stack = QStackedWidget()
        self.local_container = QWidget()
        local_layout = QVBoxLayout(self.local_container)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(8)
        self.local_status_label = QLabel("点击左侧搜索框并输入关键词。")
        self.local_status_label.setObjectName("pageSubtitle")
        self.local_status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.local_status_label.setWordWrap(True)
        # Keep the former attribute available for callers outside this page.
        self.page_status = self.local_status_label
        self.local_view = TrackListView(
            object_name="localSearchResults",
            empty_text="输入关键词后显示本地搜索结果",
        )
        self.local_view.use_canonical_delegate()
        self.local_view.sortRequested.connect(self._sort_local_results)
        self.local_view.list_widget.itemClicked.connect(self._browse_local)
        self.local_view.list_widget.itemDoubleClicked.connect(self._play_local)
        self.local_view.list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.local_view.list_widget.customContextMenuRequested.connect(
            self._show_local_context_menu
        )
        local_layout.addWidget(self.local_status_label)
        local_layout.addWidget(self.local_view, 1)

        self.online_container = QWidget()
        online_layout = QVBoxLayout(self.online_container)
        online_layout.setContentsMargins(0, 0, 0, 0)
        online_layout.setSpacing(0)
        self.online_results = UnifiedSearchResultsPanel(
            self.online_container,
            standalone=True,
        )
        self.status_label = self.online_results.status_label
        online_layout.addWidget(self.online_results, 1)
        self.results_stack.addWidget(self.local_container)
        self.results_stack.addWidget(self.online_container)
        layout.addLayout(header)
        layout.addLayout(tab_row)
        layout.addWidget(self.results_stack, 1)
        self.setStyleSheet(
            "QPushButton#searchTabButton { background: #151922; color: #9ca5b5; border: 1px solid #2a303b; border-radius: 10px; padding: 8px 16px; font-weight: 700; }"
            "QPushButton#searchTabButton:hover { background: #202631; color: #eef1f7; }"
            "QPushButton#searchTabButton[active='true'] { background: rgba(76,141,255,0.20); color: #ffffff; border-color: rgba(76,141,255,0.55); }"
        )
        self.show_tab("local")

    def set_responsive_mode(self, mode: str) -> None:
        mode = mode if mode in {"full", "compact", "narrow"} else "full"
        self.subtitle_label.setVisible(mode != "narrow")
        self.local_status_label.setVisible(self.current_tab() == "local")
        if mode == "full":
            self.page_layout.setContentsMargins(28, 26, 28, 24)
        elif mode == "compact":
            self.page_layout.setContentsMargins(20, 20, 20, 18)
        else:
            self.page_layout.setContentsMargins(16, 16, 16, 14)

    def set_collection_providers(self, local_state_provider, playlist_provider) -> None:
        self.local_state_provider = local_state_provider or (lambda _track: {})
        self.playlist_provider = playlist_provider or (lambda: [])

    def set_playing_key_provider(self, provider) -> None:
        self.local_view.use_canonical_delegate(provider)
        self.online_results.set_playing_key_provider(provider)

    def refresh_playing_indicator(self) -> None:
        self.local_view.list_widget.viewport().update()
        self.online_results.refresh_playing_indicator()

    def set_keyword(self, keyword: str) -> None:
        self._keyword = str(keyword or "").strip()
        self.title_label.setText(f"搜索：{self._keyword}" if self._keyword else "搜索")
        if not self._keyword:
            self.page_status.setText("输入歌名、歌手或专辑")

    def set_local_results(self, keyword: str, results: list[dict]) -> None:
        self.set_keyword(keyword)
        self._local_results = [MediaItem.from_mapping(value).to_dict() for value in results]
        if not self._keyword:
            empty_text = "输入关键词后显示本地搜索结果"
        else:
            empty_text = "本地音乐库没有找到匹配歌曲"
        self.local_view.set_items(self._local_results, empty_text=empty_text)
        self.local_tab.setText(f"本地结果 · {len(self._local_results)}")
        if self.current_tab() == "local":
            self.local_status_label.setText(
                f"本地搜索完成，找到 {len(self._local_results)} 首歌曲"
                if self._keyword
                else "输入歌名、歌手或专辑"
            )

    def set_online_results(self, keyword: str, results: list[dict], summary: dict) -> None:
        self.set_keyword(keyword)
        self.online_results.set_results(keyword, results, summary)
        count = len(results)
        self.online_tab.setText(f"在线结果 · {count}")

    def clear_online_results(self) -> None:
        self.online_results.clear_results(hide=False)
        self.online_tab.setText("在线结果")

    def set_online_status(self, message: str) -> None:
        self.online_results.set_status(message)

    def show_tab(self, name: str) -> None:
        online = name == "online"
        self.results_stack.setCurrentWidget(
            self.online_container if online else self.local_container
        )
        self.local_container.setVisible(not online)
        self.online_container.setVisible(online)
        self.local_view.setVisible(not online)
        self.online_results.setVisible(online)
        self.local_status_label.setVisible(not online)
        self.local_tab.setProperty("active", not online)
        self.online_tab.setProperty("active", online)
        for button in (self.local_tab, self.online_tab):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        if not online:
            self.local_status_label.setText(
                f"本地搜索完成，找到 {len(self._local_results)} 首歌曲"
                if self._keyword
                else "输入歌名、歌手或专辑"
            )

    def current_tab(self) -> str:
        return (
            "online"
            if self.results_stack.currentWidget() is self.online_container
            else "local"
        )

    def _local_data(self, item: QListWidgetItem | None) -> dict | None:
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return value if isinstance(value, dict) else None

    def _browse_local(self, item: QListWidgetItem) -> None:
        value = self._local_data(item)
        if value is not None:
            self.localBrowseRequested.emit(dict(value))

    def _play_local(self, item: QListWidgetItem) -> None:
        value = self._local_data(item)
        if value is not None:
            self.localPlayRequested.emit(dict(value))

    def _show_local_context_menu(self, position: QPoint) -> None:
        item = self.local_view.list_widget.itemAt(position)
        value = self._local_data(item)
        if value is None:
            return
        self.local_view.list_widget.setCurrentItem(item)
        try:
            state = self.local_state_provider(value) or {}
        except Exception:
            state = {}
        menu = QMenu(self)
        play_action = menu.addAction("播放")
        play_action.triggered.connect(
            lambda checked=False, track=dict(value): self.localPlayRequested.emit(track)
        )
        next_action = menu.addAction("下一首播放")
        next_action.triggered.connect(
            lambda checked=False, track=dict(value): self.localQueueNextRequested.emit(track)
        )
        menu.addSeparator()
        if state.get("liked"):
            like_action = menu.addAction("取消收藏")
            like_action.triggered.connect(
                lambda checked=False, track=dict(value): self.localUnlikeRequested.emit(track)
            )
        else:
            like_action = menu.addAction("添加到我喜欢")
            like_action.triggered.connect(
                lambda checked=False, track=dict(value): self.localLikeRequested.emit(track)
            )
        playlist_menu = menu.addMenu("添加到歌单")
        try:
            playlists = list(self.playlist_provider() or [])
        except Exception:
            playlists = []
        if not playlists:
            empty = playlist_menu.addAction("暂无自定义歌单")
            empty.setEnabled(False)
        for playlist_id, playlist_name in playlists:
            action = playlist_menu.addAction(str(playlist_name))
            action.triggered.connect(
                lambda checked=False, track=dict(value), target=str(playlist_id):
                self.localAddToPlaylistRequested.emit(track, target)
            )
        if state.get("inCurrentPlaylist"):
            remove_current = menu.addAction("从当前歌单移除")
            remove_current.triggered.connect(
                lambda checked=False, track=dict(value):
                self.localRemoveFromCurrentPlaylistRequested.emit(track)
            )
        menu.addSeparator()
        open_action = menu.addAction("打开文件位置")
        open_action.triggered.connect(
            lambda checked=False, track=dict(value): self.localOpenFolderRequested.emit(track)
        )
        info_action = menu.addAction("查看歌曲信息")
        info_action.triggered.connect(
            lambda checked=False, track=dict(value): self.localInfoRequested.emit(track)
        )
        remove_action = menu.addAction("从音乐库移除")
        remove_action.triggered.connect(
            lambda checked=False, track=dict(value): self.localRemoveRequested.emit(track)
        )
        menu.exec(self.local_view.list_widget.mapToGlobal(position))

    def _sort_local_results(self, field: str) -> None:
        self._local_results.sort(
            key=lambda value: str(value.get(field) or "").casefold()
        )
        self.local_view.set_items(self._local_results)
