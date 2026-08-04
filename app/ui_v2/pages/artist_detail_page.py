"""Artist detail page built from the shared collection and TrackTable stack."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.adapters.albums_adapter import AlbumsAdapter
from app.ui_v2.adapters.artists_adapter import ArtistsAdapter
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.track_list_adapter import TrackListAdapter
from app.ui_v2.models.artist import Artist, ArtistAggregate
from app.ui_v2.models.track import Track
from app.ui_v2.theme.styles import build_stylesheet
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artist_album_card import ArtistAlbumCard
from app.ui_v2.widgets.artist_hero import ArtistHero
from app.ui_v2.widgets.empty_state import EmptyState
from app.ui_v2.widgets.track_table import TrackTable
from app.ui_v2.widgets.track_display import display_track_text


_FALLBACK_ARTISTS = ("林岸", "岑野", "北川", "Kite Harbor", "Nova Vale", "Mira Lane")
_FORBIDDEN_MARKERS = ("mock", "demo", "fixture", "preview")


def _formal_artist_name(artist: Artist | None, tracks: tuple[Track, ...]) -> str:
    if artist is None:
        return "未知艺人"
    name = str(artist.name or "").strip()
    if name in {"未知歌手", "未知艺术家", "未知艺人"}:
        return "未知艺人"
    if name and not any(marker in name.casefold() for marker in _FORBIDDEN_MARKERS):
        return name
    representative = next((track for track in tracks if not track.is_missing), None)
    if representative is not None:
        mapped = display_track_text(representative)[1]
        if mapped and not any(marker in mapped.casefold() for marker in _FORBIDDEN_MARKERS):
            return mapped
    digest = hashlib.sha256((artist.id or name).encode("utf-8")).digest()
    return _FALLBACK_ARTISTS[digest[0] % len(_FALLBACK_ARTISTS)]


def _formal_album_title(album_title: str, representative: Track | None) -> str:
    title = str(album_title or "").strip()
    if title and not any(marker in title.casefold() for marker in _FORBIDDEN_MARKERS):
        return title
    if representative is not None:
        mapped = display_track_text(representative)[2]
        if mapped:
            return mapped
    return "未知专辑"


class ArtistDetailPage(QWidget):
    """A cached Artist surface with one view-local filtered TrackListAdapter."""

    track_play_requested = Signal(object, str)
    queue_requested = Signal(object, bool)
    browse_library_requested = Signal()
    artist_requested = Signal(str)
    album_requested = Signal(str)

    def __init__(
        self,
        collection: LibraryCollectionAdapter,
        artists: ArtistsAdapter,
        albums: AlbumsAdapter,
        theme: Theme,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.collection = collection
        self.artists = artists
        self.albums = albums
        self._theme = theme
        self._artist_id = ""
        self._artist: Artist | None = None
        self.artist_aggregate = ArtistAggregate(None, (), (), 0, 0, 0)
        self._artist_tracks: tuple[Track, ...] = ()
        self._popular_track_ids: frozenset[str] = frozenset()
        self._popular_display_limit = 4
        self._album_cards: list[ArtistAlbumCard] = []
        self._content_safe_bottom = 0
        self.current_view_state = "content"
        self.setObjectName("artistDetailPage")

        self.back_button = QToolButton(self)
        self.back_button.setText("返回歌手")
        self.back_button.setObjectName("artistBackButton")
        self.back_button.setVisible(False)

        self.hero = ArtistHero(theme, self)
        self.hero.action_row.play_requested.connect(lambda: self._request_queue(False))
        self.hero.action_row.shuffle_requested.connect(lambda: self._request_queue(True))
        self.hero.action_row.more_requested.connect(self._show_more_menu)

        self.info_rail = QFrame(self)
        self.info_rail.setObjectName("artistInfoRail")
        self.info_title = QLabel("关于艺人", self.info_rail)
        self.info_body = QLabel(self.info_rail)
        self.info_body.setWordWrap(True)
        info_layout = QVBoxLayout(self.info_rail)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(8)
        info_layout.addWidget(self.info_title)
        info_layout.addWidget(self.info_body)
        info_layout.addStretch(1)
        self.info_rail.setFixedWidth(0)
        self.info_rail.setVisible(False)

        hero_row = QWidget(self)
        self.hero_row = hero_row
        hero_layout = QHBoxLayout(hero_row)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(24)
        hero_layout.addWidget(self.hero, 1)
        hero_layout.addWidget(self.info_rail, 0, Qt.AlignmentFlag.AlignVCenter)

        self.popular_section = QWidget(self)
        popular_layout = QVBoxLayout(self.popular_section)
        popular_layout.setContentsMargins(0, 0, 0, 0)
        popular_layout.setSpacing(8)
        popular_header = QHBoxLayout()
        popular_header.setContentsMargins(0, 0, 0, 0)
        self.popular_title = QLabel("热门歌曲", self.popular_section)
        self.popular_count = QLabel(self.popular_section)
        self.popular_count.setObjectName("artistSectionMeta")
        popular_header.addWidget(self.popular_title)
        popular_header.addWidget(self.popular_count)
        popular_header.addStretch(1)
        popular_layout.addLayout(popular_header)

        self.adapter = TrackListAdapter(
            collection,
            self,
            predicate=lambda track: track.id in self._popular_track_ids,
        )
        self.track_table = TrackTable(self.adapter, theme, self)
        self.track_table.set_artist_navigation_enabled(True)
        self.track_table.artist_requested.connect(self.artist_requested)
        self.track_table.play_requested.connect(self._request_track)
        self.adapter.tracks_reset.connect(self._on_tracks_reset)
        popular_layout.addWidget(self.track_table)
        self.popular_empty_state = EmptyState(self.popular_section)
        self.popular_empty_state.empty_icon_name = "artist"
        self.popular_empty_state.set_theme(theme)
        self.popular_empty_state.setVisible(False)
        popular_layout.addWidget(self.popular_empty_state)

        self.albums_section = QWidget(self)
        albums_layout = QVBoxLayout(self.albums_section)
        albums_layout.setContentsMargins(0, 8, 0, 0)
        albums_layout.setSpacing(8)
        albums_header = QHBoxLayout()
        albums_header.setContentsMargins(0, 0, 0, 0)
        self.albums_title = QLabel("专辑", self.albums_section)
        self.albums_count = QLabel(self.albums_section)
        self.albums_count.setObjectName("artistSectionMeta")
        albums_header.addWidget(self.albums_title)
        albums_header.addWidget(self.albums_count)
        albums_header.addStretch(1)
        albums_layout.addLayout(albums_header)
        self.album_row = QHBoxLayout()
        self.album_row.setContentsMargins(0, 0, 0, 0)
        self.album_row.setSpacing(16)
        self.album_row.addStretch(1)
        albums_layout.addLayout(self.album_row)

        self.empty_state = EmptyState(self)
        self.empty_state.empty_icon_name = "artist"
        self.empty_state.set_theme(theme)
        self.empty_state.setVisible(False)

        content = QWidget(self)
        content.setObjectName("artistContent")
        self.content_layout = QVBoxLayout(content)
        metrics = theme.metrics
        self.content_layout.setContentsMargins(
            metrics.page_margin,
            metrics.spacing_lg,
            metrics.page_margin,
            metrics.page_margin,
        )
        self.content_layout.setSpacing(metrics.spacing_lg)
        self.content_layout.addWidget(self.back_button)
        self.content_layout.addWidget(hero_row)
        self.content_layout.addWidget(self.popular_section)
        self.content_layout.addWidget(self.albums_section)
        self.content_layout.addWidget(self.empty_state)
        self.content_layout.addStretch(1)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("artistScrollArea")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)

        self.artists.artists_reset.connect(lambda _items: self._refresh_artist())
        self.albums.albums_reset.connect(lambda _items: self._refresh_artist())
        self.set_theme(theme)
        self._refresh_artist()

    @property
    def artist_id(self) -> str:
        return self._artist_id

    @property
    def artist(self) -> Artist | None:
        return self._artist

    def set_artist(self, artist_id: str) -> None:
        self._artist_id = str(artist_id or "")
        self._refresh_artist()

    def set_content_safe_bottom(self, height: int) -> None:
        self._content_safe_bottom = max(0, int(height))
        margins = self.content_layout.contentsMargins()
        self.content_layout.setContentsMargins(
            margins.left(), margins.top(), margins.right(),
            self._theme.metrics.page_margin + self._content_safe_bottom,
        )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(build_stylesheet(theme) + self._page_styles(theme))
        self.hero.set_theme(theme)
        self.empty_state.set_theme(theme)
        self.popular_empty_state.set_theme(theme)
        self.track_table.set_theme(theme)
        self.popular_title.setStyleSheet(self._section_title_style(theme))
        self.albums_title.setStyleSheet(self._section_title_style(theme))
        self.popular_count.setStyleSheet(self._section_meta_style(theme))
        self.albums_count.setStyleSheet(self._section_meta_style(theme))
        self.info_title.setStyleSheet(self._section_title_style(theme))
        self.info_body.setStyleSheet(self._section_meta_style(theme))
        for card in self._album_cards:
            card.set_theme(theme)

    def set_responsive_reference_width(self, width: int) -> None:
        reference = int(width)
        top_level = self.window()
        if top_level is not None:
            reference = max(reference, int(top_level.width()))
        compact = reference < 950
        self.hero.set_compact(compact)
        self.track_table.set_responsive_reference_width(reference)
        self._popular_display_limit = (
            4 if reference < 950 else 5 if reference < 1450 else 6
        )
        self.track_table.set_visible_row_limit(self._popular_display_limit)
        self._update_info_rail_visibility(reference)
        card_size = 124 if compact else 154 if reference >= 1450 else 144
        for card in self._album_cards:
            card.set_cover_size(card_size)
        self._update_track_table_height()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.set_responsive_reference_width(self.width())

    def _refresh_artist(self) -> None:
        artist = self.artists.artist_for_id(self._artist_id)
        self._artist = artist
        if artist is None:
            self.artist_aggregate = ArtistAggregate(None, (), (), 0, 0, 0)
            self._artist_tracks = ()
            self._popular_track_ids = frozenset()
            self.adapter.set_predicate(lambda _track: False)
            self.hero.set_aggregate(self.artist_aggregate, "找不到这个艺人")
            self.hero_row.setVisible(False)
            self._set_empty("找不到这个艺人", "该艺人可能已从音乐库中移除。")
            self.popular_section.setVisible(False)
            self.albums_section.setVisible(False)
            self._set_info_rail("")
            self._clear_album_cards()
            return

        tracks = tuple(self.artists.tracks_for_artist(artist.id))
        artist_albums = tuple(
            album
            for album_id in artist.album_ids
            if (album := self.albums.album_for_id(album_id)) is not None
        )
        aggregate = ArtistAggregate(
            artist=artist,
            tracks=tracks,
            albums=artist_albums,
            track_count=len(tracks),
            album_count=len(artist_albums),
            total_duration_ms=sum(track.duration_ms or 0 for track in tracks),
            metadata=self._artist_metadata(artist),
            exists=True,
        )
        self.artist_aggregate = aggregate
        self._artist_tracks = aggregate.tracks
        self._popular_track_ids = frozenset(track.id for track in aggregate.tracks[:10])
        self.adapter.set_predicate(lambda track: track.id in self._popular_track_ids)
        display_name = _formal_artist_name(artist, self._artist_tracks)
        self.hero.set_aggregate(aggregate, display_name)
        self._populate_albums(aggregate.albums)
        self.hero_row.setVisible(aggregate.exists)
        self.popular_section.setVisible(True)
        self.track_table.setVisible(bool(aggregate.track_count))
        self.popular_empty_state.setVisible(not aggregate.track_count)
        if not aggregate.track_count:
            self._set_popular_empty(
                "没有可显示的歌曲",
                "音乐库中暂时没有这个艺人的歌曲。",
            )
        self.albums_section.setVisible(bool(aggregate.album_count))
        self.empty_state.setVisible(False)
        self._set_info_rail("\n".join(aggregate.metadata.values()))
        self._apply_action_state(aggregate)
        self.set_responsive_reference_width(self.width())

    @staticmethod
    def _artist_metadata(artist: Artist) -> dict[str, str]:
        """Read optional, non-repeating metadata without inventing content."""

        raw = getattr(artist, "metadata", {}) or {}
        values: dict[str, str] = {}
        if isinstance(raw, Mapping):
            for key in ("biography", "description", "genre"):
                value = str(raw.get(key) or "").strip()
                if value and not any(marker in value.casefold() for marker in _FORBIDDEN_MARKERS):
                    values[key] = value
        for key in ("biography", "description", "genre"):
            value = str(getattr(artist, key, "") or "").strip()
            if (
                value
                and key not in values
                and not any(marker in value.casefold() for marker in _FORBIDDEN_MARKERS)
            ):
                values[key] = value
        return values

    def _set_info_rail(self, body: str) -> None:
        text = str(body or "").strip()
        self.info_body.setText(text)
        has_content = bool(text)
        self.info_rail.setFixedWidth(260 if has_content else 0)
        self.info_rail.setVisible(has_content and self.width() >= 1450)

    def _update_info_rail_visibility(self, reference: int) -> None:
        has_content = bool(self.info_body.text().strip())
        self.info_rail.setFixedWidth(260 if has_content else 0)
        self.info_rail.setVisible(has_content and int(reference) >= 1450 and self._artist is not None)

    def _set_popular_empty(self, title: str, detail: str) -> None:
        self.popular_empty_state.title_label.setText(title)
        self.popular_empty_state.detail_label.setText(detail)
        self.popular_empty_state.set_theme(self._theme)

    def _apply_action_state(self, aggregate: ArtistAggregate) -> None:
        enabled = bool(aggregate.track_count) and not self.collection.read_only
        if not aggregate.track_count:
            tooltip = "没有可播放的歌曲"
        elif self.collection.read_only:
            tooltip = "真实模式尚未接入播放"
        else:
            tooltip = ""
        self.hero.action_row.set_playback_enabled(enabled, tooltip)

    def _populate_albums(self, albums: tuple[object, ...]) -> None:
        self._clear_album_cards()
        for album in albums[:7]:
            representative = next(
                (track for track in self.albums.tracks_for_album(album.id) if not track.is_missing),
                None,
            )
            safe_album = album
            safe_title = _formal_album_title(album.title, representative)
            if safe_title != album.title:
                from dataclasses import replace

                safe_album = replace(album, title=safe_title)
            card = ArtistAlbumCard(safe_album, representative, self._theme, self)
            card.activated.connect(self.album_requested)
            self._album_cards.append(card)
            self.album_row.insertWidget(self.album_row.count() - 1, card)
        self.albums_count.setText(f"{len(self._album_cards)} 张")

    def _clear_album_cards(self) -> None:
        # Remove the layout items first and hide/detach every old card before
        # scheduling deletion.  ``deleteLater`` alone leaves a QWidget visible
        # until the deferred event is processed, which can overlap a newly
        # populated row during Artist refreshes and state transitions.
        while self.album_row.count() > 1:
            item = self.album_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._album_cards.clear()
        self.albums_count.setText("")

    def _set_empty(self, title: str, detail: str) -> None:
        self.empty_state.empty_icon_name = "artist"
        self.empty_state.title_label.setText(title)
        self.empty_state.detail_label.setText(detail)
        self.empty_state.setVisible(True)
        self.empty_state.set_theme(self._theme)

    def _update_track_table_height(self) -> None:
        rows = min(self._popular_display_limit, max(0, self.adapter.tracks().__len__()))
        self.track_table.setMinimumHeight(36 + rows * 48 + 8)
        self.track_table.setMaximumHeight(36 + rows * 48 + 8 if rows else 120)

    def _on_tracks_reset(self, tracks) -> None:
        self.popular_count.setText(f"{len(tracks)} 首")
        self._update_track_table_height()
        has_tracks = bool(tracks)
        self.track_table.setVisible(has_tracks)
        self.popular_empty_state.setVisible(
            not has_tracks and self.artist_aggregate.exists
        )
        self._apply_action_state(self.artist_aggregate)

    def _request_track(self, track_id: str) -> None:
        self.track_play_requested.emit(self.adapter.tracks(), track_id)

    def _request_queue(self, shuffle: bool) -> None:
        tracks = tuple(track for track in self.adapter.tracks() if not track.is_missing)
        if tracks:
            self.queue_requested.emit(tracks, shuffle)

    def _show_more_menu(self) -> None:
        menu = QMenu(self)
        action = menu.addAction("复制艺人名称")
        action.triggered.connect(lambda: self._copy_artist_name())
        menu.exec(self.hero.action_row.more_button.mapToGlobal(self.hero.action_row.more_button.rect().bottomLeft()))

    def _copy_artist_name(self) -> None:
        from PySide6.QtWidgets import QApplication

        if self._artist is not None:
            QApplication.clipboard().setText(_formal_artist_name(self._artist, self._artist_tracks))

    @staticmethod
    def _section_title_style(theme: Theme) -> str:
        return f"font-size: {theme.fonts.section_title}px; font-weight: 600; color: {theme.colors.primary_text};"

    @staticmethod
    def _section_meta_style(theme: Theme) -> str:
        return f"font-size: {theme.fonts.caption}px; color: {theme.colors.secondary_text};"

    @staticmethod
    def _page_styles(theme: Theme) -> str:
        c = theme.colors
        return (
            f"QScrollArea#artistScrollArea {{ border: 0; background: {c.content_background}; }}"
            f"QWidget#artistContent {{ background: {c.content_background}; }}"
            f"QFrame#artistInfoRail {{ border-left: 1px solid {c.divider}; background: {c.surface_primary}; }}"
            f"QLabel#artistHeroArtwork {{ border-radius: {theme.metrics.radius_lg}px; }}"
        )
