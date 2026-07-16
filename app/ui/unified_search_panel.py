from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
)

from app.models.media_item import MediaItem


class UnifiedSearchResultsPanel(QFrame):
    GROUP_SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    GROUP_STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 2

    browseRequested = Signal(dict)
    playRequested = Signal(dict)
    queueNextRequested = Signal(dict)
    downloadRequested = Signal(dict)
    likeRequested = Signal(dict)
    unlikeRequested = Signal(dict)
    addToPlaylistRequested = Signal(dict, str)
    removeFromCurrentPlaylistRequested = Signal(dict)
    infoRequested = Signal(dict)
    deleteCacheRequested = Signal(dict)

    def __init__(self, parent=None, standalone: bool = False) -> None:
        super().__init__(parent)
        self.standalone = bool(standalone)
        self._keyword = ""
        self._results: list[dict] = []
        self._summary: dict = {}
        self._collapsed_source_ids: set[str] = set()
        self._source_results: dict[str, list[dict]] = {}
        self._source_states_by_id: dict[str, dict] = {}
        self._source_names: dict[str, str] = {}
        self._source_order: list[str] = []
        self._group_headers: dict[str, QListWidgetItem] = {}
        self.collection_state_provider = lambda _track: {}
        self.cache_state_provider = lambda _track: {}
        self.playlist_provider = lambda: []
        self.playing_key_provider = lambda: ""
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("unifiedSearchPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("在线结果")
        title.setObjectName("settingsCardTitle")
        self.status_label = QLabel("")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status_label, 1)
        self.result_list = QListWidget()
        self.result_list.setObjectName("unifiedSearchResultList")
        self.result_list.setUniformItemSizes(False)
        self.result_list.setSpacing(2)
        self.result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_list.customContextMenuRequested.connect(self.show_context_menu)
        self.result_list.itemClicked.connect(self._handle_item_clicked)
        self.result_list.itemDoubleClicked.connect(self.request_playback)
        self.result_list.setMinimumHeight(160)
        if not self.standalone:
            self.result_list.setMaximumHeight(285)
        self.detail_label = QLabel("单击在线歌曲可查看详情；双击才会解析播放地址。")
        self.detail_label.setObjectName("pageSubtitle")
        self.detail_label.setWordWrap(True)
        layout.addLayout(header)
        layout.addWidget(self.result_list)
        layout.addWidget(self.detail_label)
        self.setStyleSheet(
            "QFrame#unifiedSearchPanel { background: transparent; border-top: 1px solid rgba(255,255,255,0.07); }"
            "QListWidget#unifiedSearchResultList { background: #11151d; color: #e8ecf5; border: 1px solid #2a303b; border-radius: 14px; padding: 6px; outline: none; }"
            "QListWidget#unifiedSearchResultList::item { padding: 7px 10px; border-radius: 9px; margin: 1px 0; }"
            "QListWidget#unifiedSearchResultList::item:hover { background: rgba(255,255,255,0.06); }"
            "QListWidget#unifiedSearchResultList::item:selected { background: rgba(59,130,246,0.20); border: 1px solid rgba(96,165,250,0.42); }"
        )
        self.setVisible(self.standalone)

    def set_collection_providers(self, state_provider, playlist_provider) -> None:
        self.collection_state_provider = state_provider or (lambda _track: {})
        self.playlist_provider = playlist_provider or (lambda: [])

    def set_cache_state_provider(self, provider) -> None:
        self.cache_state_provider = provider or (lambda _track: {})

    def set_playing_key_provider(self, provider) -> None:
        self.playing_key_provider = provider or (lambda: "")
        self.refresh_playing_indicator()

    def refresh_playing_indicator(self) -> None:
        playing_key = str(self.playing_key_provider() or "")
        for row in range(self.result_list.count()):
            item = self.result_list.item(row)
            track = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if not isinstance(track, dict):
                continue
            try:
                is_playing = (
                    MediaItem.from_mapping(track).stable_identity == playing_key
                )
            except (TypeError, ValueError):
                is_playing = False
            font = self.result_list.font()
            font.setBold(is_playing)
            item.setFont(font)
            item.setData(
                Qt.ItemDataRole.ForegroundRole,
                QColor("#8fbcff") if is_playing else None,
            )

    def scroll_to_top(self) -> None:
        self.result_list.scrollToTop()
        QTimer.singleShot(0, self.result_list.scrollToTop)

    def set_status(self, message: str) -> None:
        self.status_label.setText(str(message or ""))

    def clear_results(self, hide: bool = True) -> None:
        self._keyword = ""
        self._results = []
        self._summary = {}
        self._source_results = {}
        self._source_states_by_id = {}
        self._source_names = {}
        self._source_order = []
        self._group_headers = {}
        self.result_list.clear()
        self.status_label.clear()
        self.detail_label.setText("单击在线歌曲可查看详情；双击才会解析播放地址。")
        if hide and not self.standalone:
            self.setVisible(False)

    def set_results(
        self,
        keyword: str,
        results: list[dict],
        summary: dict | None = None,
    ) -> None:
        next_keyword = str(keyword or "")
        keyword_changed = next_keyword != self._keyword
        normalized_results = [
            MediaItem.from_mapping(item).to_dict()
            for item in results
            if isinstance(item, dict)
        ]
        next_summary = dict(summary or {})
        if keyword_changed:
            self.begin_results(next_keyword, next_summary)
        else:
            self.update_summary(next_keyword, next_summary)
        grouped: OrderedDict[str, list[dict]] = OrderedDict()
        source_names: dict[str, str] = {}
        for result in normalized_results:
            source_id = str(result.get("source_id") or "")
            source_names[source_id] = str(
                result.get("source_name") or source_id or "未知来源"
            )
            grouped.setdefault(source_id, []).append(result)
        known_ids = set(self._source_results)
        for source_id, tracks in grouped.items():
            state = self._source_states_by_id.get(
                source_id,
                {
                    "sourceId": source_id,
                    "sourceName": source_names[source_id],
                    "status": "success" if tracks else "empty",
                    "resultCount": len(tracks),
                    "message": "",
                },
            )
            self.update_source_group(
                source_id,
                source_names[source_id],
                tracks,
                state,
            )
        for source_id in known_ids - set(grouped):
            state = self._source_states_by_id.get(source_id, {})
            self.update_source_group(
                source_id,
                self._source_names.get(source_id, source_id),
                [],
                state,
            )
        self._results = normalized_results
        self._update_detail_text()

    def begin_results(self, keyword: str, summary: dict | None = None) -> None:
        self._keyword = str(keyword or "")
        self._results = []
        self._summary = dict(summary or {})
        self._source_results = {}
        self._source_states_by_id = {}
        self._source_names = {}
        self._source_order = []
        self._group_headers = {}
        self.result_list.clear()
        self.setVisible(bool(self._keyword))
        self._sync_source_groups_from_summary()
        self._update_detail_text()
        if self._keyword:
            self.scroll_to_top()

    def update_summary(self, keyword: str, summary: dict | None = None) -> None:
        next_keyword = str(keyword or "")
        if next_keyword != self._keyword:
            self.begin_results(next_keyword, summary)
            return
        self._summary = dict(summary or {})
        self._sync_source_groups_from_summary()
        self._update_detail_text()

    def update_source_group(
        self,
        source_id: str,
        source_name: str,
        results: list[dict],
        state: dict | None = None,
    ) -> bool:
        source_id = str(source_id or "").strip()
        if not source_id:
            return False
        normalized_results = [
            MediaItem.from_mapping(item).to_dict()
            for item in results
            if isinstance(item, dict)
        ]
        source_name = str(source_name or source_id or "未知来源")
        next_state = dict(state or {})
        next_state.setdefault("sourceId", source_id)
        next_state.setdefault("sourceName", source_name)
        next_state.setdefault(
            "status",
            "success" if normalized_results else "empty",
        )
        next_state["resultCount"] = len(normalized_results)
        self._source_names[source_id] = source_name
        self._source_states_by_id[source_id] = next_state
        if source_id not in self._source_order:
            self._source_order.append(source_id)
        header = self._ensure_source_group(source_id)
        results_changed = normalized_results != self._source_results.get(source_id, [])
        self._source_results[source_id] = normalized_results
        self._update_group_header(source_id)
        if not results_changed:
            self._update_detail_text()
            return False

        previous_key = self._track_key(self.current_track())
        scroll_bar = self.result_list.verticalScrollBar()
        scroll_value = scroll_bar.value()
        previous_signal_state = self.result_list.blockSignals(True)
        self.result_list.setUpdatesEnabled(False)
        selected_item = None
        try:
            self._remove_source_track_rows(source_id)
            if source_id not in self._collapsed_source_ids:
                insert_row = self.result_list.row(header) + 1
                for track in normalized_results:
                    item = self._create_track_item(track)
                    self.result_list.insertItem(insert_row, item)
                    insert_row += 1
                    if previous_key and self._track_key(track) == previous_key:
                        selected_item = item
        finally:
            self.result_list.blockSignals(previous_signal_state)
            self.result_list.setUpdatesEnabled(True)
        if selected_item is not None:
            self.result_list.setCurrentItem(selected_item)
        scroll_bar.setValue(scroll_value)
        self._update_detail_text()
        return True

    def clear_source_group(self, source_id: str) -> bool:
        source_id = str(source_id or "").strip()
        if source_id not in self._group_headers:
            return False
        self._remove_source_group(source_id)
        self._source_results.pop(source_id, None)
        self._source_states_by_id.pop(source_id, None)
        self._source_names.pop(source_id, None)
        self._source_order = [item for item in self._source_order if item != source_id]
        self._update_detail_text()
        return True

    def _sync_source_groups_from_summary(self) -> None:
        states = self._source_states()
        if "sources" in self._summary:
            next_order = [
                str(state.get("sourceId") or state.get("source_id") or "")
                for state in states
                if str(state.get("sourceId") or state.get("source_id") or "")
            ]
            for source_id in set(self._group_headers) - set(next_order):
                self.clear_source_group(source_id)
            self._source_order = next_order
        for state in states:
            source_id = str(state.get("sourceId") or state.get("source_id") or "")
            if not source_id:
                continue
            source_name = str(
                state.get("sourceName")
                or state.get("source_name")
                or source_id
                or "未知来源"
            )
            self._source_names[source_id] = source_name
            self._source_states_by_id[source_id] = dict(state)
            self._ensure_source_group(source_id)
            self._update_group_header(source_id)

    def _ensure_source_group(self, source_id: str) -> QListWidgetItem:
        existing = self._group_headers.get(source_id)
        if existing is not None:
            return existing
        group_item = QListWidgetItem()
        group_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        group_item.setData(Qt.ItemDataRole.UserRole, None)
        group_item.setData(self.GROUP_SOURCE_ROLE, source_id)
        group_font = group_item.font()
        group_font.setBold(True)
        group_item.setFont(group_font)
        group_item.setForeground(QColor("#a9c8ff"))
        group_item.setBackground(QColor("#171e2a"))
        group_item.setSizeHint(QSize(0, 38))
        insert_row = self.result_list.count()
        if source_id in self._source_order:
            source_index = self._source_order.index(source_id)
            for following_id in self._source_order[source_index + 1:]:
                following = self._group_headers.get(following_id)
                if following is not None:
                    insert_row = self.result_list.row(following)
                    break
        self.result_list.insertItem(insert_row, group_item)
        self._group_headers[source_id] = group_item
        self._update_group_header(source_id)
        return group_item

    def _update_group_header(self, source_id: str) -> None:
        item = self._group_headers.get(source_id)
        if item is None:
            return
        state = self._source_states_by_id.get(source_id, {})
        source_name = self._source_names.get(source_id, source_id or "未知来源")
        tracks = self._source_results.get(source_id, [])
        collapsed = source_id in self._collapsed_source_ids
        arrow = "▶" if collapsed else "▼"
        item.setText(
            f"{arrow}  {source_name} · {self._source_status_text(state, len(tracks))}"
        )
        item.setData(self.GROUP_STATUS_ROLE, str(state.get("status") or ""))
        item.setToolTip(self._source_status_tooltip(source_name, state))

    def _remove_source_track_rows(self, source_id: str) -> None:
        header = self._group_headers.get(source_id)
        if header is None:
            return
        row = self.result_list.row(header) + 1
        while row < self.result_list.count():
            item = self.result_list.item(row)
            if str(item.data(self.GROUP_SOURCE_ROLE) or ""):
                break
            self.result_list.takeItem(row)

    def _remove_source_group(self, source_id: str) -> None:
        header = self._group_headers.get(source_id)
        if header is None:
            return
        self._remove_source_track_rows(source_id)
        row = self.result_list.row(header)
        if row >= 0:
            self.result_list.takeItem(row)
        self._group_headers.pop(source_id, None)

    def _create_track_item(self, track: dict) -> QListWidgetItem:
        item = QListWidgetItem(self._result_text(track))
        item.setData(Qt.ItemDataRole.UserRole, track)
        item.setToolTip(self._result_tooltip(track))
        item.setSizeHint(QSize(0, 54))
        self._apply_playing_indicator(item, track)
        return item

    def _apply_playing_indicator(self, item: QListWidgetItem, track: dict) -> None:
        playing_key = str(self.playing_key_provider() or "")
        try:
            is_playing = MediaItem.from_mapping(track).stable_identity == playing_key
        except (TypeError, ValueError):
            is_playing = False
        font = self.result_list.font()
        font.setBold(is_playing)
        item.setFont(font)
        item.setData(
            Qt.ItemDataRole.ForegroundRole,
            QColor("#8fbcff") if is_playing else None,
        )

    def _update_detail_text(self) -> None:
        has_results = bool(any(self._source_results.values()))
        try:
            has_results = has_results or int(self._summary.get("resultCount") or 0) > 0
        except (TypeError, ValueError):
            pass
        errors = self._summary.get("errors")
        if isinstance(errors, dict) and errors:
            messages = [str(message) for message in list(errors.values())[:3]]
            self.detail_label.setText("部分来源搜索失败：" + "；".join(messages))
        elif (
            not has_results
            and self._summary.get("final")
            and "selectedSourceIds" in self._summary
            and not self._summary.get("selectedSourceIds")
        ):
            self.detail_label.setText("请至少选择一个搜索来源。")
        elif not has_results and self._summary.get("final"):
            self.detail_label.setText("所选在线来源没有返回匹配结果；本地搜索结果不受影响。")
        elif self._summary.get("pendingCount"):
            self.detail_label.setText("已完成的来源会立即显示；其余来源继续搜索中。")
        else:
            self.detail_label.setText("单击在线歌曲可查看详情；双击才会解析播放地址。")

    def _render_results(self, *, scroll_to_top: bool) -> None:
        previous_key = self._track_key(self.current_track())
        self.result_list.blockSignals(True)
        self.result_list.setUpdatesEnabled(False)
        self.result_list.clear()
        groups: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
        for result in self._results:
            source_id = str(result.get("source_id") or "")
            source_name = str(result.get("source_name") or source_id or "未知来源")
            groups.setdefault((source_id, source_name), []).append(result)
        source_states = self._source_states()
        ordered_groups: list[tuple[str, str, list[dict], dict]] = []
        included_ids: set[str] = set()
        for state in source_states:
            source_id = str(state.get("sourceId") or state.get("source_id") or "")
            source_name = str(
                state.get("sourceName")
                or state.get("source_name")
                or source_id
                or "未知来源"
            )
            tracks = groups.get((source_id, source_name))
            if tracks is None:
                tracks = next(
                    (
                        values
                        for (group_id, _group_name), values in groups.items()
                        if group_id == source_id
                    ),
                    [],
                )
            ordered_groups.append((source_id, source_name, list(tracks), state))
            included_ids.add(source_id)
        for (source_id, source_name), tracks in groups.items():
            if source_id in included_ids:
                continue
            fallback_state = {
                "sourceId": source_id,
                "sourceName": source_name,
                "status": "success" if tracks else "empty",
                "resultCount": len(tracks),
                "message": "",
            }
            ordered_groups.append((source_id, source_name, tracks, fallback_state))
        selected_item = None
        for source_id, source_name, tracks, state in ordered_groups:
            collapsed = source_id in self._collapsed_source_ids
            arrow = "▶" if collapsed else "▼"
            group_item = QListWidgetItem(
                f"{arrow}  {source_name} · {self._source_status_text(state, len(tracks))}"
            )
            group_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            group_item.setData(Qt.ItemDataRole.UserRole, None)
            group_item.setData(self.GROUP_SOURCE_ROLE, source_id)
            group_item.setData(self.GROUP_STATUS_ROLE, str(state.get("status") or ""))
            group_item.setToolTip(self._source_status_tooltip(source_name, state))
            group_font = group_item.font()
            group_font.setBold(True)
            group_item.setFont(group_font)
            group_item.setForeground(QColor("#a9c8ff"))
            group_item.setBackground(QColor("#171e2a"))
            group_item.setSizeHint(QSize(0, 38))
            self.result_list.addItem(group_item)
            if collapsed:
                continue
            for track in tracks:
                item = QListWidgetItem(self._result_text(track))
                item.setData(Qt.ItemDataRole.UserRole, track)
                item.setToolTip(self._result_tooltip(track))
                item.setSizeHint(QSize(0, 54))
                self.result_list.addItem(item)
                if previous_key and self._track_key(track) == previous_key:
                    selected_item = item
        self.result_list.blockSignals(False)
        self.result_list.setUpdatesEnabled(True)
        self.refresh_playing_indicator()
        if selected_item is not None:
            self.result_list.setCurrentItem(selected_item)
        if scroll_to_top:
            self.scroll_to_top()

    def _source_states(self) -> list[dict]:
        states = self._summary.get("sources")
        if not isinstance(states, list):
            return []
        return [dict(state) for state in states if isinstance(state, dict)]

    @staticmethod
    def _source_status_text(state: dict, actual_count: int) -> str:
        status = str(state.get("status") or "")
        try:
            result_count = max(0, int(state.get("resultCount", actual_count) or 0))
        except (TypeError, ValueError):
            result_count = max(0, int(actual_count))
        if status == "searching":
            return "搜索中…"
        if status == "empty":
            return "无结果"
        if status == "failed":
            return "搜索失败"
        if status == "timeout":
            return "搜索超时"
        if status == "unavailable":
            return "来源不可用"
        if status == "success":
            return f"搜索成功 · {result_count} 条结果"
        return f"{result_count} 条结果"

    @staticmethod
    def _source_status_tooltip(source_name: str, state: dict) -> str:
        try:
            result_count = int(state.get("resultCount") or 0)
        except (TypeError, ValueError):
            result_count = 0
        status_text = UnifiedSearchResultsPanel._source_status_text(
            state,
            result_count,
        )
        message = str(state.get("message") or "").strip()
        return (
            f"来源：{source_name}\n状态：{status_text}"
            + (f"\n原因：{message}" if message else "")
        )

    def _handle_item_clicked(self, item: QListWidgetItem) -> None:
        source_id = str(item.data(self.GROUP_SOURCE_ROLE) or "")
        if source_id:
            self.toggle_source_group(source_id)
            return
        self.browse_result(item)

    def toggle_source_group(self, source_id: str) -> None:
        target = str(source_id or "").strip()
        if not target:
            return
        if target in self._collapsed_source_ids:
            self._collapsed_source_ids.remove(target)
        else:
            self._collapsed_source_ids.add(target)
        scroll_bar = self.result_list.verticalScrollBar()
        scroll_value = scroll_bar.value()
        previous_signal_state = self.result_list.blockSignals(True)
        self.result_list.setUpdatesEnabled(False)
        try:
            self._remove_source_track_rows(target)
            if target not in self._collapsed_source_ids:
                header = self._group_headers.get(target)
                if header is not None:
                    insert_row = self.result_list.row(header) + 1
                    for track in self._source_results.get(target, []):
                        self.result_list.insertItem(
                            insert_row,
                            self._create_track_item(track),
                        )
                        insert_row += 1
            self._update_group_header(target)
        finally:
            self.result_list.blockSignals(previous_signal_state)
            self.result_list.setUpdatesEnabled(True)
        scroll_bar.setValue(scroll_value)

    def is_source_collapsed(self, source_id: str) -> bool:
        return str(source_id or "").strip() in self._collapsed_source_ids

    def current_track(self) -> dict | None:
        item = self.result_list.currentItem()
        track = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return track if isinstance(track, dict) else None

    def browse_result(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, dict):
            return
        status = self._local_status(track)
        self.detail_label.setText(
            f"{track.get('title') or '未知歌曲'} · {track.get('artist') or '未知艺术家'} · "
            f"{track.get('album') or '未知专辑'}\n"
            f"来源：{track.get('source_name') or track.get('source_id') or '未知来源'} · "
            f"播放：{'可用' if track.get('can_play') else '不可用'} · "
            f"下载：{'可用' if track.get('can_download') else '不可用'} · {status}"
        )
        self.browseRequested.emit(dict(track))

    def request_playback(self, item: QListWidgetItem) -> None:
        track = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, dict):
            return
        try:
            cache_state = self.cache_state_provider(track) or {}
        except Exception:
            cache_state = {}
        cache_available = bool(cache_state.get("complete"))
        if track.get("availability") != "available" and not cache_available:
            self.set_status("该在线来源当前不可用。")
            return
        if (
            not track.get("can_play")
            and not track.get("local_file_path")
            and not cache_available
        ):
            self.set_status("该来源没有可用的播放能力。")
            return
        self.playRequested.emit(dict(track))

    def show_context_menu(self, position) -> None:
        item = self.result_list.itemAt(position)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, dict):
            return
        self.result_list.setCurrentItem(item)
        available = track.get("availability") == "available"
        try:
            state = self.collection_state_provider(track) or {}
        except Exception:
            state = {}
        try:
            cache_state = self.cache_state_provider(track) or {}
        except Exception:
            cache_state = {}
        cache_available = bool(cache_state.get("complete"))
        menu = QMenu(self)
        play_action = menu.addAction("播放")
        play_action.setEnabled(
            bool(track.get("local_file_path"))
            or cache_available
            or (available and bool(track.get("can_play")))
        )
        play_action.triggered.connect(
            lambda checked=False, current_item=item: self.request_playback(current_item)
        )
        queue_action = menu.addAction("下一首播放")
        queue_action.setEnabled(play_action.isEnabled())
        queue_action.triggered.connect(
            lambda checked=False, current_track=dict(track): self.queueNextRequested.emit(current_track)
        )
        download_action = menu.addAction("下载")
        download_action.setVisible(bool(track.get("can_download")))
        download_action.setEnabled(available and bool(track.get("can_download")))
        download_action.triggered.connect(
            lambda checked=False, current_track=dict(track): self.downloadRequested.emit(current_track)
        )
        if cache_state.get("complete"):
            delete_cache_action = menu.addAction("删除此歌曲缓存")
            delete_cache_action.triggered.connect(
                lambda checked=False, current_track=dict(track):
                self.deleteCacheRequested.emit(current_track)
            )
        menu.addSeparator()
        if state.get("liked"):
            like_action = menu.addAction("取消收藏")
            like_action.triggered.connect(
                lambda checked=False, current_track=dict(track): self.unlikeRequested.emit(current_track)
            )
        else:
            like_action = menu.addAction("收藏到“我喜欢”")
            like_action.triggered.connect(
                lambda checked=False, current_track=dict(track): self.likeRequested.emit(current_track)
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
                lambda checked=False, current_track=dict(track), target_id=str(playlist_id):
                self.addToPlaylistRequested.emit(current_track, target_id)
            )
        if state.get("inCurrentPlaylist"):
            remove_action = menu.addAction("从当前歌单移除")
            remove_action.triggered.connect(
                lambda checked=False, current_track=dict(track):
                self.removeFromCurrentPlaylistRequested.emit(current_track)
            )
        menu.addSeparator()
        info_action = menu.addAction("查看歌曲信息")
        info_action.triggered.connect(
            lambda checked=False, current_track=dict(track): self.infoRequested.emit(current_track)
        )
        menu.exec(self.result_list.mapToGlobal(position))

    @classmethod
    def _result_text(cls, track: dict) -> str:
        title = str(track.get("title") or "未知歌曲")
        artist = str(track.get("artist") or "未知艺术家")
        album = str(track.get("album") or "未知专辑")
        duration = cls._format_duration(track.get("duration"))
        flags = [cls._local_status(track)]
        flags.append("可播放" if track.get("can_play") else "不可播放")
        flags.append("可下载" if track.get("can_download") else "不可下载")
        return f"{title}\n{artist} · {album} · {duration}   {' · '.join(flags)}"

    @classmethod
    def _result_tooltip(cls, track: dict) -> str:
        return (
            f"歌曲：{track.get('title') or '未知歌曲'}\n"
            f"歌手：{track.get('artist') or '未知艺术家'}\n"
            f"专辑：{track.get('album') or '未知专辑'}\n"
            f"来源：{track.get('source_name') or track.get('source_id') or '未知来源'}\n"
            f"状态：{cls._local_status(track)}"
        )

    @staticmethod
    def _local_status(track: dict) -> str:
        if track.get("availability") != "available":
            return "来源不可用"
        if track.get("local_file_path"):
            return "已下载"
        extra = track.get("extra") if isinstance(track.get("extra"), dict) else {}
        if extra.get("local_existing"):
            return "本地已有"
        return "在线"

    @staticmethod
    def _track_key(track: dict | None) -> tuple:
        if not isinstance(track, dict):
            return ()
        return (
            str(track.get("source_id") or ""),
            str(track.get("track_id") or ""),
        )

    @staticmethod
    def _format_duration(value) -> str:
        try:
            seconds = max(0, int(float(value or 0)))
        except (TypeError, ValueError):
            seconds = 0
        return f"{seconds // 60}:{seconds % 60:02d}" if seconds else "--:--"
