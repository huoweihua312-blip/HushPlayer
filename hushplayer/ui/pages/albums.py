"""Album grid and album detail pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

from ...model.track import format_duration
from ..context import ctx
from ..menus import track_menu
from ..widgets.cards import AlbumCard, CardGrid
from ..widgets.common import TextButton
from ..widgets.hero import HeroPanel
from ..widgets.tracklist import TrackListWidget
from .page import BackButton, Page, PageHeader, ScrollPage


class AlbumsPage(ScrollPage):
    route = "albums"
    title = "专辑"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.header = PageHeader("专辑", "音乐库中的专辑")
        self.body.addWidget(self.header)
        self.grid = CardGrid()
        self.body.addWidget(self.grid)
        self.body.addStretch(1)
        ctx().library.library_changed.connect(self._schedule_reload)
        self._timer = __import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self.reload)
        self.reload()

    def _schedule_reload(self) -> None:
        self._timer.start()

    def on_show(self, payload: object = None) -> None:
        self.reload()

    def reload(self) -> None:
        try:
            albums = ctx().library.albums()
        except Exception:  # noqa: BLE001
            albums = []
        cards = []
        for album in albums:
            card = AlbumCard(album)
            card.activated.connect(self._open)
            card.context_requested.connect(self._menu)
            cards.append(card)
        self.grid.set_cards(cards)
        self.header.set_subtitle(
            f"{len(albums)} 张专辑" if albums else "扫描音乐库后，专辑会显示在这里"
        )
        self.scroll_to_top()

    def _open(self, album) -> None:
        if album is None:
            return
        window = ctx().window
        if window is not None:
            window.navigate("album", album.id)

    def _menu(self, album, position) -> None:
        if album is None:
            return
        menu = QMenu(self)
        menu.addAction(
            "播放专辑",
            lambda: self._play_album(album),
        )
        menu.addAction(
            "随机播放",
            lambda: self._play_album(album, shuffle=True),
        )
        menu.addSeparator()
        menu.addAction("查看专辑", lambda: self._open(album))
        menu.exec(position)

    def _play_album(self, album, *, shuffle: bool = False) -> None:
        tracks = ctx().library.album_tracks(album.id)
        if not tracks:
            return
        player = ctx().player
        if shuffle:
            player.set_shuffle(True)
        player.play_tracks(tracks, 0, context=f"专辑 · {album.name}")

    def refresh_theme(self) -> None:
        self.header.update()
        self.reload()


class AlbumPage(Page):
    route = "album"
    title = "专辑"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._album = None
        layout = self.content_layout
        layout.setContentsMargins(30, 14, 30, 0)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.back = BackButton()
        self.back.clicked.connect(self._go_back)
        top.addWidget(self.back)
        top.addStretch(1)
        layout.addLayout(top)

        self.hero = HeroPanel(cover_size=190)
        self.hero.play_requested.connect(lambda: self._play(shuffle=False))
        self.hero.shuffle_requested.connect(lambda: self._play(shuffle=True))
        self.hero.menu_requested.connect(self._hero_menu)
        layout.addWidget(self.hero)

        self.list = TrackListWidget()
        self.list.play_requested.connect(self._on_play)
        self.list.menu_requested.connect(self._on_menu)
        self.list.favorite_clicked.connect(self._on_favorite)
        self.list.remove_requested.connect(lambda _tracks: None)
        layout.addWidget(self.list, 1)

        ctx().library.library_changed.connect(self._refresh)
        ctx().library.favorites_changed.connect(self._apply_favorites)

    # ------------------------------------------------------------------ load
    def on_show(self, payload: object = None) -> None:
        album_id = payload if isinstance(payload, str) else ""
        if album_id:
            self._load(album_id)
        else:
            self._refresh()

    def _load(self, album_id: str) -> None:
        album = None
        try:
            for candidate in ctx().library.albums():
                if candidate.id == album_id:
                    album = candidate
                    break
        except Exception:  # noqa: BLE001
            album = None
        self._album = album
        if album is None:
            self.list.set_tracks([])
            self.list.set_empty_text("找不到这张专辑", "它可能已从音乐库中移除")
            return
        self.hero.set_cover_track(_album_cover_item(album))
        self.hero.set_text(
            album.name or "未知专辑",
            album.artist or "未知艺术家",
            _album_meta(album),
        )
        self.hero.set_actions_visible(True)
        self._refresh()

    def _refresh(self) -> None:
        album = self._album
        if album is None:
            return
        tracks = ctx().library.album_tracks(album.id)
        self.list.set_tracks(tracks)
        self.list.set_empty_text("这张专辑还没有歌曲", "")
        self._apply_favorites()
        player = ctx().player
        track = player.current_track
        if track is not None:
            self.list.set_current(track.id, player.state == "playing")
        self.hero.set_text(album.name or "未知专辑", album.artist or "未知艺术家", _album_meta(album))

    def _apply_favorites(self) -> None:
        self.list.set_favorites({track.id for track in self.list.tracks() if track.favorite})

    # ----------------------------------------------------------------- events
    def _go_back(self) -> None:
        window = ctx().window
        if window is not None:
            window.go_back()

    def _play(self, *, shuffle: bool = False) -> None:
        tracks = self.list.tracks()
        if not tracks:
            return
        player = ctx().player
        if shuffle:
            player.set_shuffle(True)
        name = self._album.name if self._album is not None else "专辑"
        player.play_tracks(tracks, 0, context=f"专辑 · {name}")

    def _on_play(self, tracks: list, index: int) -> None:
        name = self._album.name if self._album is not None else "专辑"
        ctx().player.play_tracks(tracks, index, context=f"专辑 · {name}")

    def _on_menu(self, tracks: list, position) -> None:
        if not tracks:
            return
        menu = track_menu(self, tracks, on_play=lambda items: self._on_play(items, 0))
        menu.exec(position)

    def _on_favorite(self, track) -> None:
        value = ctx().library.toggle_favorite(track)
        self._refresh()
        window = ctx().window
        if window is not None:
            window.toast("已添加到「我喜欢」" if value else "已从「我喜欢」移除", "success" if value else "info")

    def _hero_menu(self) -> None:
        album = self._album
        if album is None:
            return
        menu = QMenu(self)
        menu.addAction("播放专辑", lambda: self._play())
        menu.addAction("随机播放", lambda: self._play(shuffle=True))
        menu.addAction("前往艺术家", self._go_artist)
        menu.exec(self.hero.more_button.mapToGlobal(self.hero.more_button.rect().bottomLeft()))

    def _go_artist(self) -> None:
        album = self._album
        if album is None:
            return
        tracks = ctx().library.album_tracks(album.id)
        if not tracks:
            return
        artists = ctx().library.artists(album.artist)
        match = next((a for a in artists if a.name == album.artist), None)
        window = ctx().window
        if match is not None and window is not None:
            window.navigate("artist", match.id)

    def refresh_theme(self) -> None:
        self.hero.refresh_theme()
        self.list.refresh_theme()
        self.update()


def _album_cover_item(album):
    """Return something the cover provider can resolve for an album."""
    from ...model.track import Track

    if album.artwork_path:
        return Track(
            id=f"album-cover:{album.id}",
            title=album.name,
            path="",
            artwork_path=album.artwork_path,
        )
    if album.cover_track_id:
        track = ctx().library.track(album.cover_track_id)
        if track is not None:
            return track
    return Track(id=f"album-cover:{album.id}", title=album.name, path="")


def _album_meta(album) -> str:
    parts = []
    if album.year:
        parts.append(str(album.year))
    if album.genre:
        parts.append(album.genre)
    parts.append(f"{album.track_count} 首歌曲")
    if album.duration_ms:
        parts.append(format_duration(album.duration_ms))
    return " · ".join(parts)
