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

import time

from ...core.logging_setup import get_logger
from ...core.theme import css_rgba, rgba, theme
from ...model.track import Track
from ...online.matching import dedupe_tracks
from ...online.models import build_sources, tracks_from_items
from ..context import ctx
from ..menus import track_menu
from ..widgets.cards import AlbumCard, ArtistCard, CardGrid
from ..widgets.common import TextButton
from ..widgets.searchfield import SearchField, SegmentedControl
from ..widgets.source_filter import HistoryChips, SourceFilterBar
from ..widgets.tracklist import TrackListWidget
from .page import EmptyState, Page

log = get_logger(__name__)

#: A 64-source search must not wait for the slowest plugin: results stream in,
#: each request is capped, and the whole sweep has a hard deadline.
SEARCH_PER_SOURCE_TIMEOUT_MS = 9000
SEARCH_CONCURRENCY = 12
SEARCH_DEADLINE_MS = 12000
SEARCH_CACHE_TTL_S = 300
SEARCH_RENDER_INTERVAL_MS = 60


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
        self._queue: list = []
        self._active = 0
        self._done = 0
        self._online_total = 0
        self._timed_out = 0
        self._finished = False
        self._query = ""
        self._request_ids: list[int] = []
        self._source_speed: dict[str, float] = {}
        self._dispatch_at: dict[str, float] = {}
        self._search_cache: dict[tuple[str, str], tuple[float, list[Track]]] = {}
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(SEARCH_RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._render_online)
        self._deadline_timer = QTimer(self)
        self._deadline_timer.setSingleShot(True)
        self._deadline_timer.setInterval(SEARCH_DEADLINE_MS)
        self._deadline_timer.timeout.connect(self._on_deadline)

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

        self.history.set_history(self._history_items())
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
        layout.setSpacing(0)

        self.local_stack = QStackedWidget()
        layout.addWidget(self.local_stack, 1)

        intro = QWidget()
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(0, 0, 0, 0)
        intro_layout.addStretch(1)
        self.local_empty = EmptyState(
            "搜索你的音乐库",
            "输入歌曲、专辑或歌手的名字；想听网络音乐请切换到「在线」",
            icon_name="search",
        )
        intro_layout.addWidget(self.local_empty)
        intro_layout.addStretch(2)
        self.local_stack.addWidget(intro)
        self._local_intro = intro

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

        # Songs first: a keyword search is almost always about a song.
        self._track_title = _MiniTitle("歌曲")
        holder_layout.addWidget(self._track_title)
        self.local_list = TrackListWidget()
        self.local_list.play_requested.connect(self._play_local)
        self.local_list.menu_requested.connect(self._menu_local)
        self.local_list.favorite_clicked.connect(self._favorite)
        holder_layout.addWidget(self.local_list)

        self._album_title = _MiniTitle("专辑")
        holder_layout.addWidget(self._album_title)
        self.album_grid = CardGrid()
        holder_layout.addWidget(self.album_grid)

        self._artist_title = _MiniTitle("歌手")
        holder_layout.addWidget(self._artist_title)
        self.artist_grid = CardGrid()
        holder_layout.addWidget(self.artist_grid)

        holder_layout.addStretch(1)
        self.local_scroll.setWidget(holder)
        self.local_stack.addWidget(self.local_scroll)
        return page

    def _build_online(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.online_toolbar = QWidget()
        toolbar = QHBoxLayout(self.online_toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(10)
        self.source_filter = SourceFilterBar()
        self.source_filter.changed.connect(lambda _sid: self._run_online(self.field.text()))
        toolbar.addWidget(self.source_filter, 1)
        self.manage_button = TextButton("管理音源", icon_name="cloud", size=30)
        self.manage_button.clicked.connect(self._manage_sources)
        toolbar.addWidget(self.manage_button)
        self.play_all_button = TextButton("全部播放", icon_name="play", accent=True)
        self.play_all_button.clicked.connect(self._play_all_online)
        self.play_all_button.setEnabled(False)
        toolbar.addWidget(self.play_all_button)
        layout.addWidget(self.online_toolbar)

        self.online_status = QLabel("")
        self.online_status.setStyleSheet(
            f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(theme().palette.text, 0.5)};"
        )
        layout.addWidget(self.online_status)

        self.online_stack = QStackedWidget()
        layout.addWidget(self.online_stack, 1)

        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(4)
        empty_layout.addStretch(1)
        self.online_empty = EmptyState(
            "搜索在线音乐",
            "结果来自已启用的音源，播放时会自动解析真实资源",
            icon_name="globe",
        )
        self.online_empty.setMinimumHeight(210)
        empty_layout.addWidget(self.online_empty)
        self.history = HistoryChips()
        self.history.requested.connect(self._search_history)
        empty_layout.addWidget(self.history, 0, Qt.AlignHCenter)
        empty_layout.addStretch(3)
        self.online_stack.addWidget(empty_page)
        self._online_empty_page = empty_page

        self.online_list = TrackListWidget()
        self.online_list.play_requested.connect(self._play_online)
        self.online_list.menu_requested.connect(self._menu_online)
        self.online_list.favorite_clicked.connect(self._favorite)
        self.online_stack.addWidget(self.online_list)
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
            self.local_stack.setCurrentWidget(self._local_intro)
            self.local_empty.set_text(
                "搜索你的音乐库",
                "输入歌曲、专辑或歌手的名字；想听网络音乐请切换到「在线」",
            )
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
        if has_any:
            self.local_stack.setCurrentWidget(self.local_scroll)
            self.local_list.setFixedHeight(min(420, 56 * max(1, len(self.local_list.tracks())) + 44))
        else:
            self.local_stack.setCurrentWidget(self._local_intro)
            self.local_empty.set_text("没有找到结果", f"音乐库中没有与「{text}」匹配的内容")
        self.local_list.set_empty_text("没有找到歌曲", "")
        player = ctx().player
        current = player.current_track if player is not None else None
        if current is not None:
            self.local_list.set_current(current.id, player.state == "playing")

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
        current = self.source_filter.current()
        self.source_filter.blockSignals(True)
        self.source_filter.set_sources([(s.id, s.label or s.name) for s in self._sources])
        self.source_filter.set_current(current or "", emit=False)
        self.source_filter.blockSignals(False)
        if not self.field.text().strip():
            if not self._sources:
                self.online_status.setText("没有可用的在线音源")
            else:
                self.online_status.setText(f"{len(self._sources)} 个音源可用")
            self.online_status.setVisible(bool(self._sources))

    def _run_online(self, text: str, *, force: bool = False) -> None:
        text = text.strip()
        if not text:
            self._online_tracks = []
            self.online_list.set_tracks([])
            self.online_toolbar.setVisible(False)
            self.online_status.setVisible(False)
            self.online_stack.setCurrentWidget(self._online_empty_page)
            ready = len(getattr(self, "_sources", []))
            self.online_empty.set_text(
                "搜索在线音乐",
                f"{ready} 个音源已就绪 · 输入关键词后自动并行搜索并即时显示结果"
                if ready
                else "还没有可用的音源，请先在设置中启用或导入",
            )
            self.play_all_button.setEnabled(False)
            self.history.set_history(self._history_items())
            self.history.setVisible(bool(self.history.items()))
            return
        client = ctx().client
        if client is None or not self._sources:
            self.online_toolbar.setVisible(False)
            self.online_status.setVisible(False)
            self.online_stack.setCurrentWidget(self._online_empty_page)
            self.history.setVisible(True)
            self.online_empty.set_text("在线音源未就绪", "正在启动 Node.js 运行时与音源插件")
            return

        cache = getattr(self, "_online_cache", None)
        if cache is None:
            cache = self._online_cache = {}
        cache_key = (text, self.source_filter.current() or "")
        cached = cache.get(cache_key)
        if cached is not None and not force and time.monotonic() - cached[0] < 300:
            tracks, errors, total = cached[1], cached[2], cached[3]
            self._online_tracks = list(tracks)
            self._errors = list(errors)
            self._online_total = total
            self.online_toolbar.setVisible(True)
            self.online_status.setVisible(True)
            self.online_stack.setCurrentWidget(self.online_list)
            self.online_list.set_tracks(list(tracks))
            self.online_status.setText(
                f"缓存结果 · {len(tracks)} 首（5 分钟内有效，点搜索图标可刷新）"
            )
            self.play_all_button.setEnabled(bool(tracks))
            return

        for request_id in getattr(self, "_request_ids", []):
            try:
                ctx().client.cancel(request_id)
            except Exception:  # noqa: BLE001
                pass
        self._token += 1
        token = self._token
        self._query = text
        chosen = self.source_filter.current() or ""
        targets = [s for s in self._sources if not chosen or s.id == chosen]
        self._online_tracks = []
        self._errors = []
        self._online_total = len(targets)
        self._done = 0
        self._active = 0
        self._finished = False
        self._request_ids = []
        self.online_list.set_tracks([])
        self.online_list.set_empty_text("正在搜索…", "结果会在音源返回后即时出现")
        self.online_toolbar.setVisible(True)
        self.online_status.setVisible(True)
        self.online_stack.setCurrentWidget(self.online_list)
        self.online_status.setText(f"正在搜索 {len(targets)} 个音源…")
        self.play_all_button.setEnabled(False)
        client.ensure_started()

        # Repeat searches are served from a short-lived cache so the very common
        # "same song again" case renders instantly.
        now = time.monotonic()
        pending: list = []
        for source in targets:
            cached = self._search_cache.get((text, source.id))
            if cached and not force and (now - cached[0]) < SEARCH_CACHE_TTL_S:
                self._online_tracks.extend(cached[1])
                self._done += 1
            else:
                pending.append(source)
        if self._online_tracks:
            self._render_online()
        if not pending:
            self._finish_online("")
            return

        pending.sort(key=lambda s: self._source_speed.get(s.id, 1.0))
        self._queue = pending
        self._dispatch(token)
        self._render_timer.start()
        self._deadline_timer.start()

    def _dispatch(self, token: int) -> None:
        client = ctx().client
        while (
            self._active < SEARCH_CONCURRENCY
            and self._queue
            and token == self._token
            and not self._finished
        ):
            source = self._queue.pop(0)
            self._active += 1
            self._dispatch_at[source.id] = time.monotonic()
            request_id = client.search(
                source.id,
                self._query,
                1,
                lambda response, sid=source.id, tok=token: self._on_source_results(sid, tok, response),
                timeout=SEARCH_PER_SOURCE_TIMEOUT_MS,
            )
            if isinstance(request_id, int) and request_id > 0:
                self._request_ids.append(request_id)

    def _on_source_results(self, source_id: str, token: int, response: dict) -> None:
        if token != self._token or self._finished:
            return
        self._active = max(0, self._active - 1)
        self._done += 1
        started = self._dispatch_at.pop(source_id, None)
        if started is not None:
            elapsed = max(0.05, time.monotonic() - started)
            previous = self._source_speed.get(source_id)
            self._source_speed[source_id] = elapsed if previous is None else (previous * 0.7 + elapsed * 0.3)
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
            self._search_cache[(self._query, source_id)] = (time.monotonic(), tracks)
        self._dispatch(token)
        # Throttled repaint after every batch: results must appear while the
        # slower plugins are still working, not after the last one answers.
        if not self._finished:
            self._render_timer.start()
        if self._queue or self._active:
            return
        self._finish_online(source_id)

    def _render_online(self) -> None:
        tracks = self._online_tracks
        if self._dedupe_enabled():
            tracks = dedupe_tracks(tracks)
        if not self._finished:
            # Show partial results while slower plugins are still answering; the
            # previous implementation waited for every source and only then
            # painted, which is what made a 64-source search feel frozen.
            self.online_status.setText(
                f"已找到 {len(tracks)} 首 · 正在搜索 {self._done}/{self._online_total} 个音源…"
            )
            if tracks:
                self.online_stack.setCurrentWidget(self.online_list)
        self.online_list.set_tracks(list(tracks))
        self.online_list.set_favorites(self._favorites_of(tracks))
        counts: dict[str, int] = {}
        for item in tracks:
            counts[item.source_id] = counts.get(item.source_id, 0) + 1
        counts[""] = len(tracks)
        self.source_filter.set_counts(counts)
        self.play_all_button.setEnabled(bool(tracks))

    def _dedupe_enabled(self) -> bool:
        try:
            return bool(ctx().settings.get("online.dedupe_results", True))
        except Exception:  # noqa: BLE001
            return True

    def _on_deadline(self) -> None:
        if self._finished:
            return
        for request_id in self._request_ids:
            try:
                ctx().client.cancel(request_id)
            except Exception:  # noqa: BLE001
                pass
        timed_out = self._active + len(self._queue)
        self._queue.clear()
        self._active = 0
        self._done = self._online_total
        self._timed_out = timed_out
        self._finish_online("")

    def _finish_online(self, last_source: str) -> None:
        if self._finished:
            return
        cache = getattr(self, "_online_cache", None)
        if cache is not None:
            cache[(self._query, self.source_filter.current() or "")] = (
                time.monotonic(), list(self._online_tracks), list(self._errors), self._online_total,
            )
        self._finished = True
        self._deadline_timer.stop()
        self._render_timer.stop()
        tracks = self._online_tracks
        covers = ctx().covers
        for item in tracks[:80]:
            covers.prefetch(item)
        self._render_online()
        if tracks:
            self.online_stack.setCurrentWidget(self.online_list)
            self.online_list.set_empty_text("没有找到歌曲", "")
        else:
            self.online_stack.setCurrentWidget(self._online_empty_page)
            self.history.setVisible(False)
            self.online_empty.set_text(
                "没有找到结果",
                "；".join(self._errors[:2]) if self._errors else "换个关键词，或检查音源设置",
            )
        failed = len(self._errors)
        timed_out = getattr(self, "_timed_out", 0)
        parts = [f"{len(tracks)} 首结果", f"{self._online_total} 个音源"]
        if failed:
            parts.append(f"{failed} 个失败")
        if timed_out:
            parts.append(f"{timed_out} 个超时")
        self.online_status.setText(" · ".join(parts))
        if self._errors:
            log.info("在线搜索部分失败: %s", self._errors)
        self._remember_query(self.field.text().strip())

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

    # ------------------------------------------------------------- 历史 / 管理
    def _history_items(self) -> list[str]:
        raw = ctx().settings.get("online.search_history", []) or []
        return [str(item) for item in raw][:8]

    def _remember_query(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        items = [item for item in self._history_items() if item != text]
        items.insert(0, text)
        ctx().settings.set("online.search_history", items[:8])
        self.history.set_history(items[:8])

    def _search_history(self, text: str) -> None:
        self.field.set_text(text)
        self.segments.set_current(1)
        self._mode = 1
        self.stack.setCurrentIndex(1)
        self._run_online(text, force=True)

    def _manage_sources(self) -> None:
        window = ctx().window
        if window is not None:
            window.navigate("settings", "online")

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
            f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(theme().palette.text, 0.5)};"
        )


class _MiniTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(f"font-size:{theme().pt(11):.1f}pt; font-weight:700;")
