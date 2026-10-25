"""Shared base for pages that show a single track list."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.theme import Metrics, theme
from ...model.track import Track, format_duration
from ..context import ctx
from ..menus import track_menu
from ..widgets.tracklist import TrackListWidget
from ..widgets.searchfield import SearchField
from .page import CenteredBox, Page, PageHeader
from ..widgets.menu import themed_menu


def play_queue_for(
    full: list[Track], visible: list[Track], index: int
) -> tuple[list[Track], int]:
    """双击播放时，队列仍用整页顺序（歌单/我喜欢…），只用可见项定位起点。

    页内搜索只是“看”的过滤，不应该把队列切到搜索结果；否则下一首会跳到
    搜索结果里的下一首，而不是原歌单的下一首。
    """
    if not visible:
        return full, 0
    safe = max(0, min(index, len(visible) - 1))
    anchor = visible[safe]
    for position, track in enumerate(full):
        if track.id == anchor.id:
            return full, position
    return visible, safe


def filter_tracks(tracks: list[Track], query: str) -> list[Track]:
    """只保留匹配 *query* 的歌曲（标题/歌手/专辑/来源都参与匹配）。"""
    tokens = [token for token in str(query or "").casefold().split() if token]
    if not tokens:
        return list(tracks)
    result: list[Track] = []
    for track in tracks:
        haystack = " ".join(
            (track.title or "", track.artist or "", track.album or "",
             track.source_name or "")
        ).casefold()
        if all(token in haystack for token in tokens):
            result.append(track)
    return result


class TrackListPage(Page):
    """A page with a header and a rich track table.

    Subclasses override :meth:`load_tracks` and optionally :meth:`header_text`,
    :meth:`build_actions` and :meth:`context_label`.
    """

    title = "歌曲"
    subtitle = ""
    show_count = True

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(120)
        self._reload_timer.timeout.connect(self.reload)

        layout = self.content_layout
        layout.setContentsMargins(Metrics.page_pad, 14, Metrics.page_pad, 8)
        layout.setSpacing(8)
        # Header and table share one constrained column so the title lines up
        # with the table's left edge instead of floating at the page margin.
        column = QWidget()
        column.setStyleSheet("background:transparent;")
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        self.header = PageHeader(self.title, self.subtitle)
        column_layout.addWidget(self.header)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)
        self.filter = SearchField(
            f"搜索{self.title}", width=theme().scaled(260, factor=1.0)
        )
        self.filter.text_changed.connect(self._apply_filter)
        self.filter.submitted.connect(lambda _text: self._apply_filter())
        filter_row.addWidget(self.filter, 0)
        filter_row.addStretch(1)
        column_layout.addLayout(filter_row)

        spacer = QWidget()
        spacer.setFixedHeight(6)
        column_layout.addWidget(spacer)

        self.list = TrackListWidget()
        column_layout.addWidget(self.list, 1)
        layout.addWidget(
            CenteredBox(column, max_width=theme().scaled(1180, factor=1.0)), 1
        )

        self.list.play_requested.connect(self._on_play)
        self.list.menu_requested.connect(self._on_menu)
        self.list.favorite_clicked.connect(self._on_favorite)
        self.list.sort_requested.connect(self._on_sort)
        self.list.remove_requested.connect(self._on_remove)
        self.list.play_selected_requested.connect(self._play_selected)
        self.list.play_next_requested.connect(self._play_next_selected)
        self.list.enqueue_requested.connect(self._enqueue_selected)
        self.list.favorite_selected_requested.connect(self._favorite_selected)
        self.list.playlist_requested.connect(self._playlist_selected)
        self.list.remove_selected_requested.connect(self._remove_tracks)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.build_actions(actions)
        if actions.count():
            holder = QWidget()
            holder.setLayout(actions)
            self.header.add_action(holder)

        self._sort_key = "title"
        self._sort_asc = True

        library = ctx().library
        library.library_changed.connect(self._schedule_reload)
        library.favorites_changed.connect(self._schedule_favorites)
        library.track_updated.connect(lambda _id: self._schedule_reload())
        library.playlists_changed.connect(self._schedule_reload)
        self.list.set_empty_text("还没有歌曲", "导入音乐文件或文件夹后，歌曲会显示在这里")

    # ------------------------------------------------------------- overrides
    def load_tracks(self) -> list[Track]:
        raise NotImplementedError

    def build_actions(self, layout: QHBoxLayout) -> None:
        """Add header buttons (optional)."""

    def context_label(self) -> str:
        return self.title

    def empty_text(self) -> tuple[str, str]:
        return ("还没有歌曲", "导入音乐文件或文件夹后，歌曲会显示在这里")

    def _playlist_id(self) -> int | None:
        return None

    # ---------------------------------------------------------------- reload
    def on_show(self, payload: object = None) -> None:
        self.reload()

    def reload(self) -> None:
        self.list.set_can_remove_selected(self._playlist_id() is not None)
        try:
            tracks = self.load_tracks()
        except Exception as exc:  # noqa: BLE001 - keep the UI alive
            from ...core.logging_setup import log_exception

            log_exception("加载歌曲列表失败", exc)
            tracks = []
        self._tracks = tracks
        self._apply_filter()
        self._apply_favorites()
        self._sync_current()

    def _apply_filter(self, _text: str = "") -> None:
        query = self.filter.text().strip()
        visible = filter_tracks(self._tracks, query)
        self.list.set_tracks(visible)
        if query:
            self.list.set_empty_text(
                "没有匹配的歌曲", f"当前页面没有包含「{query}」的歌曲"
            )
        else:
            title, description = self.empty_text()
            self.list.set_empty_text(title, description)
        if query and self.show_count:
            self.header.set_subtitle(f"{len(visible)} / {len(self._tracks)} 首歌曲")
        else:
            self._update_header()

    def _update_header(self) -> None:
        if not self.show_count:
            return
        count = len(self._tracks)
        total = sum(track.duration_ms for track in self._tracks)
        if count == 0:
            self.header.set_subtitle(self.subtitle)
        else:
            self.header.set_subtitle(
                f"{count} 首歌曲 · {format_duration(total)}"
            )

    def _apply_favorites(self) -> None:
        try:
            favorite_ids = {track.id for track in self._tracks if track.favorite}
            self.list.set_favorites(favorite_ids)
        except Exception:  # noqa: BLE001
            pass

    def _sync_current(self) -> None:
        player = ctx().player
        track = player.current_track
        if track is not None:
            self.list.set_current(track.id, player.state == "playing")
            if player.state == "playing":
                self.list.ensure_current_visible()

    def refresh_theme(self) -> None:
        self.list.refresh_theme()
        self.header.update()

    def _schedule_reload(self) -> None:
        self._reload_timer.start()

    def _schedule_favorites(self) -> None:
        self._apply_favorites()
        self._reload_timer.start()

    # ----------------------------------------------------------------- events
    def _on_play(self, tracks: list, index: int) -> None:
        if not tracks:
            return
        queue, start = play_queue_for(self._tracks, tracks, index)
        try:
            ctx().player.play_tracks(queue, start, context=self.context_label())
        except Exception as exc:  # noqa: BLE001
            from ...core.logging_setup import log_exception

            log_exception("播放失败", exc)

    def _on_menu(self, tracks: list, position) -> None:
        if not tracks:
            return
        playlist_id = self._playlist_id()
        menu = track_menu(
            self,
            tracks,
            playlist_id=playlist_id,
            on_play=lambda items: self._play(items, 0),
            on_remove=self._remove_tracks if playlist_id else None,
        )
        menu.exec(position)

    def _play(self, tracks: list, index: int) -> None:
        ctx().player.play_tracks(tracks, index, context=self.context_label())

    # ---------------------------------------------------------- multi-selection
    def _play_selected(self, tracks: list) -> None:
        if tracks:
            self._on_play(tracks, 0)

    def _play_next_selected(self, tracks: list) -> None:
        if not tracks:
            return
        try:
            count = ctx().player.play_next_in_queue(tracks)
        except Exception as exc:  # noqa: BLE001
            from ...core.logging_setup import log_exception

            log_exception("下一首播放失败", exc)
            return
        window = ctx().window
        if window is not None and count:
            window.toast(f"已把 {count} 首歌曲插到下一首", "info")

    def _enqueue_selected(self, tracks: list) -> None:
        if not tracks:
            return
        try:
            count = ctx().player.enqueue(tracks)
        except Exception as exc:  # noqa: BLE001
            from ...core.logging_setup import log_exception

            log_exception("加入队列失败", exc)
            return
        window = ctx().window
        if window is not None and count:
            window.toast(f"已加入播放队列：{count} 首", "info")

    def _favorite_selected(self, tracks: list) -> None:
        if not tracks:
            return
        library = ctx().library
        added = 0
        for track in tracks:
            if not library.is_favorite(track):
                library.set_favorite(track, True)
                added += 1
        self._apply_favorites()
        if self._playlist_id() == library.favorites_playlist_id():
            self._schedule_reload()
        window = ctx().window
        if window is not None:
            window.toast(
                f"已收藏 {added} 首歌曲" if added else "所选歌曲已在「我喜欢」中",
                "success" if added else "info",
            )

    def _playlist_selected(self, tracks: list) -> None:
        if not tracks:
            return
        from PySide6.QtWidgets import QMenu

        from ..dialogs import ask_text

        library = ctx().library
        playlists = library.playlists_all()
        if not playlists:
            text, ok = ask_text(self, "新建歌单", "给这个歌单起个名字")
            name = (text or "").strip()
            if ok and name:
                playlist_id = library.create_playlist(name)
                count = library.add_to_playlist(playlist_id, tracks)
                window = ctx().window
                if window is not None and count:
                    window.toast(f"已新建歌单并添加 {count} 首歌曲", "success")
            return
        menu = themed_menu(self)
        for playlist in playlists:
            action = menu.addAction(f"{playlist.name}（{playlist.track_count} 首）")
            action.triggered.connect(
                lambda _=False, pid=playlist.id: self._add_selected_to_playlist(pid, tracks)
            )
        menu.exec(self.mapToGlobal(self.rect().center()))

    def _add_selected_to_playlist(self, playlist_id: int, tracks: list) -> None:
        library = ctx().library
        count = library.add_to_playlist(playlist_id, tracks)
        window = ctx().window
        if window is not None and count:
            window.toast(f"已添加 {count} 首歌曲到歌单", "success")

    def _on_favorite(self, track: Track) -> None:
        library = ctx().library
        value = library.toggle_favorite(track)
        self._apply_favorites()
        if self._playlist_id() == library.favorites_playlist_id():
            self._schedule_reload()
        window = ctx().window
        if window is not None:
            window.toast(
                "已添加到「我喜欢」" if value else "已从「我喜欢」移除",
                "success" if value else "info",
            )

    def _on_sort(self, key: str, ascending: bool) -> None:
        self._sort_key = key
        self._sort_asc = ascending
        self.reload()

    def _on_remove(self, tracks: list) -> None:
        self._remove_tracks(tracks)

    def _remove_tracks(self, tracks: list) -> None:
        playlist_id = self._playlist_id()
        if not playlist_id or not tracks:
            return
        ids = [track.id for track in tracks]
        count = ctx().library.remove_from_playlist(playlist_id, ids)
        window = ctx().window
        if window is not None and count:
            window.toast(f"已从歌单移除 {count} 首歌曲", "info")
        self.reload()

    # ----------------------------------------------------------------- helpers
    def selected_tracks(self) -> list[Track]:
        return self.list.selected_tracks()
