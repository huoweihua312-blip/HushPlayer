from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.models.media_item import MediaItem
from app.ui.track_list_view import TrackListView
from app.ui.unified_search_panel import UnifiedSearchResultsPanel


class SearchSourceSelector(QToolButton):
    selectionChanged = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchSourceSelector")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMinimumWidth(170)
        self._sources: list[dict] = []
        self._checkboxes: dict[str, QCheckBox] = {}
        self._selected_ids: set[str] = set()
        self._updating = False
        self._loading = True
        self._build_menu()
        self.set_loading()

    def _build_menu(self) -> None:
        menu = QMenu(self)
        menu.setObjectName("searchSourceMenu")
        panel = QFrame(menu)
        panel.setObjectName("searchSourceMenuPanel")
        panel.setMinimumWidth(300)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)
        panel_layout.setSpacing(8)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.select_all_button = QPushButton("全选")
        self.clear_button = QPushButton("取消全选")
        self.select_all_button.setObjectName("secondaryButton")
        self.clear_button.setObjectName("secondaryButton")
        self.select_all_button.clicked.connect(self.select_all)
        self.clear_button.clicked.connect(self.clear_selection)
        action_row.addWidget(self.select_all_button)
        action_row.addWidget(self.clear_button)
        action_row.addStretch()
        panel_layout.addLayout(action_row)

        self.source_scroll = QScrollArea(panel)
        self.source_scroll.setWidgetResizable(True)
        self.source_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.source_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.source_scroll.setMaximumHeight(320)
        self.source_container = QWidget(self.source_scroll)
        self.source_layout = QVBoxLayout(self.source_container)
        self.source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_layout.setSpacing(5)
        self.source_scroll.setWidget(self.source_container)
        panel_layout.addWidget(self.source_scroll)

        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(panel)
        menu.addAction(widget_action)
        self.setMenu(menu)

    def set_loading(self) -> None:
        self._loading = True
        self.setText("正在读取来源…")
        self.setEnabled(False)

    def set_sources(self, sources: list[dict], selected_ids: list[str]) -> None:
        normalized_sources = [dict(source) for source in sources if isinstance(source, dict)]
        selected_set = {str(source_id or "").strip() for source_id in selected_ids}
        selected_set.discard("")
        signature = [
            (
                str(source.get("id") or ""),
                str(source.get("name") or ""),
                bool(source.get("selectable")),
                str(source.get("reason") or ""),
            )
            for source in normalized_sources
        ]
        current_signature = [
            (
                str(source.get("id") or ""),
                str(source.get("name") or ""),
                bool(source.get("selectable")),
                str(source.get("reason") or ""),
            )
            for source in self._sources
        ]
        self._sources = normalized_sources
        self._selected_ids = selected_set
        self._loading = False
        if signature != current_signature:
            self._rebuild_source_checkboxes()
        else:
            self._sync_checkbox_states()
        self._update_button_text()
        self.setEnabled(self.has_sources())

    def _clear_source_layout(self) -> None:
        while self.source_layout.count():
            item = self.source_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._checkboxes.clear()

    def _rebuild_source_checkboxes(self) -> None:
        self._updating = True
        self._clear_source_layout()
        if not self._sources:
            empty_label = QLabel("没有已启用的自定义来源")
            empty_label.setObjectName("pageSubtitle")
            self.source_layout.addWidget(empty_label)
        for source in self._sources:
            source_id = str(source.get("id") or "").strip()
            if not source_id:
                continue
            source_name = str(source.get("name") or source_id)
            selectable = bool(source.get("selectable"))
            reason = str(source.get("reason") or "").strip()
            label = source_name if selectable or not reason else f"{source_name}（{reason}）"
            checkbox = QCheckBox(label, self.source_container)
            checkbox.setChecked(selectable and source_id in self._selected_ids)
            checkbox.setEnabled(selectable)
            if reason:
                checkbox.setToolTip(reason)
            checkbox.toggled.connect(
                lambda checked, current_id=source_id:
                self._on_source_toggled(current_id, checked)
            )
            self._checkboxes[source_id] = checkbox
            self.source_layout.addWidget(checkbox)
        self.source_layout.addStretch()
        self._updating = False

    def _sync_checkbox_states(self) -> None:
        self._updating = True
        for source in self._sources:
            source_id = str(source.get("id") or "")
            checkbox = self._checkboxes.get(source_id)
            if checkbox is not None:
                checkbox.setChecked(
                    bool(source.get("selectable"))
                    and source_id in self._selected_ids
                )
        self._updating = False

    def _on_source_toggled(self, source_id: str, checked: bool) -> None:
        if self._updating:
            return
        if checked:
            self._selected_ids.add(source_id)
        else:
            self._selected_ids.discard(source_id)
        self._emit_selection()

    def select_all(self) -> None:
        self._selected_ids = {
            str(source.get("id") or "")
            for source in self._sources
            if source.get("selectable") and str(source.get("id") or "")
        }
        self._sync_checkbox_states()
        self._emit_selection()

    def clear_selection(self) -> None:
        self._selected_ids.clear()
        self._sync_checkbox_states()
        self._emit_selection()

    def selected_source_ids(self) -> list[str]:
        return [
            str(source.get("id") or "")
            for source in self._sources
            if source.get("selectable")
            and str(source.get("id") or "") in self._selected_ids
        ]

    def has_selectable_sources(self) -> bool:
        return any(source.get("selectable") for source in self._sources)

    def has_sources(self) -> bool:
        return bool(self._sources)

    def _emit_selection(self) -> None:
        self._update_button_text()
        self.selectionChanged.emit(self.selected_source_ids())

    def _update_button_text(self) -> None:
        if self._loading:
            self.setText("正在读取来源…")
            return
        selectable = [source for source in self._sources if source.get("selectable")]
        selected_ids = self.selected_source_ids()
        self.select_all_button.setEnabled(bool(selectable))
        self.clear_button.setEnabled(bool(selected_ids))
        if not selectable:
            self.setText("无可用来源")
        elif not selected_ids:
            self.setText("未选择来源")
        elif len(selected_ids) == len(selectable):
            self.setText("全部来源")
        elif len(selected_ids) == 1:
            selected_id = selected_ids[0]
            selected = next(
                (source for source in selectable if str(source.get("id") or "") == selected_id),
                {},
            )
            self.setText(str(selected.get("name") or selected_id))
        else:
            self.setText(f"已选择 {len(selected_ids)} 个来源")


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
        self._source_service = getattr(parent, "unified_search_service", None)
        self._settings_owner = parent
        self._responsive_mode = "full"
        self._keyword = ""
        self._local_results: list[dict] = []
        self.local_state_provider = lambda _track: {}
        self.playlist_provider = lambda: []
        self._build_ui(local_only)
        self._connect_source_service()

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
        self.local_only_checkbox.toggled.connect(self._sync_source_selector_state)
        self.source_selector_label = QLabel("搜索来源：")
        self.source_selector_label.setObjectName("pageSubtitle")
        self.source_selector = SearchSourceSelector(self)
        self.source_selector.selectionChanged.connect(
            self._on_source_selection_changed
        )
        self.back_button = QPushButton("返回音乐库")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.backRequested)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.source_selector_label)
        header.addWidget(self.source_selector)
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
        self.local_view.list_widget.likeToggleRequested.connect(
            self._toggle_local_like
        )
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
            "QToolButton#searchSourceSelector { background: #151922; color: #eef1f7; border: 1px solid #303744; border-radius: 9px; padding: 7px 12px; font-weight: 650; }"
            "QToolButton#searchSourceSelector:hover { background: #202631; border-color: #465066; }"
            "QToolButton#searchSourceSelector:disabled { color: #737d8f; background: #12161d; border-color: #252b35; }"
            "QFrame#searchSourceMenuPanel { background: #171c25; border: 1px solid #303744; border-radius: 10px; }"
        )
        self.show_tab("local")

    def _connect_source_service(self) -> None:
        service = self._source_service
        if service is None:
            self.source_selector.set_sources([], [])
            self._sync_source_selector_state()
            return
        service.sourceCatalogChanged.connect(self._on_source_catalog_changed)
        getter = getattr(self._settings_owner, "get_user_setting", None)
        saved_ids = getter("online_search_selected_sources", None) if callable(getter) else None
        if isinstance(saved_ids, list):
            service.set_selected_source_ids(saved_ids, restart=False)
        if service.source_catalog_loaded:
            self._on_source_catalog_changed(
                service.source_catalog,
                service.selected_source_ids,
            )
        else:
            self.source_selector.set_loading()
        self._sync_source_selector_state()

    def _on_source_catalog_changed(
        self,
        sources: list[dict],
        selected_ids: list[str],
    ) -> None:
        self.source_selector.set_sources(sources, selected_ids)
        self._sync_source_selector_state()

    def _on_source_selection_changed(self, source_ids: list[str]) -> None:
        service = self._source_service
        if service is not None:
            service.set_selected_source_ids(source_ids)
        saver = getattr(self._settings_owner, "save_hush_settings", None)
        if callable(saver):
            saver({"online_search_selected_sources": list(source_ids)})
        self._sync_source_selector_state()

    def _sync_source_selector_state(self, *_args) -> None:
        online = hasattr(self, "results_stack") and self.current_tab() == "online"
        self.source_selector_label.setVisible(
            online and self._responsive_mode != "narrow"
        )
        self.source_selector.setVisible(online)
        self.source_selector.setEnabled(
            online
            and not self.local_only_checkbox.isChecked()
            and self.source_selector.has_sources()
        )

    def set_responsive_mode(self, mode: str) -> None:
        mode = mode if mode in {"full", "compact", "narrow"} else "full"
        self._responsive_mode = mode
        self.subtitle_label.setVisible(mode != "narrow")
        self.local_status_label.setVisible(self.current_tab() == "local")
        if mode == "full":
            self.page_layout.setContentsMargins(28, 26, 28, 24)
        elif mode == "compact":
            self.page_layout.setContentsMargins(20, 20, 20, 18)
        else:
            self.page_layout.setContentsMargins(16, 16, 16, 14)
        self._sync_source_selector_state()

    def set_collection_providers(self, local_state_provider, playlist_provider) -> None:
        self.local_state_provider = local_state_provider or (lambda _track: {})
        self.playlist_provider = playlist_provider or (lambda: [])
        self.local_view.set_like_state_provider(self.local_state_provider)

    def _toggle_local_like(self, value: dict) -> None:
        try:
            liked = bool((self.local_state_provider(value) or {}).get("liked"))
        except Exception:
            liked = False
        signal = self.localUnlikeRequested if liked else self.localLikeRequested
        signal.emit(dict(value))

    def refresh_like_identity(self, identity: str) -> int:
        return (
            self.local_view.refresh_like_identity(identity)
            + self.online_results.refresh_like_identity(identity)
        )

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

    def set_local_results(self, keyword: str, results: list[dict]) -> bool:
        self.set_keyword(keyword)
        normalized_results = [
            MediaItem.from_mapping(value).to_dict()
            for value in results
        ]
        results_changed = normalized_results != self._local_results
        self._local_results = normalized_results
        if not self._keyword:
            empty_text = "输入关键词后显示本地搜索结果"
        else:
            empty_text = "本地音乐库没有找到匹配歌曲"
        if results_changed:
            self.local_view.set_items(
                self._local_results,
                empty_text=empty_text,
                preserve_scroll=True,
            )
        else:
            # Playing and collection state come from live providers, so a
            # repaint is enough when the ordered result data is unchanged.
            self.local_view.update_empty_state(empty_text)
            self.local_view.list_widget.viewport().update()
        self.local_tab.setText(f"本地结果 · {len(self._local_results)}")
        if self.current_tab() == "local":
            self.local_status_label.setText(
                f"本地搜索完成，找到 {len(self._local_results)} 首歌曲"
                if self._keyword
                else "输入歌名、歌手或专辑"
            )
        return results_changed

    def set_online_results(self, keyword: str, results: list[dict], summary: dict) -> None:
        self.set_keyword(keyword)
        self.online_results.set_results(keyword, results, summary)
        count = len(results)
        self.online_tab.setText(f"在线结果 · {count}")

    def begin_online_results(self, keyword: str, summary: dict) -> None:
        self.set_keyword(keyword)
        self.online_results.begin_results(keyword, summary)
        self._update_online_tab_count(summary)

    def update_online_summary(self, keyword: str, summary: dict) -> None:
        self.set_keyword(keyword)
        self.online_results.update_summary(keyword, summary)
        self._update_online_tab_count(summary)

    def update_online_source_results(
        self,
        keyword: str,
        source_id: str,
        source_name: str,
        results: list[dict],
        state: dict,
        summary: dict,
    ) -> bool:
        self.set_keyword(keyword)
        self.online_results.update_summary(keyword, summary)
        changed = self.online_results.update_source_group(
            source_id,
            source_name,
            results,
            state,
        )
        self._update_online_tab_count(summary)
        return changed

    def _update_online_tab_count(self, summary: dict) -> None:
        try:
            count = max(0, int((summary or {}).get("resultCount") or 0))
        except (TypeError, ValueError):
            count = 0
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
        self._sync_source_selector_state()
        if online and self._source_service is not None:
            self._source_service.ensure_source_catalog()
        if not online:
            self.local_status_label.setText(
                f"本地搜索完成，找到 {len(self._local_results)} 首歌曲"
                if self._keyword
                else "输入歌名、歌手或专辑"
            )
        target_list = (
            self.online_results.result_list
            if online
            else self.local_view.list_widget
        )
        target_list.scrollToTop()
        QTimer.singleShot(0, target_list.scrollToTop)

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
