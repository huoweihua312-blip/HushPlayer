"""Approved Browse CoverCard reused by the UI V2 landing sections."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.models.track import Track
from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.placeholder_cover import cover_pixmap
from app.ui_v2.widgets.track_display import display_track_text


class CoverCard(QFrame):
    """A compact artwork/title/meta card with one shared hover-play treatment."""

    activated = Signal(object)
    play_requested = Signal(object)

    COVER_WIDTH = 164
    COVER_HEIGHT = 164

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._track: Track | None = None
        self._interactive = True
        self.setObjectName("coverCard")
        self.setFixedWidth(self.COVER_WIDTH)
        self.setFixedHeight(210)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.artwork = QLabel(self)
        self.artwork.setObjectName("coverCardArtwork")
        self.artwork.setFixedSize(self.COVER_WIDTH, self.COVER_HEIGHT)
        self.artwork.setScaledContents(False)
        self._artwork_effect = QGraphicsOpacityEffect(self.artwork)
        self._artwork_effect.setOpacity(1.0)
        self.artwork.setGraphicsEffect(self._artwork_effect)
        self.play_button = QToolButton(self)
        self.play_button.setObjectName("coverCardPlay")
        self.play_button.setFixedSize(34, 34)
        self.play_button.setToolTip("播放")
        self.play_button.clicked.connect(self._emit_play_requested)

        artwork_host = QWidget(self)
        artwork_layout = QGridLayout(artwork_host)
        artwork_layout.setContentsMargins(0, 0, 0, 0)
        artwork_layout.addWidget(self.artwork, 0, 0)
        artwork_layout.addWidget(
            self.play_button,
            0,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )

        self.title_label = ElidedLabel(self)
        self.title_label.setObjectName("coverCardTitle")
        self.title_label.setWordWrap(False)
        self.meta_label = ElidedLabel(self)
        self.meta_label.setObjectName("coverCardMeta")
        self.meta_label.setWordWrap(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(artwork_host)
        layout.addSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        self.set_theme(theme)

    @property
    def track(self) -> Track | None:
        return self._track

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        c = theme.colors
        self.setStyleSheet(
            f"QFrame#coverCard {{ background: transparent; border: 0; }}"
            f"QLabel#coverCardArtwork {{ border: 0; border-radius: {theme.metrics.radius_lg}px; background: {c.surface_secondary}; }}"
            f"QLabel#coverCardTitle {{ color: {c.text_primary}; font-size: {theme.fonts.card_title}px; font-weight: 600; line-height: 18px; }}"
            f"QLabel#coverCardMeta {{ color: {c.text_secondary}; font-size: {theme.fonts.card_meta}px; line-height: 17px; }}"
            f"QToolButton#coverCardPlay {{ border: 0; border-radius: 17px; background: {c.surface_elevated}; color: {c.app_background}; margin: 0 8px 8px 0; }}"
            f"QToolButton#coverCardPlay:hover {{ background: {c.text_primary}; }}"
            f"QToolButton#coverCardPlay:disabled {{ background: {c.surface_secondary}; color: {c.text_disabled}; }}"
        )
        self.play_button.setIcon(icon("play", theme, "disabled" if not self._interactive else "normal"))
        self.play_button.setIconSize(QSize(15, 15))
        self._refresh_artwork()

    def set_track(self, track: Track) -> None:
        self._track = track
        title, artist, album = display_track_text(track)
        title = title or "未命名歌曲"
        meta = artist or album or "未知艺术家"
        self.title_label.set_full_text(title)
        self.meta_label.set_full_text(meta)
        self.setToolTip(f"{title} · {meta}")
        self._refresh_artwork()

    def set_interactive(self, enabled: bool, tooltip: str = "") -> None:
        self._interactive = bool(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self._interactive else Qt.CursorShape.ArrowCursor
        )
        self.play_button.setEnabled(self._interactive)
        if tooltip:
            self.play_button.setToolTip(tooltip)
        elif self._interactive:
            self.play_button.setToolTip("播放")
        self.play_button.setVisible(False)
        self.set_theme(self._theme)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.play_button.setVisible(self._interactive)
        self._artwork_effect.setOpacity(0.7 if self._interactive else 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.play_button.hide()
        self._artwork_effect.setOpacity(1.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            self._interactive
            and self._track is not None
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.activated.emit(self._track)
        super().mouseReleaseEvent(event)

    def _refresh_artwork(self) -> None:
        if self._track is None:
            self.artwork.clear()
            return
        self.artwork.setPixmap(
            cover_pixmap(self._track.stable_id, self.COVER_WIDTH, self.COVER_HEIGHT)
        )

    def _emit_play_requested(self) -> None:
        if self._interactive and self._track is not None:
            self.play_requested.emit(self._track)
