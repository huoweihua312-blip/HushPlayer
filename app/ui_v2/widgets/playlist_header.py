"""Compact Playlist Hero and action row for the second UI V2 stage."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.models.playlist import Playlist
from app.ui_v2.models.track import Track
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.artwork_thumbnail import ArtworkThumbnail
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.quiet_context_menu import apply_menu_theme


class PlaylistHeader(QWidget):
    """A compact 160px Playlist Hero with inline, mode-aware actions."""

    play_requested = Signal()
    shuffle_requested = Signal()
    favorite_requested = Signal(bool)
    more_requested = Signal()
    rename_requested = Signal()
    delete_requested = Signal()
    add_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._read_only = False
        self._playback_enabled = True
        self._favorite = False
        self._playlist: Playlist | None = None
        self._tracks: tuple[Track, ...] = ()
        self.setObjectName("playlistHero")

        self.artwork = ArtworkThumbnail(theme, self, size=160)
        self.artwork.setObjectName("playlistHeroArtwork")
        self.eyebrow_label = QLabel("歌单", self)
        self.eyebrow_label.setObjectName("playlistHeroEyebrow")
        self.title_label = ElidedLabel(self)
        self.title_label.setObjectName("playlistHeroTitle")
        self.owner_label = QLabel(self)
        self.owner_label.setObjectName("playlistHeroOwner")
        self.description_label = QLabel(self)
        self.description_label.setObjectName("playlistHeroDescription")
        self.description_label.setWordWrap(True)
        self.description_label.setMaximumHeight(40)
        self.meta_label = QLabel(self)
        self.meta_label.setObjectName("playlistHeroMeta")

        self.play_button = QToolButton(self)
        self.play_button.setObjectName("playlistHeroPlay")
        self.play_button.setText("播放")
        self.play_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.play_button.clicked.connect(self.play_requested)
        self.shuffle_button = QToolButton(self)
        self.shuffle_button.setObjectName("playlistHeroShuffle")
        self.shuffle_button.setText("随机播放")
        self.shuffle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.shuffle_button.clicked.connect(self.shuffle_requested)
        self.favorite_button = QToolButton(self)
        self.favorite_button.setObjectName("playlistHeroFavorite")
        self.favorite_button.setText("收藏")
        self.favorite_button.setCheckable(True)
        self.favorite_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.favorite_button.toggled.connect(self.favorite_requested)
        self.more_button = QToolButton(self)
        self.more_button.setObjectName("playlistHeroMore")
        self.more_button.setText("")
        self.more_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.more_button.setFixedSize(32, 32)
        self.more_button.setToolTip("更多")
        self.more_button.clicked.connect(self.more_requested)
        # Keep the small public handles used by existing page code and tests.
        self.add_button = QToolButton(self)
        self.rename_button = QToolButton(self)
        self.delete_button = QToolButton(self)
        self.add_button.clicked.connect(self.add_requested)
        self.rename_button.clicked.connect(self.rename_requested)
        self.delete_button.clicked.connect(self.delete_requested)

        self._more_menu = apply_menu_theme(QMenu(self), theme)
        add_action = self._more_menu.addAction("添加歌曲")
        rename_action = self._more_menu.addAction("重命名")
        self._more_menu.addSeparator()
        delete_action = self._more_menu.addAction("删除歌单")
        add_action.triggered.connect(self.add_requested)
        rename_action.triggered.connect(self.rename_requested)
        delete_action.triggered.connect(self.delete_requested)
        self.more_button.clicked.connect(self._show_more_menu)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.play_button)
        actions.addWidget(self.shuffle_button)
        actions.addWidget(self.favorite_button)
        actions.addWidget(self.more_button)
        actions.addStretch(1)

        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(4)
        details.addWidget(self.eyebrow_label)
        details.addWidget(self.title_label)
        details.addWidget(self.owner_label)
        details.addWidget(self.description_label)
        details.addWidget(self.meta_label)
        details.addSpacing(8)
        details.addLayout(actions)
        details.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(details, 1)
        self.set_theme(theme)
        self.set_playlist(None, ())

    def set_read_only(self, value: bool) -> None:
        self._read_only = bool(value)
        self.favorite_button.setVisible(not self._read_only)
        self.favorite_button.setEnabled(not self._read_only)
        self.favorite_button.setToolTip(
            "只读模式不可修改歌单收藏" if self._read_only else "收藏歌单"
        )
        self.more_button.setVisible(not self._read_only)
        self.more_button.setEnabled(not self._read_only)
        self.add_button.setVisible(False)
        self.rename_button.setVisible(False)
        self.delete_button.setVisible(False)

    def set_playback_enabled(self, value: bool) -> None:
        self._playback_enabled = bool(value)
        self.play_button.setEnabled(self._playback_enabled and bool(self._tracks))
        self.shuffle_button.setEnabled(self._playback_enabled and bool(self._tracks))
        if self._playback_enabled:
            self.play_button.setToolTip("播放歌单")
            self.shuffle_button.setToolTip("随机播放歌单")
        else:
            self.play_button.setToolTip("真实模式尚未接入播放")
            self.shuffle_button.setToolTip("真实模式尚未接入播放")

    def set_playlist(self, playlist: Playlist | None, tracks: Iterable[Track] = ()) -> None:
        self._playlist = playlist
        self._tracks = tuple(tracks)
        if playlist is None:
            self.artwork.set_track(None)
            self.eyebrow_label.setText("歌单")
            self.title_label.set_full_text("歌单不存在")
            self.owner_label.setText("HushPlayer")
            self.description_label.setText("尚未选择内容")
            self.meta_label.setText("0 首歌曲")
        else:
            representative = next((track for track in self._tracks if not track.is_missing), None)
            self.artwork.set_track(representative)
            self.eyebrow_label.setText("歌单")
            self.title_label.set_full_text(playlist.name)
            self.owner_label.setText("创建者 · HushPlayer")
            description = playlist.description or "本地音乐收藏"
            if any(marker in description.casefold() for marker in ("mock", "demo", "preview", "fixture")):
                description = "本地音乐收藏"
            self.description_label.setText(description)
            self.description_label.setToolTip(description)
            total_ms = sum(track.duration_ms or 0 for track in self._tracks)
            minutes, seconds = divmod(total_ms // 1000, 60)
            metadata = [f"{len(self._tracks)} 首歌曲", f"{minutes}:{seconds:02d}"]
            created = self._safe_date(playlist.created_at)
            if created:
                metadata.append(f"创建于 {created}")
            self.meta_label.setText("  ·  ".join(metadata))
        self.set_playback_enabled(self._playback_enabled)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        metrics = theme.metrics
        colors = theme.colors
        self.artwork.set_theme(theme)
        apply_menu_theme(self._more_menu, theme)
        self.eyebrow_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; font-weight: 600; color: {colors.accent};"
        )
        self.title_label.setStyleSheet(
            f"font-size: {theme.fonts.page_title}px; font-weight: 600; color: {colors.primary_text};"
        )
        self.owner_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {colors.primary_text};"
        )
        self.description_label.setStyleSheet(
            f"font-size: {theme.fonts.secondary}px; color: {colors.secondary_text};"
        )
        self.meta_label.setStyleSheet(
            f"font-size: {theme.fonts.caption}px; color: {colors.secondary_text};"
        )
        self.play_button.setIcon(icon("play", theme, "selected"))
        self.shuffle_button.setIcon(icon("shuffle", theme, "normal"))
        self.favorite_button.setIcon(icon("favorite_filled" if self._favorite else "favorite", theme, "selected" if self._favorite else "normal"))
        self.more_button.setIcon(icon("more", theme, "normal"))
        for button in (self.play_button, self.shuffle_button, self.favorite_button):
            button.setIconSize(QSize(theme.metrics.icon_sm, theme.metrics.icon_sm))
        self.more_button.setIconSize(QSize(theme.metrics.icon_sm, theme.metrics.icon_sm))
        self.play_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
            f"border: 0; border-radius: {metrics.radius_sm}px; color: {colors.content_background}; "
            f"background: {colors.accent}; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {colors.accent_hover}; }}"
            f"QToolButton:disabled {{ color: {colors.disabled_text}; background: {colors.surface_secondary}; }}"
        )
        for button in (self.shuffle_button, self.favorite_button):
            button.setStyleSheet(
                f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_md}px; "
                f"border: 1px solid {colors.border}; border-radius: {metrics.radius_sm}px; color: {colors.primary_text}; "
                f"background: {colors.surface_secondary}; }}"
                f"QToolButton:hover {{ background: {colors.hover_background}; border-color: {colors.border_strong}; }}"
                f"QToolButton:checked {{ color: {colors.accent}; background: {colors.selected_background}; }}"
                f"QToolButton:disabled {{ color: {colors.disabled_text}; background: transparent; border-color: {colors.border}; }}"
            )
        self.more_button.setStyleSheet(
            f"QToolButton {{ min-height: {metrics.control_height}px; padding: 0 {metrics.spacing_sm}px; border: 0; "
            f"border-radius: {metrics.radius_sm}px; color: {colors.secondary_text}; }}"
            f"QToolButton:hover {{ color: {colors.primary_text}; background: {colors.hover_background}; }}"
        )

    def set_responsive_reference_width(self, width: int) -> None:
        compact = int(width) < 950
        size = 132 if compact else 160
        self.artwork.setFixedSize(size, size)
        self.description_label.setMaximumHeight(34 if compact else 40)
        self.shuffle_button.setText("" if compact else "随机播放")
        self.shuffle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.shuffle_button.setToolTip("随机播放")
        self.favorite_button.setText("" if compact else "收藏")
        self.favorite_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.favorite_button.setToolTip("收藏歌单")
        self.more_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.more_button.setToolTip("更多")

    @staticmethod
    def _safe_date(value) -> str:
        if value is None or value.year <= 1970:
            return ""
        return value.strftime("%Y-%m-%d")

    def _show_more_menu(self) -> None:
        if not self._read_only:
            self._more_menu.popup(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))
