"""Approved Browse CoverCard reused by the UI V2 landing sections."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
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
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from app.ui_v2.widgets.track_display import display_track_text


class CoverCardPlayButton(QToolButton):
    """Paint a complete circular play surface without native button chrome."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setAccessibleName("播放")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        colors = self._theme.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        circle = self.rect().adjusted(0, 0, -1, -1)
        if not self.isEnabled():
            background = QColor(colors.surface_secondary)
            foreground = QColor(colors.disabled_text)
        elif self.isDown():
            background = QColor(colors.accent_pressed)
            foreground = QColor(colors.app_background)
        elif self.underMouse():
            background = QColor(colors.accent_hover)
            foreground = QColor(colors.app_background)
        else:
            background = QColor(colors.accent)
            foreground = QColor(colors.app_background)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(circle)

        triangle = QPainterPath()
        left = circle.left() + circle.width() * 0.39
        top = circle.top() + circle.height() * 0.29
        triangle.moveTo(left, top)
        triangle.lineTo(circle.left() + circle.width() * 0.70, circle.center().y())
        triangle.lineTo(left, circle.top() + circle.height() * 0.71)
        triangle.closeSubpath()
        painter.setBrush(foreground)
        painter.drawPath(triangle)

        if self.hasFocus():
            focus_pen = QPen(QColor(colors.focus_ring), 1.0)
            focus_pen.setCosmetic(True)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle.adjusted(1, 1, -1, -1))
        painter.end()


class CoverCard(QFrame):
    """A compact artwork/title/meta card with one shared hover-play treatment."""

    activated = Signal(object)
    play_requested = Signal(object)
    context_menu_requested = Signal(object, object)

    COVER_WIDTH = 164
    COVER_HEIGHT = 164
    PLAY_BUTTON_SIZE = 36
    PLAY_BUTTON_INSET = 10

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._track: Track | None = None
        self._interactive = True
        self.setObjectName("coverCard")
        self.setFixedWidth(self.COVER_WIDTH)
        self.setFixedHeight(210)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_menu)

        self.artwork = QLabel(self)
        self.artwork.setObjectName("coverCardArtwork")
        self.artwork.setFixedSize(self.COVER_WIDTH, self.COVER_HEIGHT)
        self.artwork.setScaledContents(False)
        self._artwork_effect = QGraphicsOpacityEffect(self.artwork)
        self._artwork_effect.setOpacity(1.0)
        self.artwork.setGraphicsEffect(self._artwork_effect)
        self.play_button = CoverCardPlayButton(theme, self)
        self.play_button.setObjectName("coverCardPlay")
        self.play_button.setFixedSize(self.PLAY_BUTTON_SIZE, self.PLAY_BUTTON_SIZE)
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
            f"QToolButton#coverCardPlay {{ border: 0; background: transparent; padding: 0; margin: 0 {self.PLAY_BUTTON_INSET}px {self.PLAY_BUTTON_INSET}px 0; }}"
        )
        self.play_button.setIcon(icon("play", theme, "disabled" if not self._interactive else "normal"))
        self.play_button.setIconSize(QSize(16, 16))
        self.play_button.set_theme(theme)
        self._refresh_artwork()

    def set_track(self, track: Track) -> None:
        self._track = track
        title, artist, album = display_track_text(track)
        title = title or "未命名歌曲"
        meta = artist or album or "未知艺术家"
        if track.is_online:
            meta = f"在线 · {meta}"
        self.title_label.set_full_text(title)
        self.meta_label.set_full_text(meta)
        source = str(track.source_name or track.source_id or "在线来源").strip()
        tooltip = f"{title} · {meta}"
        if track.is_online:
            tooltip += f"\n来源：{source}"
        self.setToolTip(tooltip)
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
            artwork_pixmap_for_track(self._track, self.COVER_WIDTH, self.COVER_HEIGHT)
        )

    def _emit_play_requested(self) -> None:
        if self._interactive and self._track is not None:
            self.play_requested.emit(self._track)

    def _emit_context_menu(self, position) -> None:
        if self._track is not None:
            self.context_menu_requested.emit(
                self._track,
                self.mapToGlobal(position),
            )
