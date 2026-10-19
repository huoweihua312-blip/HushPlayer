"""Home / overview page."""

from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...model.track import Track
from ..context import ctx
from ..widgets.cards import AlbumCard, CardGrid, PlaylistCard
from ..widgets.common import TextButton
from ..widgets.tracklist import TrackListWidget
from .page import EmptyState, PageHeader, ScrollPage


class HomePage(ScrollPage):
    route = "home"
    title = "首页"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.header = PageHeader(self._greeting(), "欢迎回来")
        self.body.addWidget(self.header)

        self.empty = EmptyState(
            "欢迎使用 HushPlayer",
            "添加音乐文件夹，或搜索在线音乐开始你的第一首歌",
            icon_name="headphones",
            action_text="添加音乐文件夹",
        )
        self.empty.action_clicked.connect(self._add_folder)
        self.body.addWidget(self.empty)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(26)

        shelf_header = _SectionTitle("最近播放", "继续收听")
        content_layout.addWidget(shelf_header)
        self._recent_row = QHBoxLayout()
        self._recent_row.setContentsMargins(0, 0, 0, 0)
        self._recent_row.setSpacing(18)
        recent_holder = QWidget()
        recent_holder.setLayout(self._recent_row)
        content_layout.addWidget(recent_holder)

        added_header = _SectionTitle("最近添加", "音乐库")
        content_layout.addWidget(added_header)
        self._added_grid = CardGrid()
        content_layout.addWidget(self._added_grid)

        tracks_header = _SectionTitle("常听歌曲", "按播放次数排序")
        content_layout.addWidget(tracks_header)
        self._top_list = TrackListWidget()
        self._top_list.setFixedHeight(320)
        self._top_list.play_requested.connect(self._on_play)
        self._top_list.favorite_clicked.connect(self._on_favorite)
        self._top_list.menu_requested.connect(self._on_menu)
        content_layout.addWidget(self._top_list)

        self.body.addWidget(self.content)
        self.body.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.reload)
        ctx().library.library_changed.connect(self._timer.start)
        ctx().library.favorites_changed.connect(self._timer.start)
        ctx().library.playlists_changed.connect(self._timer.start)
        ctx().player.track_changed.connect(lambda _t: self._timer.start())
        self.reload()

    # ------------------------------------------------------------------ data
    def _greeting(self) -> str:
        hour = _dt.datetime.now().hour
        if hour < 5:
            return "夜深了"
        if hour < 12:
            return "早上好"
        if hour < 18:
            return "下午好"
        return "晚上好"

    def on_show(self, payload: object = None) -> None:
        self.header.set_title(self._greeting())
        self.reload()

    def reload(self) -> None:
        library = ctx().library
        try:
            stats = library.stats
        except Exception:  # noqa: BLE001
            stats = None
        total_tracks = stats.track_count if stats is not None else 0
        has_content = bool(total_tracks)
        self.empty.setVisible(not has_content)
        self.content.setVisible(has_content)
        if not has_content:
            self.header.set_subtitle("本地音乐库还是空的")
            return
        albums = stats.album_count
        artists = stats.artist_count
        self.header.set_subtitle(f"{total_tracks} 首歌曲 · {albums} 张专辑 · {artists} 位艺术家")

        recent = library.recent(12)
        self._fill_recent(recent)
        added = library.recently_added(12)
        self._fill_added(added)
        top = library.most_played(12)
        self._top_list.set_tracks(top)
        self._top_list.set_empty_text("还没有播放记录", "播放歌曲后这里会显示你最常听的音乐")
        self._top_list.set_favorites({t.id for t in top if t.favorite})
        current = ctx().player.current_track
        if current is not None:
            self._top_list.set_current(current.id, ctx().player.state == "playing")

    def _fill_recent(self, tracks: list[Track]) -> None:
        while self._recent_row.count():
            item = self._recent_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        library = ctx().library
        seen: set[str] = set()
        count = 0
        for track in tracks:
            album_id = track.album_id or track.album
            if not album_id or album_id in seen:
                continue
            seen.add(album_id)
            albums = [a for a in library.albums() if a.id == album_id]
            if not albums:
                continue
            card = AlbumCard(albums[0], size=150)
            card.activated.connect(self._open_album)
            self._recent_row.addWidget(card)
            count += 1
            if count >= 6:
                break
        if count == 0:
            for playlist in library.playlists_all():
                if playlist.system:
                    continue
                card = PlaylistCard(playlist, size=150)
                card.activated.connect(self._open_playlist)
                self._recent_row.addWidget(card)
                count += 1
                if count >= 6:
                    break
        self._recent_row.addStretch(1)

    def _fill_added(self, tracks: list[Track]) -> None:
        library = ctx().library
        seen: set[str] = set()
        cards = []
        for track in tracks:
            if track.album_id in seen or not track.album_id:
                continue
            seen.add(track.album_id)
            albums = [a for a in library.albums() if a.id == track.album_id]
            if not albums:
                continue
            card = AlbumCard(albums[0], size=150)
            card.activated.connect(self._open_album)
            cards.append(card)
            if len(cards) >= 8:
                break
        self._added_grid.set_cards(cards)

    # ----------------------------------------------------------------- events
    def _open_album(self, album) -> None:
        window = ctx().window
        if window is not None and album is not None:
            window.navigate("album", album.id)

    def _open_playlist(self, playlist) -> None:
        window = ctx().window
        if window is not None and playlist is not None:
            window.navigate(f"playlist:{playlist.id}")

    def _on_play(self, tracks: list, index: int) -> None:
        if tracks:
            ctx().player.play_tracks(tracks, index, context="常听歌曲")

    def _on_favorite(self, track) -> None:
        value = ctx().library.toggle_favorite(track)
        window = ctx().window
        if window is not None:
            window.toast("已添加到「我喜欢」" if value else "已从「我喜欢」移除", "success" if value else "info")

    def _on_menu(self, tracks: list, position) -> None:
        from ..menus import track_menu

        if not tracks:
            return
        track_menu(self, tracks, on_play=lambda items: self._on_play(items, 0)).exec(position)

    def _add_folder(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "添加音乐文件夹")
        if not folder:
            return
        settings = ctx().settings
        folders = list(settings.get("library.folders", []) or [])
        if folder not in folders:
            folders.append(folder)
            settings.set("library.folders", folders)
        ctx().library.scan(folders)
        window = ctx().window
        if window is not None:
            window.toast("正在扫描音乐文件夹…", "info")

    def refresh_theme(self) -> None:
        self.header.update()
        self._top_list.refresh_theme()
        self.reload()


class _SectionTitle(QWidget):
    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from ...core.theme import css_rgba, rgba, theme

        self.title = QLabel(title)
        self.hint = QLabel(hint)
        self.title.setStyleSheet(f"font-size:{theme().pt(14):.1f}pt; font-weight:700;")
        self.hint.setStyleSheet(f"font-size:{theme().pt(9):.1f}pt; color:{css_rgba(theme().palette.text, 0.45)};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.hint, 0, Qt.AlignBottom)
        layout.addStretch(1)
