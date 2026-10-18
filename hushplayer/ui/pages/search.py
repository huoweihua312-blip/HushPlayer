"""Global search page: local library and online sources."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.logging_setup import get_logger
from ...core.theme import css_rgba, rgba, theme
from ...model.track import Track
from ...online.models import build_sources, tracks_from_items
from ..context import ctx
from ..menus import track_menu
from ..widgets.cards import AlbumCard, ArtistCard, CardGrid
from ..widgets.common import TextButton
from ..widgets.searchfield import SearchField, SegmentedControl
from ..widgets.tracklist import TrackListWidget
from .page import EmptyState, Page

log = get_logger(__name__)


class SearchPage(Page):
    route = "search"
    title = "搜索"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = 0
        self._token = 0
        self._online_tracks: list[Track] = []
        self._pending: set[str] = set()
        self._errors: list[str] = []
        self._local_tracks: list[Track] = []

        root = self.content_layout
        root.setContentsMargins(30, 12, 30, 12)
        root.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(14)
        self.field = SearchField("搜索歌曲、专辑、歌手，或在线音乐")
        self.field.setFixedWidth(420)
        self.field.text_changed.connect(self._on_text)
        self.field.submitted.connect(self._on_submit)
        top.addWidget(self.field)
        self.segments = SegmentedControl(["本地", "在线"])
        self.segments.setFixedWidth(180)
        self.segments.changed.connect(self._on_mode)
        top.addWidget(self.segments)
        top.addStretch(1)
        root.addLayout(top)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_local())
        self.stack.addWidget(self._build_online())

        ctx().library.library_changed.connect(self._maybe_reload_local)
        ctx().library.favorites_changed.connect(self._maybe_reload_local)
        client = ctx().client
        if client is not None:
            client.sources_changed.connect(self._on_sources)
        self._on_sources([])

    # ------------------------------------------------------------------ build
    def _build_local(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        self.local_empty = EmptyState(
            "搜索你的音乐库",
            "输入歌曲、专辑或歌手的名字开始查找",
            icon_name="search",
        )
        layout.addWidget(self.local_empty)

        self.local_scroll = QScrollArea()
        self.local_scroll.setWidgetResizable(True)
        self.local_scroll.setFrameShape(QScrollArea.NoFrame)
        self.local_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.local_scroll.viewport().setAutoFillBackground(False)
        self.local_scroll.setStyleSheet("background:transparent;")
        holder = QWidget()
        holder.setStyleSheet("background:transparent;")
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 4, 12)
        holder_layout.setSpacing(18)

        self._album_title = _MiniTitle("专辑")
        holder_layout.addWidget(self._album_title)
        self.album_grid = CardGrid()
        holder_layout.addWidget(self.album_grid)
        self._artist_title = _MiniTitle("歌手")
        holder_layout.addWidget(self._artist_title)
        self.artist_grid = CardGrid()
        holder_layout.addWidget(self.artist_grid)
        self._track_title = _MiniTitle("歌曲")
        holder_layout.addWidget(self._track_title)
        self.local_list = TrackListWidget()
        self.local_list.play_requested.connect(self._play_local)
        self.local_list.menu_requested.connect(self._menu_local)
        self.local_list.favorite_clicked.connect(self._favorite)
        holder_layout.addWidget(self.local_list)
        holder_layout.addStretch(1)
        self.local_scroll.setWidget(holder)
        layout.addWidget(self.local_scroll, 1)
        return page

    def _build_online(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.source_box = QComboBox()
        self.source_box.setMinimumWidth(160)
        self.source_box.currentIndexChanged.connect(lambda _i: self._run_online(self.field.text()))
        bar.addWidget(self.source_box)
        self.online_status = QLabel("")
        self.online_status.setStyleSheet(
            f"font-size:9pt; color:{css_rgba(theme().palette.text, 0.5)};"
        )
        bar.addWidget(self.online_status, 1)
        self.play_all_button = TextButton("全部播放", icon_name="play", accent=True)
        self.play_all_button.clicked.connect(self._play_all_online)
        self.play_all_button.setEnabled(False)
        bar.addWidget(self.play_all_button)
        layout.addLayout(bar)

        self.online_empty = EmptyState(
            "搜索在线音乐",
            "结果来自已启用的音源，播放时会自动解析真实资源",
            icon_name="globe",
        )
        layout.addWidget(self.online_empty)
        self.online_list = TrackListWidget()
        self.online_list.play_requested.connect(self._play_online)
        self.online_list.menu_requested.connect(self._menu_online)
        self.online_list.favorite_clicked.connect(self._favorite)
        layout.addWidget(self.online_list, 1)
        return page

    # ------------------------------------------------------------------- state
    def on_show(self, payload: object = None) -> None:
        if isinstance(payload, str) and payload:
            self.field.set_text(payload)
            self._on_submit(payload)
        self.field.focus()

    def search(self, text: str) -> None:
        self.field.set_text(text)
        if text:
            self._on_submit(text)

    def _on_mode(self, index: int) -> None:
        self._mode = index
        self.stack.setCurrentIndex(1 if index == 1 else 0)
        if index == 1:
            text = self.field.text().strip()
            if text:
                self._run_online(text)
        else:
            self._run_local(self.field.text())

    def _on_text(self, text: str) -> None:
        if self._mode == 0:
            self._run_local(text)
        else:
            self._run_online(text)

    def _on_submit(self, text: str) -> None:
        if self._mode == 0:
            self._run_local(text, force=True)
        else:
            self._run_online(text, force=True)

    def _maybe_reload_local(self) -> None:
        if self._mode == 0 and self.field.text().strip():
            self._run_local(self.field.text())

    # ------------------------------------------------------------------- local
    def _run_local(self, text: str, *, force: bool = False) -> None:
        text = text.strip()
        library = ctx().library
        if not text:
            self._local_tracks = []
            self.local_list.set_tracks([])
            self.album_grid.set_cards([])
            self.artist_grid.set_cards([])
            self.local_scroll.setVisible(False)
            self.local_empty.setVisible(True)
            self.local_empty.set_text("搜索你的音乐库", "输入歌曲、专辑或歌手的名字开始查找")
            return
        tracks = library.search_local(text, limit=200)
        albums = library.albums(search=text, limit=8)
        artists = library.artists(search=text, limit=8)
        self._local_tracks = tracks
        self.local_list.set_tracks(tracks[:80])
        favorites = {t.id for t in tracks if t.favorite}
        self.local_list.set_favorites(favorites)
        cards = []
        for album in albums:
            card = AlbumCard(album, size=136)
            card.activated.connect(self._open_album)
            cards.append(card)
        self.album_grid.set_cards(cards)
        self.album_grid.setVisible(bool(cards))
        self._album_title.setVisible(bool(cards))
        artist_cards = []
        for artist in artists:
            card = ArtistCard(artist, size=136)
            card.activated.connect(self._open_artist)
            artist_cards.append(card)
        self.artist_grid.set_cards(artist_cards)
        self.artist_grid.setVisible(bool(artist_cards))
        self._artist_title.setVisible(bool(artist_cards))
        self._track_title.setVisible(bool(tracks))
        has_any = bool(tracks or cards or artist_cards)
        self.local_scroll.setVisible(has_any)
        self.local_empty.setVisible(not has_any)
        if not has_any:
            self.local_empty.set_text("没有找到结果", f"音乐库中没有与「{text}」匹配的内容")
        self.local_list.set_empty_text("没有找到歌曲", "")
        current = ctx().player.current_track
        if current is not None:
            self.local_list.set_current(current.id, ctx().player.state == "playing")

    def _play_local(self, tracks: list, index: int) -> None:
        if tracks:
            ctx().player.play_tracks(tracks, index, context=f"搜索 · {self.field.text().strip()}")

    def _menu_local(self, tracks: list, position) -> None:
        if not tracks:
            return
        track_menu(self, tracks, on_play=lambda items: self._play_local(items, 0)).exec(position)

    def _open_album(self, album) -> None:
        if album is not None and ctx().window is not None:
            ctx().window.navigate("album", album.id)

    def _open_artist(self, artist) -> None:
        if artist is not None and ctx().window is not None:
            ctx().window.navigate("artist", artist.id)

    # ------------------------------------------------------------------ online
    def _on_sources(self, _sources=None) -> None:
        client = ctx().client
        raw = client.sources if client is not None else []
        self._sources = [s for s in build_sources(raw) if s.enabled and s.searchable]
        current = self.source_box.currentData() if self.source_box.count() else None
        self.source_box.blockSignals(True)
        self.source_box.clear()
        self.source_box.addItem("全部音源", "")
        for source in self._sources:
            self.source_box.addItem(source.label or source.name, source.id)
        if current:
            index = self.source_box.findData(current)
            if index >= 0:
                self.source_box.setCurrentIndex(index)
        self.source_box.blockSignals(False)
        if not self._sources:
            self.online_status.setText("没有可用的在线音源")
        elif not self.field.text().strip():
            self.online_status.setText(f"{len(self._sources)} 个音源可用")

    def _run_online(self, text: str, *, force: bool = False) -> None:
        text = text.strip()
        if not text:
            self._online_tracks = []
            self.online_list.set_tracks([])
            self.online_list.setVisible(False)
            self.online_empty.setVisible(True)
            self.online_empty.set_text("搜索在线音乐", "结果来自已启用的音源，播放时会自动解析真实资源")
            self.online_status.setText(f"{len(getattr(self, '_sources', []))} 个音源可用")
            self.play_all_button.setEnabled(False)
            return
        client = ctx().client
        if client is None or not self._sources:
            self.online_empty.setVisible(True)
            self.online_list.setVisible(False)
            self.online_empty.set_text("在线音源不可用", "请检查 Node.js 运行时与音源配置")
            return
        self._token += 1
        token = self._token
        chosen = self.source_box.currentData() or ""
        targets = [s for s in self._sources if not chosen or s.id == chosen]
        self._online_tracks = []
        self._pending = {s.id for s in targets}
        self._errors = []
        self.online_list.set_tracks([])
        self.online_list.setVisible(False)
        self.online_empty.setVisible(True)
        self.online_empty.set_text("正在搜索…", text)
        self.online_status.setText(f"正在搜索 {len(targets)} 个音源…")
        self.play_all_button.setEnabled(False)
        client.ensure_started()
        for source in targets:
            client.search(
                source.id,
                text,
                1,
                lambda response, sid=source.id, tok=token: self._on_source_results(sid, tok, response),
                timeout=25000,
            )

    def _on_source_results(self, source_id: str, token: int, response: dict) -> None:
        if token != self._token:
            return
        self._pending.discard(source_id)
        source = next((s for s in self._sources if s.id == source_id), None)
        if not response.get("ok"):
            error = response.get("error") or "未知错误"
            self._errors.append(f"{source.label if source else source_id}：{error}")
        else:
            items = response.get("data") or []
            if isinstance(items, dict):
                items = items.get("items") or items.get("songs") or []
            tracks = tracks_from_items(items, source=source)
            self._online_tracks.extend(tracks)
        if self._pending:
            self.online_status.setText(
                f"正在搜索… 已完成 {len(self._sources) - len(self._pending) + 1} 个音源"
            )
            return
        self._finish_online(source_id)

    def _finish_online(self, last_source: str) -> None:
        tracks = self._online_tracks
        covers = ctx().covers
        for item in tracks[:60]:
            covers.prefetch(item)
        self.online_list.set_tracks(tracks)
        self.online_list.set_favorites(self._favorites_of(tracks))
        self.online_list.setVisible(bool(tracks))
        self.online_empty.setVisible(not tracks)
        if not tracks:
            self.online_empty.set_text(
                "没有找到在线结果",
                "；".join(self._errors[:2]) if self._errors else "换个关键词，或切换音源再试",
            )
        total_sources = len(self._sources)
        failed = len(self._errors)
        parts = [f"{len(tracks)} 首结果"]
        if failed:
            parts.append(f"{failed} 个音源失败")
        self.online_status.setText(" · ".join(parts))
        self.play_all_button.setEnabled(bool(tracks))
        if self._errors:
            log.info("在线搜索部分失败: %s", self._errors)

    def _favorites_of(self, tracks: list[Track]) -> set[str]:
        library = ctx().library
        found: set[str] = set()
        for track in tracks:
            try:
                if library.is_favorite(track):
                    found.add(track.id)
            except Exception:  # noqa: BLE001
                continue
        return found

    def _play_online(self, tracks: list, index: int) -> None:
        if not tracks:
            return
        ctx().player.play_tracks(
            tracks, index, context=f"在线搜索 · {self.field.text().strip()}"
        )
        self.online_list.set_current(tracks[index].id, True)

    def _play_all_online(self) -> None:
        if self._online_tracks:
            self._play_online(self._online_tracks, 0)

    def _menu_online(self, tracks: list, position) -> None:
        if not tracks:
            return
        track_menu(self, tracks, on_play=lambda items: self._play_online(items, 0)).exec(position)

    # ------------------------------------------------------------------ shared
    def _favorite(self, track: Track) -> None:
        library = ctx().library
        value = library.toggle_favorite(track)
        for widget in (self.local_list, self.online_list):
            ids = {t.id for t in widget.tracks() if t.favorite}
            if value:
                ids.add(track.id)
            else:
                ids.discard(track.id)
            widget.set_favorites(ids)
        window = ctx().window
        if window is not None:
            window.toast("已添加到「我喜欢」" if value else "已从「我喜欢」移除", "success" if value else "info")

    def refresh_theme(self) -> None:
        self.local_list.refresh_theme()
        self.online_list.refresh_theme()
        self.segments.update()
        self.online_status.setStyleSheet(
            f"font-size:9pt; color:{css_rgba(theme().palette.text, 0.5)};"
        )


class _MiniTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet("font-size:11pt; font-weight:700;")
