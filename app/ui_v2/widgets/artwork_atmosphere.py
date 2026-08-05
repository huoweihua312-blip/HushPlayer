"""Deterministic artwork-derived visuals used by the formal immersive page."""

from __future__ import annotations

from hashlib import sha256

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.ui_v2.models.track import Track
from app.ui_v2.theme.tokens import Theme


def _color(value: str, alpha: int = 255) -> QColor:
    color = QColor(value)
    color.setAlpha(max(0, min(255, alpha)))
    return color


def _mix(first: str, second: str, amount: float) -> QColor:
    left, right = QColor(first), QColor(second)
    value = max(0.0, min(1.0, amount))
    return QColor(
        round(left.red() + (right.red() - left.red()) * value),
        round(left.green() + (right.green() - left.green()) * value),
        round(left.blue() + (right.blue() - left.blue()) * value),
    )


class ArtworkPalette:
    """Small immutable-looking palette generated from the current mock track."""

    def __init__(self, key: str = "hushplayer") -> None:
        digest = sha256(key.encode("utf-8")).digest()
        hue = digest[0] % 360
        secondary = (hue + 42 + digest[1] % 60) % 360
        tertiary = (hue + 180 + digest[2] % 60) % 360
        self.colors = tuple(
            QColor.fromHsv(value, 118 + digest[index + 3] % 78, 118 + digest[index + 6] % 92).name()
            for index, value in enumerate((hue, secondary, tertiary))
        )
        self.accent = QColor.fromHsv(hue, 104, 246).name()


