from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.models.media_item import MediaItem
from app.ui.track_list_view import TrackListView


class LibraryViewSwitcher(QFrame):
    viewChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("libraryViewSwitcher")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in (("tracks", "歌曲"), ("artists", "歌手"), ("albums", "专辑")):
            button = QPushButton(text)
            button.setObjectName("libraryViewSwitchButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, current=key: self.viewChanged.emit(current)
            )
            self.buttons[key] = button
            layout.addWidget(button)
        self.set_current("tracks")

    def set_current(self, view_name: str) -> None:
        for key, button in self.buttons.items():
            button.setProperty("active", key == view_name)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()


class GroupedLibraryView(QFrame):
    trackBrowsed = Signal(dict)
    trackPlayRequested = Signal(dict)
    trackContextRequested = Signal(dict, object)

    CHUNK_SIZE = 250

    def __init__(self, group_type: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if group_type not in {"artist", "album"}:
            raise ValueError("group_type 必须为 artist 或 album")
        self.group_type = group_type
        self._cache: dict[str, list[dict]] = {}
        self._cache_key = ""
        self._tracks: list[dict] = []
        self._generation = 0
        self._active_group_key = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.stack = QStackedWidget()
        self.grid_page = QFrame()
        grid_layout = QVBoxLayout(self.grid_page)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(8)
        self.status_label = QLabel("首次打开时加载分组…")
        self.status_label.setObjectName("pageSubtitle")
        self.group_list = QListWidget()
        self.group_list.setObjectName("libraryGroupList")
        self.group_list.setSpacing(4)
        self.group_list.setIconSize(QSize(48, 48))
        self.group_list.itemClicked.connect(self.open_group)
        grid_layout.addWidget(self.status_label)
        grid_layout.addWidget(self.group_list, 1)

        self.detail_page = QFrame()
        detail_layout = QVBoxLayout(self.detail_page)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)
        breadcrumb = QHBoxLayout()
        self.back_button = QPushButton("‹ 返回")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.show_groups)
        self.detail_title = QLabel("")
        self.detail_title.setObjectName("settingsCardTitle")
        breadcrumb.addWidget(self.back_button)
        breadcrumb.addWidget(self.detail_title)
        breadcrumb.addStretch()
        self.detail_tracks = TrackListView(
            object_name="libraryGroupDetailTracks",
            empty_text="这个分组没有歌曲",
            parent=self.detail_page,
        )
        self.detail_tracks.use_canonical_delegate()
        self.detail_tracks.sortRequested.connect(self._sort_detail_tracks)
        self.detail_tracks.list_widget.itemClicked.connect(self._browse_detail)
        self.detail_tracks.list_widget.itemDoubleClicked.connect(self._play_detail)
        self.detail_tracks.list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.detail_tracks.list_widget.customContextMenuRequested.connect(
            self._show_detail_context
        )
        detail_layout.addLayout(breadcrumb)
        detail_layout.addWidget(self.detail_tracks, 1)

        self.stack.addWidget(self.grid_page)
        self.stack.addWidget(self.detail_page)
        layout.addWidget(self.stack)
        self.setStyleSheet(
            "QListWidget#libraryGroupList { background: transparent; color: #e8ecf5; border: none; outline: none; }"
            "QListWidget#libraryGroupList::item { background: #151922; border: 1px solid #2a303b; border-radius: 14px; padding: 10px 12px; margin: 2px; }"
            "QListWidget#libraryGroupList::item:hover { background: #202631; border-color: #3a4352; }"
            "QListWidget#libraryGroupList::item:selected { background: rgba(76,141,255,0.18); border-color: rgba(76,141,255,0.55); }"
        )

    @classmethod
    def build_groups(cls, tracks: list[dict], group_type: str) -> list[dict]:
        groups: OrderedDict[str, dict] = OrderedDict()
        for value in tracks:
            item = MediaItem.from_mapping(value)
            if group_type == "artist":
                label = item.artist or "未知艺术家"
                key = label.casefold()
                subtitle = ""
            else:
                label = item.album or "未知专辑"
                subtitle = item.artist or "未知艺术家"
                key = f"{label.casefold()}\0{subtitle.casefold()}"
            group = groups.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "subtitle": subtitle,
                    "tracks": [],
                    "cover_path": item.local_cover_path,
                },
            )
            group["tracks"].append(item.to_dict())
            if not group.get("cover_path") and item.local_cover_path:
                group["cover_path"] = item.local_cover_path
        return sorted(
            groups.values(),
            key=lambda group: (
                str(group.get("label") or "").startswith("未知"),
                str(group.get("label") or "").casefold(),
                str(group.get("subtitle") or "").casefold(),
            ),
        )

    def set_tracks(self, tracks: list[dict], cache_key: str) -> None:
        normalized_key = str(cache_key or "")
        if normalized_key == self._cache_key and normalized_key in self._cache:
            return
        self._tracks = [MediaItem.from_mapping(item).to_dict() for item in tracks]
        self._cache_key = normalized_key
        self._generation += 1
        generation = self._generation
        cached = self._cache.get(self._cache_key)
        if cached is not None:
            self._render_groups(cached)
            return
        self.status_label.setText("正在整理歌手…" if self.group_type == "artist" else "正在整理专辑…")
        self.group_list.clear()
        # Chunking yields back to Qt between batches and avoids a long UI stall.
        groups: OrderedDict[str, dict] = OrderedDict()

        def consume(start: int = 0) -> None:
            if generation != self._generation:
                return
            end = min(len(self._tracks), start + self.CHUNK_SIZE)
            partial = self.build_groups(self._tracks[start:end], self.group_type)
            for incoming in partial:
                key = str(incoming["key"])
                existing = groups.get(key)
                if existing is None:
                    groups[key] = incoming
                else:
                    existing["tracks"].extend(incoming["tracks"])
                    if not existing.get("cover_path"):
                        existing["cover_path"] = incoming.get("cover_path", "")
            if end < len(self._tracks):
                QTimer.singleShot(0, lambda: consume(end))
                return
            ordered = sorted(
                groups.values(),
                key=lambda group: (
                    str(group.get("label") or "").startswith("未知"),
                    str(group.get("label") or "").casefold(),
                    str(group.get("subtitle") or "").casefold(),
                ),
            )
            self._cache[self._cache_key] = ordered
            self._render_groups(ordered)

        QTimer.singleShot(0, consume)

    def set_playing_key_provider(self, provider) -> None:
        self.detail_tracks.use_canonical_delegate(provider)

    def refresh_playing_indicator(self) -> None:
        self.detail_tracks.list_widget.viewport().update()

    def invalidate_cache(self) -> None:
        self._generation += 1
        self._cache.clear()
        self._cache_key = ""

    def _render_groups(self, groups: list[dict]) -> None:
        self.group_list.clear()
        self.show_groups()
        generation = self._generation

        def render(start: int = 0) -> None:
            if generation != self._generation:
                return
            self.group_list.setUpdatesEnabled(False)
            end = min(len(groups), start + 100)
            for group in groups[start:end]:
                count = len(group.get("tracks") or [])
                subtitle = str(group.get("subtitle") or "")
                second_line = f"{subtitle} · {count} 首歌曲" if subtitle else f"{count} 首歌曲"
                item = QListWidgetItem(f"{group.get('label') or '未知'}\n{second_line}")
                item.setData(Qt.ItemDataRole.UserRole, str(group.get("key") or ""))
                item.setSizeHint(QSize(0, 72))
                item.setIcon(self._group_icon(group))
                self.group_list.addItem(item)
            self.group_list.setUpdatesEnabled(True)
            if end < len(groups):
                self.status_label.setText(f"正在显示分组… {end}/{len(groups)}")
                QTimer.singleShot(0, lambda: render(end))
                return
            label = "位歌手" if self.group_type == "artist" else "张专辑"
            self.status_label.setText(f"共 {len(groups)} {label} · 点击进入详情")

        QTimer.singleShot(0, render)

    def _group_icon(self, group: dict) -> QIcon:
        path = str(group.get("cover_path") or "")
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            pixmap = QPixmap(48, 48)
            pixmap.fill(QColor("#202631"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#9aa6bb"))
            font = painter.font()
            font.setPointSize(20)
            font.setBold(True)
            painter.setFont(font)
            text = "人" if self.group_type == "artist" else "♪"
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
            painter.end()
        return QIcon(
            pixmap.scaled(
                48,
                48,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def open_group(self, item: QListWidgetItem) -> None:
        key = str(item.data(Qt.ItemDataRole.UserRole) or "")
        groups = self._cache.get(self._cache_key, [])
        group = next((value for value in groups if value.get("key") == key), None)
        if not isinstance(group, dict):
            return
        self._active_group_key = key
        prefix = "音乐库 / 歌手 / " if self.group_type == "artist" else "音乐库 / 专辑 / "
        self.detail_title.setText(prefix + str(group.get("label") or "未知"))
        self.detail_tracks.set_items(list(group.get("tracks") or []))
        self.stack.setCurrentWidget(self.detail_page)

    def show_groups(self) -> None:
        self.stack.setCurrentWidget(self.grid_page)
        self.group_list.scrollToTop()
        QTimer.singleShot(0, self.group_list.scrollToTop)

    def _detail_item(self, item: QListWidgetItem | None) -> dict | None:
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return value if isinstance(value, dict) else None

    def _browse_detail(self, item: QListWidgetItem) -> None:
        value = self._detail_item(item)
        if value is not None:
            self.trackBrowsed.emit(dict(value))

    def _play_detail(self, item: QListWidgetItem) -> None:
        value = self._detail_item(item)
        if value is not None:
            self.trackPlayRequested.emit(dict(value))

    def _show_detail_context(self, position: QPoint) -> None:
        item = self.detail_tracks.list_widget.itemAt(position)
        value = self._detail_item(item)
        if value is not None:
            self.detail_tracks.list_widget.setCurrentItem(item)
            self.trackContextRequested.emit(
                dict(value), self.detail_tracks.list_widget.mapToGlobal(position)
            )

    def _sort_detail_tracks(self, field: str) -> None:
        groups = self._cache.get(self._cache_key, [])
        group = next(
            (value for value in groups if value.get("key") == self._active_group_key),
            None,
        )
        if not isinstance(group, dict):
            return
        tracks = list(group.get("tracks") or [])
        tracks.sort(
            key=lambda value: str(value.get(field) or "").casefold()
        )
        self.detail_tracks.set_items(tracks)


class ArtistGridView(GroupedLibraryView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("artist", parent)


class AlbumGridView(GroupedLibraryView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("album", parent)


class LibraryPage(QFrame):
    importFilesRequested = Signal()
    importFolderRequested = Signal()
    randomPlayRequested = Signal()
    removeSelectedRequested = Signal()
    cleanMissingRequested = Signal()
    trackBrowsed = Signal(dict)
    trackPlayRequested = Signal(dict)
    trackContextRequested = Signal(dict, object)
    viewChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("libraryPanel")
        self.setAcceptDrops(True)
        self.current_mode = "tracks"
        self._scope_tracks: list[dict] = []
        self._scope_cache_key = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.page_layout = layout
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(16)
        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_box = QVBoxLayout()
        self.page_title = QLabel("音乐库")
        self.page_title.setObjectName("pageTitle")
        self.page_title.setWordWrap(True)
        self.page_subtitle = QLabel("浏览本地音乐；歌手和专辑会在首次打开时按需整理。")
        self.page_subtitle.setObjectName("pageSubtitle")
        self.page_subtitle.setWordWrap(True)
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        self.switcher = LibraryViewSwitcher()
        self.switcher.viewChanged.connect(self.show_mode)
        self.random_button = QPushButton("随机播放")
        self.random_button.setObjectName("secondaryButton")
        self.random_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.random_button.clicked.connect(self.randomPlayRequested)
        self.more_button = QPushButton("更多")
        self.more_button.setObjectName("secondaryButton")
        self.more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        more_menu = QMenu(self.more_button)
        random_action = more_menu.addAction("随机播放")
        random_action.triggered.connect(
            lambda checked=False: self.randomPlayRequested.emit()
        )
        folder_action = more_menu.addAction("导入文件夹")
        folder_action.triggered.connect(
            lambda checked=False: self.importFolderRequested.emit()
        )
        more_menu.addSeparator()
        remove_action = more_menu.addAction("从音乐库移除选中歌曲")
        remove_action.triggered.connect(self.removeSelectedRequested)
        clean_action = more_menu.addAction("清理失效歌曲")
        clean_action.triggered.connect(self.cleanMissingRequested)
        self.more_button.setMenu(more_menu)
        self.folder_button = QPushButton("导入文件夹")
        self.folder_button.setObjectName("secondaryButton")
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.clicked.connect(self.importFolderRequested)
        self.import_button = QPushButton("导入音乐")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self.importFilesRequested)

        title_row.addLayout(title_box, 1)
        title_row.addWidget(self.switcher, alignment=Qt.AlignmentFlag.AlignTop)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addStretch()
        action_row.addWidget(self.random_button)
        action_row.addWidget(self.more_button)
        action_row.addWidget(self.folder_button)
        action_row.addWidget(self.import_button)
        header.addLayout(title_row)
        header.addLayout(action_row)

        self.content_stack = QStackedWidget()
        self.track_view = TrackListView(
            object_name="libraryTrackView",
            empty_text="音乐库还是空的\n导入本地音乐后，就可以在这里浏览和播放。",
            selection_mode=QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self.artist_view = ArtistGridView()
        self.album_view = AlbumGridView()
        for view in (self.artist_view, self.album_view):
            view.trackBrowsed.connect(self.trackBrowsed)
            view.trackPlayRequested.connect(self.trackPlayRequested)
            view.trackContextRequested.connect(self.trackContextRequested)
        self.content_stack.addWidget(self.track_view)
        self.content_stack.addWidget(self.artist_view)
        self.content_stack.addWidget(self.album_view)
        layout.addLayout(header)
        layout.addWidget(self.content_stack, 1)
        self.setStyleSheet(
            "QFrame#libraryViewSwitcher { background: #10131a; border: 1px solid #2a303b; border-radius: 12px; }"
            "QPushButton#libraryViewSwitchButton { background: transparent; color: #9ca5b5; border: none; border-radius: 8px; padding: 7px 13px; font-weight: 650; }"
            "QPushButton#libraryViewSwitchButton:hover { background: #202631; color: #eef1f7; }"
            "QPushButton#libraryViewSwitchButton[active='true'] { background: rgba(76,141,255,0.22); color: #ffffff; }"
        )

    def set_responsive_mode(self, mode: str) -> None:
        mode = mode if mode in {"full", "compact", "narrow"} else "full"
        compact = mode != "full"
        self.random_button.setVisible(not compact)
        self.folder_button.setVisible(not compact)
        self.page_subtitle.setVisible(mode != "narrow")
        if mode == "full":
            self.page_layout.setContentsMargins(28, 26, 28, 24)
        elif mode == "compact":
            self.page_layout.setContentsMargins(20, 20, 20, 18)
        else:
            self.page_layout.setContentsMargins(16, 16, 16, 14)

    def set_scope(self, title: str, tracks: list[dict], cache_key: str) -> None:
        self.page_title.setText(str(title or "音乐库"))
        self._scope_tracks = [
            dict(item)
            if isinstance(item, dict)
            and {"track_id", "media_type", "source_id"}.issubset(item)
            else MediaItem.from_mapping(item).to_dict()
            for item in tracks
        ]
        self._scope_cache_key = str(cache_key or "")
        if self.current_mode == "artists":
            self.artist_view.set_tracks(self._scope_tracks, self._scope_cache_key + ":artist")
        elif self.current_mode == "albums":
            self.album_view.set_tracks(self._scope_tracks, self._scope_cache_key + ":album")

    def set_playing_key_provider(self, provider) -> None:
        self.artist_view.set_playing_key_provider(provider)
        self.album_view.set_playing_key_provider(provider)

    def refresh_playing_indicator(self) -> None:
        self.artist_view.refresh_playing_indicator()
        self.album_view.refresh_playing_indicator()

    def show_mode(self, mode: str) -> None:
        if mode not in {"tracks", "artists", "albums"}:
            mode = "tracks"
        self.current_mode = mode
        self.switcher.set_current(mode)
        if mode == "tracks":
            self.content_stack.setCurrentWidget(self.track_view)
        elif mode == "artists":
            self.artist_view.set_tracks(self._scope_tracks, self._scope_cache_key + ":artist")
            self.content_stack.setCurrentWidget(self.artist_view)
        else:
            self.album_view.set_tracks(self._scope_tracks, self._scope_cache_key + ":album")
            self.content_stack.setCurrentWidget(self.album_view)
        self.scroll_current_view_to_top()
        self.viewChanged.emit(mode)

    def scroll_current_view_to_top(self) -> None:
        if self.current_mode == "tracks":
            self.track_view.scroll_to_top()
            return
        grouped_view = (
            self.artist_view
            if self.current_mode == "artists"
            else self.album_view
        )
        if grouped_view.stack.currentWidget() is grouped_view.detail_page:
            grouped_view.detail_tracks.scroll_to_top()
        else:
            grouped_view.group_list.scrollToTop()
            QTimer.singleShot(0, grouped_view.group_list.scrollToTop)

    def invalidate_group_cache(self) -> None:
        self.artist_view.invalidate_cache()
        self.album_view.invalidate_cache()
