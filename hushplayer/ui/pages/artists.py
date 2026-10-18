"""Artist grid and artist detail pages."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...model.track import format_duration
from ..context import ctx
from ..menus import track_menu
from ..widgets.cards import AlbumCard, ArtistCard, CardGrid
from ..widgets.hero import HeroPanel
from ..widgets.searchfield import SegmentedControl
from ..widgets.tracklist import TrackListWidget
from .page import BackButton, Page, PageHeader, ScrollPage


class ArtistsPage(ScrollPage):
    route = "artists"
    title = "艺术家"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.header = PageHeader("艺术家", "音乐库中的艺术家")
        self.body.addWidget(self.header)
        self.grid = CardGrid()
        self.body.addWidget(self.grid)
        self.body.addStretch(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(160)
        self._timer.timeout.connect(self.reload)
        ctx().library.library_changed.connect(self._timer.start)
        self.reload()

    def on_show(self, payload: object = None) -> None:
        self.reload()

    def reload(self) -> None:
        try:
            artists = ctx().library.artists()
        except Exception:  # noqa: BLE001
            artists = []
        cards = []
        for artist in artists:
            card = ArtistCard(artist)
            card.activated.connect(self._open)
            card.context_requested.connect(self._menu)
            cards.append(card)
        self.grid.set_cards(cards)
        self.header.set_subtitle(
            f"{len(artists)} 位艺术家" if artists else "扫描音乐库后，艺术家会显示在这里"
        )
        self.scroll_to_top()

    def _open(self, artist) -> None:
        if artist is None:
            return
        window = ctx().window
        if window is not None:
            window.navigate("artist", artist.id)

    def _menu(self, artist, position) -> None:
        if artist is None:
            return
        menu = QMenu(self)
        menu.addAction("播放全部歌曲", lambda: self._play(artist))
        menu.addAction("查看艺术家", lambda: self._open(artist))
        menu.exec(position)

    def _play(self, artist) -> None:
        tracks = ctx().library.artist_tracks(artist.id)
        if not tracks:
            return
        ctx().player.play_tracks(tracks, 0, context=f"艺术家 · {artist.name}")

    def refresh_theme(self) -> None:
        self.header.update()
        self.reload()


class ArtistPage(Page):
    route = "artist"
    title = "艺术家"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._artist = None
        self._tracks: list = []
        layout = self.content_layout
        layout.setContentsMargins(30, 14, 30, 0)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.back = BackButton()
        self.back.clicked.connect(self._go_back)
        top.addWidget(self.back)
        top.addStretch(1)
        layout.addLayout(top)

        self.hero = HeroPanel(cover_size=170, round_cover=True)
        self.hero.play_requested.connect(lambda: self._play(shuffle=False))
        self.hero.shuffle_requested.connect(lambda: self._play(shuffle=True))
        self.hero.menu_requested.connect(self._hero_menu)
        layout.addWidget(self.hero)

        self.segments = SegmentedControl(["歌曲", "专辑"])
        self.segments.setFixedWidth(180)
        self.segments.changed.connect(self._on_segment)
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 6)
        row.addWidget(self.segments)
        row.addStretch(1)
        layout.addLayout(row)

        self.stack = QStackedWidget()
        self.list = TrackListWidget()
        self.list.play_requested.connect(self._on_play)
        self.list.menu_requested.connect(self._on_menu)
        self.list.favorite_clicked.connect(self._on_favorite)
        self.list.remove_requested.connect(lambda _tracks: None)
        self.stack.addWidget(self.list)

        self._album_scroll = QScrollArea()
        self._album_scroll.setWidgetResizable(True)
        self._album_scroll.setFrameShape(QScrollArea.NoFrame)
        self._album_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._album_scroll.viewport().setAutoFillBackground(False)
        self._album_scroll.setStyleSheet("background:transparent;")
        holder = QWidget()
        holder.setStyleSheet("background:transparent;")
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 8, 0, 20)
        self._album_grid = CardGrid()
        holder_layout.addWidget(self._album_grid)
        holder_layout.addStretch(1)
        self._album_scroll.setWidget(holder)
        self.stack.addWidget(self._album_scroll)
        layout.addWidget(self.stack, 1)

        ctx().library.library_changed.connect(self._refresh)
        ctx().library.favorites_changed.connect(self._apply_favorites)

    # ------------------------------------------------------------------ load
    def on_show(self, payload: object = None) -> None:
        artist_id = payload if isinstance(payload, str) else ""
        if artist_id:
            self._load(artist_id)

    def _load(self, artist_id: str) -> None:
        artist = None
        try:
            for candidate in ctx().library.artists():
                if candidate.id == artist_id:
                    artist = candidate
                    break
        except Exception:  # noqa: BLE001
            artist = None
        self._artist = artist
        self.segments.set_current(0, emit=False)
        self.stack.setCurrentIndex(0)
        if artist is None:
            self.list.set_tracks([])
            return
        self.hero.set_cover_track(_artist_cover_item(artist))
        self._refresh()

    def _refresh(self) -> None:
        artist = self._artist
        if artist is None:
            return
        self._tracks = ctx().library.artist_tracks(artist.id)
        self.list.set_tracks(self._tracks)
        self.list.set_empty_text("没有找到歌曲", "")
        albums = ctx().library.artist_albums(artist.id)
        cards = []
        for album in albums:
            card = AlbumCard(album, size=156)
            card.activated.connect(self._open_album)
            cards.append(card)
        self._album_grid.set_cards(cards)
        total = sum(track.duration_ms for track in self._tracks)
        meta_parts = [f"{len(self._tracks)} 首歌曲", f"{len(albums)} 张专辑"]
        if total:
            meta_parts.append(format_duration(total))
        self.hero.set_text(
            artist.name or "未知艺术家",
            "艺术家",
            " · ".join(meta_parts),
        )
        self._apply_favorites()

    def _apply_favorites(self) -> None:
        self.list.set_favorites({track.id for track in self._tracks if track.favorite})

    # ----------------------------------------------------------------- events
    def _go_back(self) -> None:
        window = ctx().window
        if window is not None:
            window.go_back()

    def _play(self, *, shuffle: bool = False) -> None:
        if not self._tracks:
            return
        player = ctx().player
        if shuffle:
            player.set_shuffle(True)
        name = self._artist.name if self._artist is not None else "艺术家"
        player.play_tracks(self._tracks, 0, context=f"艺术家 · {name}")

    def _on_play(self, tracks: list, index: int) -> None:
        name = self._artist.name if self._artist is not None else "艺术家"
        ctx().player.play_tracks(tracks, index, context=f"艺术家 · {name}")

    def _on_menu(self, tracks: list, position) -> None:
        if not tracks:
            return
        menu = track_menu(self, tracks, on_play=lambda items: self._on_play(items, 0))
        menu.exec(position)

    def _on_favorite(self, track) -> None:
        value = ctx().library.toggle_favorite(track)
        self._apply_favorites()
        window = ctx().window
        if window is not None:
            window.toast("已添加到「我喜欢」" if value else "已从「我喜欢」移除", "success" if value else "info")

    def _open_album(self, album) -> None:
        window = ctx().window
        if window is not None and album is not None:
            window.navigate("album", album.id)

    def _hero_menu(self) -> None:
        if self._artist is None:
            return
        menu = QMenu(self)
        menu.addAction("播放全部歌曲", lambda: self._play())
        menu.addAction("随机播放", lambda: self._play(shuffle=True))
        menu.exec(self.hero.more_button.mapToGlobal(self.hero.more_button.rect().bottomLeft()))

    def _on_segment(self, index: int) -> None:
        self.stack.setCurrentIndex(1 if index == 1 else 0)

    def refresh_theme(self) -> None:
        self.hero.refresh_theme()
        self.list.refresh_theme()
        self.segments.update()


def _artist_cover_item(artist):
    from ...model.track import Track

    if artist.artwork_path:
        return Track(id=f"artist-cover:{artist.id}", title=artist.name, path="", artwork_path=artist.artwork_path)
    if artist.cover_track_id:
        track = ctx().library.track(artist.cover_track_id)
        if track is not None:
            return track
    return Track(id=f"artist-cover:{artist.id}", title=artist.name, path="")