class AbstractArtwork(QWidget):
    """A text-free abstract cover that shares its palette with the backdrop."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._palette = ArtworkPalette()
        self.setObjectName("immersiveArtwork")
        self.setToolTip("当前歌曲封面")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    @property
    def palette_key(self) -> str:
        return self._palette.colors[0]

    def set_track(self, track: Track | None) -> None:
        key = track.stable_identity if track is not None else "hushplayer"
        self._palette = ArtworkPalette(key)
        self.setToolTip(track.title if track is not None else "当前歌曲封面")
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        colors = self._palette.colors
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(colors[0]))
        gradient.setColorAt(0.5, QColor(colors[1]))
        gradient.setColorAt(1.0, QColor(colors[2]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 10, 10)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 10, 10)
        painter.save()
        painter.setClipPath(clip)
        for center, radius, color, alpha in (
            (QPointF(rect.left() + rect.width() * 0.24, rect.top() + rect.height() * 0.22), rect.width() * 0.46, colors[0], 155),
            (QPointF(rect.left() + rect.width() * 0.80, rect.top() + rect.height() * 0.72), rect.width() * 0.58, colors[2], 144),
        ):
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.0, _color(color, alpha))
            glow.setColorAt(1.0, _color(color, 0))
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))
        painter.setPen(QPen(_color("#edf6ff", 150), max(1.1, rect.width() * 0.007)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect.adjusted(rect.width() * 0.13, rect.height() * 0.13, -rect.width() * 0.18, -rect.height() * 0.17), 28 * 16, 246 * 16)
        painter.drawLine(rect.left() + rect.width() * 0.13, rect.bottom() - rect.height() * 0.2, rect.right() - rect.width() * 0.14, rect.top() + rect.height() * 0.29)
        painter.restore()


class ArtworkAtmosphere(QWidget):
    """Full-bleed artwork field with only broad, boundary-free protection."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._palette = ArtworkPalette()
        self._mode = "artwork"
        # Keep the artwork-derived field atmospheric rather than turning the
        # whole shell into a saturated cover.  Foreground identity and lyrics
        # remain the visual focus at the approved default.
        self._opacity = 42
        self._overlay_strength = 52
        self.setObjectName("immersiveArtworkAtmosphere")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def generation(self) -> int:
        """Compatibility marker: palette changes, not ordinary resizes, refresh it."""
        return self._generation

    @property
    def _cache(self) -> ArtworkPalette:
        return self._palette

    _generation = 0

    def set_track(self, track: Track | None) -> None:
        key = track.stable_identity if track is not None else "hushplayer"
        self._palette = ArtworkPalette(key)
        self._generation += 1
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in {"artwork", "gradient", "solid", "transparent"} else "artwork"
        self.update()

    def set_opacity(self, value: int) -> None:
        self._opacity = max(0, min(100, int(value)))
        self.update()

    def set_overlay_strength(self, value: int) -> None:
        self._overlay_strength = max(15, min(85, int(value)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = self._palette.colors
        if self._mode == "transparent":
            painter.fillRect(
                self.rect(),
                _color(
                    "#101923" if self._theme.mode == "dark" else "#edf4f6",
                    round(12 * self._opacity / 100),
                ),
            )
        elif self._mode == "solid":
            painter.fillRect(self.rect(), _mix(colors[0], "#15212d" if self._theme.mode == "dark" else "#e9f3f7", 0.42))
        else:
            base_left = "#111b28" if self._theme.mode == "dark" else "#e8f4f6"
            base_right = "#1c2b38" if self._theme.mode == "dark" else "#f5ece8"
            field = QLinearGradient(0, 0, self.width(), self.height())
            field.setColorAt(0.0, _mix(base_left, colors[0], 0.40 if self._mode == "artwork" else 0.30))
            field.setColorAt(0.53, _mix(base_right, colors[1], 0.34 if self._mode == "artwork" else 0.26))
            field.setColorAt(1.0, _mix(base_left, colors[2], 0.30 if self._mode == "artwork" else 0.22))
            painter.fillRect(self.rect(), field)
        alpha_factor = self._opacity / 100
        for center, radius, color, alpha in (
            (QPointF(self.width() * 0.14, self.height() * 0.19), self.width() * 0.48, colors[0], 88),
            (QPointF(self.width() * 0.79, self.height() * 0.25), self.width() * 0.56, colors[1], 78),
            (QPointF(self.width() * 0.55, self.height() * 0.93), self.width() * 0.54, colors[2], 64),
        ):
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.0, _color(color, round(alpha * alpha_factor)))
            glow.setColorAt(0.58, _color(color, round(alpha * 0.24 * alpha_factor)))
            glow.setColorAt(1.0, _color(color, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))


class ReadabilityOverlay(QWidget):
    """Boundary-free protection limited to lyrics, identity and controls.

    The artwork field remains responsible for atmosphere.  This sibling only
    adds a small amount of contrast where text is actually painted, so a
    transparent background never turns into a page-wide dark veil.
    """

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._strength = 45
        self._identity_rect = QRect()
        self._lyrics_rect = QRect()
        self._controls_rect = QRect()
        self.setObjectName("immersiveReadabilityOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    @property
    def strength(self) -> int:
        return self._strength

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_strength(self, value: int) -> None:
        self._strength = max(15, min(85, int(value)))
        self.update()

    def set_regions(self, identity: QRect, lyrics: QRect, controls: QRect) -> None:
        if (identity, lyrics, controls) == (self._identity_rect, self._lyrics_rect, self._controls_rect):
            return
        self._identity_rect = QRect(identity)
        self._lyrics_rect = QRect(lyrics)
        self._controls_rect = QRect(controls)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._lyrics_rect.isNull() and self._identity_rect.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        surface = "#09121c" if self._theme.mode == "dark" else "#fffaf3"
        strength = self._strength / 100
        self._paint_region(painter, self._lyrics_rect, surface, round(22 + 74 * strength), 1.22)
        self._paint_region(painter, self._identity_rect, surface, round(14 + 42 * strength), 1.12)
        if not self._controls_rect.isNull():
            # Controls can now sit in the left identity column rather than at
            # the page bottom.  Use the same feathered treatment as text so
            # the group never reads as a dark rectangular control card.
            self._paint_region(
                painter,
                self._controls_rect,
                surface,
                round(12 + 28 * strength),
                1.04,
            )

    @staticmethod
    def _paint_region(painter: QPainter, rect: QRect, surface: str, alpha: int, expansion: float) -> None:
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        area = QRectF(rect)
        radius = max(area.width(), area.height()) * expansion * 0.72
        center = area.center()
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, _color(surface, alpha))
        gradient.setColorAt(0.58, _color(surface, round(alpha * 0.38)))
        gradient.setColorAt(1.0, _color(surface, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))
