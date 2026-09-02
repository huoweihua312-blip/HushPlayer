"""Standalone immersive-lyrics visual experiment.

This module deliberately stays outside the formal V2 shell.  Its layers are
kept separate so background transparency never changes the alpha of lyrics,
artwork, track information, or controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPalette,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui_v2.theme.icons import icon
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.models.track import Track, format_duration
from app.ui_v2.widgets.elided_label import ElidedLabel
from app.ui_v2.widgets.playback_button import PlaybackButton

if TYPE_CHECKING:
    from app.ui_v2.adapters.playback_adapter import PlaybackAdapter


@dataclass(frozen=True, slots=True)
class MockArtwork:
    key: str
    label: str
    first: str
    second: str
    third: str


MOCK_ARTWORKS = (
    MockArtwork("cool", "冷色夜航", "#2c6877", "#172a4a", "#6d9bb2"),
    MockArtwork("warm", "暖色余温", "#8c573a", "#472b3d", "#d08b55"),
    MockArtwork("muted", "低饱和雾面", "#5e6d73", "#3c424d", "#92988e"),
)


@dataclass(frozen=True, slots=True)
class PreviewLine:
    text: str
    translation: str
    romanization: str
    segments: tuple[str, ...]


CHINESE_LINES = (
    PreviewLine("夜色把城市放得很轻", "The night holds the city softly", "Ye se ba cheng shi fang de hen qing", ("夜色", "把城市", "放得", "很轻")),
    PreviewLine("远处的灯沿着风移动", "Distant lights move with the wind", "Yuan chu de deng yan zhe feng yi dong", ("远处", "的灯", "沿着", "风移动")),
    PreviewLine("我们在安静里交换呼吸", "We trade our breathing in the quiet", "Wo men zai an jing li jiao huan hu xi", ("我们", "在安静里", "交换", "呼吸")),
    PreviewLine("让这一刻慢慢发亮", "Let this moment begin to glow", "Rang zhe yi ke man man fa liang", ("让", "这一刻", "慢慢", "发亮")),
    PreviewLine("不必回答明天的方向", "Tomorrow does not need an answer", "Bu bi hui da ming tian de fang xiang", ("不必", "回答", "明天", "的方向")),
    PreviewLine("只听见心跳靠近海岸", "Only a heartbeat nearing the shore", "Zhi ting jian xin tiao kao jin hai an", ("只听见", "心跳", "靠近", "海岸")),
    PreviewLine("潮汐替我们保留回声", "The tide keeps an echo for us", "Chao xi ti wo men bao liu hui sheng", ("潮汐", "替我们", "保留", "回声")),
)

ENGLISH_LINES = (
    PreviewLine("A quiet blue is falling over town", "一抹安静的蓝落在城里", "Yi mo an jing de lan luo zai cheng li", ("A", "quiet", "blue", "is falling", "over town")),
    PreviewLine("The windows carry pieces of the sky", "窗户带着天空的碎片", "Chuang hu dai zhe tian kong de sui pian", ("The", "windows", "carry", "pieces", "of the sky")),
    PreviewLine("We leave our names inside the sound", "我们把名字留在声音里", "Wo men ba ming zi liu zai sheng yin li", ("We", "leave", "our names", "inside", "the sound")),
    PreviewLine("And let the distance open wide", "让距离慢慢打开", "Rang ju li man man da kai", ("And", "let", "the distance", "open", "wide")),
    PreviewLine("No map can tell us where to turn", "没有地图能告诉我们转向哪里", "Mei you di tu neng gao su wo men zhuan xiang na li", ("No", "map", "can tell us", "where", "to turn")),
    PreviewLine("The afterglow is still returning", "余晖仍在回来", "Yu hui reng zai hui lai", ("The", "afterglow", "is still", "returning")),
    PreviewLine("A softer morning waits ahead", "更柔软的清晨在前方", "Geng rou ruan de qing chen zai qian fang", ("A", "softer", "morning", "waits", "ahead")),
)


def _color(value: str, alpha: int | None = None) -> QColor:
    result = QColor(value)
    if alpha is not None:
        result.setAlpha(max(0, min(255, int(alpha))))
    return result


def _rgba(value: str, alpha: int) -> str:
    color = QColor(value)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(0, min(255, int(alpha)))})"


def _blend(first: QColor, second: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, float(ratio)))
    return QColor(
        round(first.red() * (1 - ratio) + second.red() * ratio),
        round(first.green() * (1 - ratio) + second.green() * ratio),
        round(first.blue() * (1 - ratio) + second.blue() * ratio),
    )


def artwork_for_key(key: str) -> MockArtwork:
    return next((item for item in MOCK_ARTWORKS if item.key == key), MOCK_ARTWORKS[0])


def artwork_for_track(track: Track | None) -> MockArtwork:
    """Choose one deterministic mock artwork without reading a real cover file."""
    if track is None:
        return MOCK_ARTWORKS[0]
    return MOCK_ARTWORKS[sum(ord(character) for character in track.id) % len(MOCK_ARTWORKS)]


def artwork_palette(artwork: MockArtwork, theme: Theme) -> tuple[QColor, QColor, QColor, QColor]:
    first = _color(artwork.first)
    second = _color(artwork.second)
    third = _color(artwork.third)
    if theme.mode == "dark":
        first = first.darker(125)
        second = second.darker(115)
        third = third.darker(118)
    else:
        first = first.lighter(128)
        second = second.lighter(122)
        third = third.lighter(116)
    accent = _blend(_color(theme.colors.accent), first, 0.36)
    return first, second, third, accent


class BackgroundLayer(QWidget):
    """Owns only the artwork/gradient surface and its own alpha."""

    MODES = ("artwork", "gradient", "solid", "transparent")

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._artwork = MOCK_ARTWORKS[0]
        self._cache = QImage()
        self._generation = 0
        self._mode = "artwork"
        self._opacity_percent = 55
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._regenerate_cache()

    @property
    def artwork_key(self) -> str:
        return self._artwork.key

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def opacity_percent(self) -> int:
        return self._opacity_percent

    @property
    def surface_alpha(self) -> int:
        return round(255 * self._opacity_percent / 100) if self._mode == "transparent" else 255

    def set_theme(self, theme: Theme) -> None:
        if theme == self._theme:
            return
        self._theme = theme
        self._regenerate_cache()
        self.update()

    def set_artwork(self, artwork: MockArtwork) -> None:
        if artwork.key == self._artwork.key:
            return
        self._artwork = artwork
        self._regenerate_cache()
        self.update()

    def set_mode(self, mode: str) -> None:
        value = mode if mode in self.MODES else "artwork"
        if value != self._mode:
            self._mode = value
            self.update()

    def set_opacity_percent(self, value: int) -> None:
        opacity = max(0, min(100, int(value)))
        if opacity != self._opacity_percent:
            self._opacity_percent = opacity
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        first, second, third, _accent = artwork_palette(self._artwork, self._theme)
        if self._mode == "solid":
            painter.fillRect(self.rect(), _color(self._theme.colors.content_background))
            return
        if self._mode == "gradient":
            gradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0.0, first)
            gradient.setColorAt(0.52, second)
            gradient.setColorAt(1.0, third)
            painter.fillRect(self.rect(), gradient)
            return
        if self._mode == "transparent":
            painter.setOpacity(self._opacity_percent / 100.0)
        painter.drawImage(self.rect(), self._cache)

    def _regenerate_cache(self) -> None:
        self._generation += 1
        first, second, third, _accent = artwork_palette(self._artwork, self._theme)
        self._cache = QImage(160, 90, QImage.Format.Format_ARGB32_Premultiplied)
        self._cache.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self._cache)
        gradient = QLinearGradient(0, 0, self._cache.width(), self._cache.height())
        gradient.setColorAt(0.0, first)
        gradient.setColorAt(0.5, second)
        gradient.setColorAt(1.0, third)
        painter.fillRect(self._cache.rect(), gradient)
        painter.setOpacity(0.24)
        painter.fillRect(QRect(0, 0, 75, 90), first.lighter(112))
        painter.fillRect(QRect(88, 8, 72, 68), second.lighter(110))
        painter.end()


class ReadabilityOverlay(QWidget):
    """A full-window low-contrast overlay, never a parent of content."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._strength = 45 if theme.mode == "dark" else 25
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def strength(self) -> int:
        return self._strength

    @property
    def alpha(self) -> int:
        return round(255 * self._strength / 100)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_strength(self, value: int) -> None:
        self._strength = max(0, min(90, int(value)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        alpha = self.alpha
        if not alpha:
            return
        tone = "#0b1119" if self._theme.mode == "dark" else "#f2f6fb"
        gradient = QLinearGradient(0, 0, 0, max(1, self.height()))
        gradient.setColorAt(0.0, _color(tone, round(alpha * 0.72)))
        gradient.setColorAt(0.58, _color(tone, alpha))
        gradient.setColorAt(1.0, _color(tone, round(alpha * 0.88)))
        painter.fillRect(self.rect(), gradient)


class LyricsReadabilityProtection(QWidget):
    """Soft local protection behind lyrics without introducing a card edge."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._enabled = True
        self._strength = 58
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def strength(self) -> int:
        return self._strength

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.update()

    def set_strength(self, value: int) -> None:
        self._strength = max(0, min(100, int(value)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._enabled or self._strength == 0:
            return
        painter = QPainter(self)
        tone = "#071018" if self._theme.mode == "dark" else "#f6f9fc"
        base_alpha = round(190 * self._strength / 100)
        horizontal = QLinearGradient(0, 0, max(1, self.width()), 0)
        horizontal.setColorAt(0.0, _color(tone, 0))
        horizontal.setColorAt(0.18, _color(tone, round(base_alpha * 0.44)))
        horizontal.setColorAt(0.72, _color(tone, round(base_alpha * 0.54)))
        horizontal.setColorAt(1.0, _color(tone, 0))
        painter.fillRect(self.rect(), horizontal)
        spotlight = QRadialGradient(
            self.width() * 0.44,
            self.height() * 0.46,
            max(self.width() * 0.64, self.height() * 0.48),
        )
        spotlight.setColorAt(0.0, _color(tone, round(base_alpha * 0.52)))
        spotlight.setColorAt(0.52, _color(tone, round(base_alpha * 0.22)))
        spotlight.setColorAt(1.0, _color(tone, 0))
        painter.fillRect(self.rect(), spotlight)


class PreviewArtwork(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._artwork = MOCK_ARTWORKS[0]
        self.setMinimumSize(112, 112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_artwork(self, artwork: MockArtwork) -> None:
        self._artwork = artwork
        self.setToolTip(f"mock artwork: {artwork.label}")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        first, second, third, accent = artwork_palette(self._artwork, self._theme)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, first)
        gradient.setColorAt(0.55, second)
        gradient.setColorAt(1.0, third)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, self._theme.metrics.radius_lg, self._theme.metrics.radius_lg)
        painter.setPen(_color(accent.name(), 120))
        painter.drawLine(rect.left() + rect.width() * 0.12, rect.bottom() - rect.height() * 0.2, rect.right() - rect.width() * 0.12, rect.top() + rect.height() * 0.2)
        painter.setPen(_color(self._theme.colors.primary_text, 255))
        font = QFont(self.font())
        font.setPointSize(max(12, round(self.width() * 0.08)))
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "MOCK")


class PreviewTrackInfo(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._cover_scale = 100
        self.artwork = PreviewArtwork(theme, self)
        self.title_label = ElidedLabel(self)
        self.artist_label = ElidedLabel(self)
        self.source_label = ElidedLabel(self)
        self.detail_label = QLabel("Mock visual / 02:18", self)
        self.detail_label.setWordWrap(False)
        details = QWidget(self)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(5)
        details_layout.addWidget(self.title_label)
        details_layout.addWidget(self.artist_label)
        details_layout.addWidget(self.source_label)
        details_layout.addSpacing(4)
        details_layout.addWidget(self.detail_label)
        self._layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(18)
        self._layout.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignLeft)
        self._layout.addWidget(details)
        self.set_theme(theme)
        self.set_artwork(MOCK_ARTWORKS[0])

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.artwork.set_theme(theme)
        self.title_label.setStyleSheet(f"font-size: {theme.fonts.page_title + 4}px; font-weight: 600; color: {theme.colors.primary_text};")
        self.artist_label.setStyleSheet(f"font-size: {theme.fonts.section_title}px; color: {theme.colors.secondary_text};")
        self.source_label.setStyleSheet(f"font-size: {theme.fonts.secondary}px; color: {theme.colors.secondary_text};")
        self.detail_label.setStyleSheet(f"font-size: {theme.fonts.caption}px; color: {theme.colors.subtle_text};")

    def set_artwork(self, artwork: MockArtwork) -> None:
        self.artwork.set_artwork(artwork)
        self.title_label.set_full_text("夜航之后，海岸仍有回声 / After the Night Tide")
        self.artist_label.set_full_text("HushPlayer Studio · Visual Draft")
        self.source_label.set_full_text(artwork.label)

    def set_track(self, track: Track | None, document: LyricsDocument | None) -> None:
        """Refresh only text and mock-artwork identity for a shared V2 track."""
        self.set_artwork(artwork_for_track(track))
        if track is None:
            self.title_label.set_full_text("未选择歌曲")
            self.artist_label.set_full_text("请选择一首歌曲开始播放")
            self.source_label.set_full_text("歌词来源: --")
            self.detail_label.setText("Mock visual / --:--")
            return
        self.title_label.set_full_text(document.title if document is not None else track.title)
        self.artist_label.set_full_text(document.artist if document is not None else track.artist)
        source = document.source_type if document is not None else track.source_name
        self.source_label.set_full_text(source or track.album)
        self.detail_label.setText(f"{track.album} / {format_duration(track.duration_ms)}")

    def set_cover_scale(self, value: int) -> None:
        self._cover_scale = max(70, min(130, int(value)))

    def set_responsive(self, width: int) -> None:
        compact = width < 1100
        self._layout.setDirection(QBoxLayout.Direction.LeftToRight if compact else QBoxLayout.Direction.TopToBottom)
        self._layout.setSpacing(14 if compact else 18)
        if width < 900:
            extent = 170
        elif width < 1100:
            extent = 220
        elif width < 1400:
            extent = max(280, min(340, round(width * 0.27)))
        else:
            extent = min(410, max(340, round(width * 0.29)))
        extent = max(140, min(460, round(extent * self._cover_scale / 100)))
        self.artwork.setFixedSize(extent, extent)
        self.setMaximumWidth(1_6777_215 if compact else max(300, round(width * 0.34)))
        self.setMaximumHeight(220 if compact else 1_6777_215)


class PreviewLyricsCanvas(QWidget):
    """One self-painted, fully opaque lyric surface for all lines and segments."""

    WEIGHTS = {
        "Normal": QFont.Weight.Normal,
        "Medium": QFont.Weight.Medium,
        "Semibold": QFont.Weight.DemiBold,
        "Bold": QFont.Weight.Bold,
    }
    PROTECTION_MODES = ("无", "轻微阴影", "描边", "描边 + 阴影")

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._artwork = MOCK_ARTWORKS[0]
        self._language = "中文"
        self._show_translation = True
        self._show_romanization = False
        self._document: LyricsDocument | None = None
        self._current_index = 3
        self._active_segment_index = 1
        self._segment_progress = 0.58
        self._responsive_scale = 1.0
        self._global_scale = 100
        self._max_line_width = 780
        self._active_font_size = 46
        self._inactive_font_size = 30
        self._translation_font_size = 14
        self._romanization_font_size = 15
        self._weight_name = "Semibold"
        self._inactive_opacity = 68
        self._text_protection = "轻微阴影"
        self.setMinimumHeight(700)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

    @property
    def language(self) -> str:
        return self._language

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def text_alpha(self) -> int:
        return 255

    @property
    def document(self) -> LyricsDocument | None:
        return self._document

    @property
    def active_font_size(self) -> int:
        return self._active_font_size

    @property
    def inactive_font_size(self) -> int:
        return self._inactive_font_size

    @property
    def translation_font_size(self) -> int:
        return self._translation_font_size

    @property
    def romanization_font_size(self) -> int:
        return self._romanization_font_size

    @property
    def inactive_opacity(self) -> int:
        return self._inactive_opacity

    @property
    def text_protection(self) -> str:
        return self._text_protection

    @property
    def global_scale(self) -> int:
        return self._global_scale

    @property
    def effective_font_sizes(self) -> tuple[int, int, int, int]:
        return tuple(round(value * self._global_scale / 100) for value in (
            self._active_font_size,
            self._inactive_font_size,
            self._translation_font_size,
            self._romanization_font_size,
        ))

    def set_responsive_scale(self, value: float) -> None:
        self._responsive_scale = max(0.76, min(1.08, float(value)))
        self.update()

    def set_global_scale(self, value: int) -> None:
        self._global_scale = max(75, min(160, int(value)))
        self.update()

    def set_max_line_width(self, value: int) -> None:
        self._max_line_width = max(420, min(920, int(value)))
        self.update()

    def set_font_sizes(self, active: int, inactive: int, translation: int, romanization: int) -> None:
        self._active_font_size = max(32, min(72, int(active)))
        self._inactive_font_size = max(22, min(48, int(inactive)))
        self._translation_font_size = max(14, min(32, int(translation)))
        self._romanization_font_size = max(12, min(26, int(romanization)))
        self.update()

    def set_weight_name(self, value: str) -> None:
        self._weight_name = value if value in self.WEIGHTS else "Semibold"
        self.update()

    def set_inactive_opacity(self, value: int) -> None:
        self._inactive_opacity = max(25, min(100, int(value)))
        self.update()

    def set_text_protection(self, value: str) -> None:
        self._text_protection = value if value in self.PROTECTION_MODES else "无"
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_artwork(self, artwork: MockArtwork) -> None:
        self._artwork = artwork
        self.update()

    def set_document(self, document: LyricsDocument | None) -> None:
        if document is self._document:
            return
        self._document = document
        self._current_index = -1
        self._active_segment_index = -1
        self._segment_progress = 0.0
        self.update()

    def set_active_line(self, line: LyricLine | None) -> None:
        if line is None or self._document is None:
            next_index = -1
        else:
            next_index = next(
                (index for index, item in enumerate(self._document.lines) if item.id == line.id),
                -1,
            )
        if next_index != self._current_index:
            self._current_index = next_index
            self._active_segment_index = -1
            self._segment_progress = 0.0
            self.update()

    def set_active_segment(self, line: LyricLine, segment_index: int, progress: float) -> None:
        if self._document is None:
            return
        self.set_active_line(line)
        self._active_segment_index = max(-1, int(segment_index))
        self._segment_progress = max(0.0, min(1.0, float(progress)))
        self.update()

    def set_language(self, language: str) -> None:
        self._language = "英文" if language == "英文" else "中文"
        self.update()

    def set_translation_visible(self, visible: bool) -> None:
        self._show_translation = bool(visible)
        self.update()

    def set_romanization_visible(self, _visible: bool) -> None:
        self._show_romanization = False
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(720, 700)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        indexed_lines = self._visible_lines()
        _first, _second, _third, accent = artwork_palette(self._artwork, self._theme)
        max_width = min(self._max_line_width, max(260, self.width() - 40))
        x = max(20, (self.width() - max_width) // 2)
        y = max(30, round(38 * self._responsive_scale))
        active_size, inactive_size, translation_size, _romanization_size = self.effective_font_sizes
        spacing_scale = self._responsive_scale * self._global_scale / 100
        for index, line in indexed_lines:
            distance = index - self._current_index
            active = distance == 0
            main_font = QFont(self.font())
            requested = active_size if active else inactive_size
            lower = 28 if active else 19
            upper = 112 if active else 76
            main_font.setPointSize(max(lower, min(upper, round(requested * self._responsive_scale))))
            main_font.setWeight(self.WEIGHTS[self._weight_name])
            main_font = self._fit_font(main_font, line.text, max_width, lower)
            metrics = QFontMetrics(main_font)
            rect = QRect(x, y, max_width, metrics.height() + 10)
            if active:
                self._draw_segmented_line(painter, line, rect, main_font, accent)
            else:
                distance_factor = max(0.55, 1.0 - abs(distance) * 0.13)
                alpha = round(255 * self._inactive_opacity / 100 * distance_factor)
                self._draw_text(painter, rect, line.text, main_font, _color(self._theme.colors.primary_text, alpha))
            y += metrics.height() + max(10, round(18 * spacing_scale))
            if active and self._show_translation:
                sub_font = QFont(self.font())
                sub_font.setPointSize(max(12, min(52, round(translation_size * self._responsive_scale))))
                sub_font.setWeight(QFont.Weight.Medium)
                sub_metrics = QFontMetrics(sub_font)
                self._draw_text(painter, QRect(x, y, max_width, sub_metrics.height() + 6), line.translation, sub_font, _color(self._theme.colors.secondary_text, 255))
                y += sub_metrics.height() + max(3, round(4 * spacing_scale))
            y += max(8, round(14 * spacing_scale))

    def _visible_lines(self) -> tuple[tuple[int, PreviewLine | LyricLine], ...]:
        if self._document is None:
            lines = ENGLISH_LINES if self._language == "英文" else CHINESE_LINES
            return tuple(enumerate(lines))
        if not self._document.lines:
            return ()
        current = self._current_index if self._current_index >= 0 else 0
        start = max(0, current - 3)
        end = min(len(self._document.lines), current + 4)
        return tuple((index, self._document.lines[index]) for index in range(start, end))

    def _draw_segmented_line(self, painter: QPainter, line: PreviewLine | LyricLine, rect: QRect, font: QFont, accent: QColor) -> None:
        self._draw_text(painter, rect, line.text, font, _color(self._theme.colors.primary_text, 255))
        if isinstance(line, PreviewLine):
            separator = " " if self._language == "英文" else ""
            visible = separator.join(line.segments[:2])
            if len(line.segments) > 2:
                count = max(1, round(len(line.segments[2]) * self._segment_progress))
                visible += separator + line.segments[2][:count]
        else:
            if self._active_segment_index < 0:
                return
            completed = "".join(segment.text for segment in line.segments[: self._active_segment_index])
            active_segment = line.segments[self._active_segment_index] if self._active_segment_index < len(line.segments) else None
            if active_segment is None:
                visible = completed
            else:
                count = max(0, round(len(active_segment.text) * self._segment_progress))
                visible = completed + active_segment.text[:count]
        if not visible:
            return
        prefix_width = QFontMetrics(font).horizontalAdvance(visible) + 3
        accent_rect = QRect(rect.x(), rect.y(), min(prefix_width, rect.width()), rect.height())
        self._draw_text(painter, accent_rect, visible, font, _color(accent.name(), 255))

    @staticmethod
    def _fit_font(font: QFont, text: str, available_width: int, minimum: int) -> QFont:
        fitted = QFont(font)
        while fitted.pointSize() > minimum and QFontMetrics(fitted).horizontalAdvance(text) > available_width - 4:
            fitted.setPointSize(fitted.pointSize() - 1)
        return fitted

    def _draw_text(self, painter: QPainter, rect: QRect, text: str, font: QFont, color: QColor) -> None:
        painter.setFont(font)
        flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        shadow = _color("#071018" if self._theme.mode == "dark" else "#ffffff", 190)
        outline = _color("#03070c" if self._theme.mode == "dark" else "#ffffff", 205)
        if self._text_protection in {"轻微阴影", "描边 + 阴影"}:
            painter.setPen(shadow)
            painter.drawText(rect.translated(1, 2), flags, text)
        if self._text_protection in {"描边", "描边 + 阴影"}:
            painter.setPen(outline)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(rect.translated(dx, dy), flags, text)
        painter.setPen(color)
        painter.drawText(rect, flags, text)


class PreviewLyricsView(QScrollArea):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.canvas = PreviewLyricsCanvas(theme, self)
        self.setWidget(self.canvas)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.viewport().setAutoFillBackground(False)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self.canvas.set_theme(theme)
        self.setStyleSheet(
            "QScrollArea { border: 0; background: transparent; }"
            "QAbstractScrollArea::viewport { background: transparent; }"
            f"QScrollBar:vertical {{ width: 5px; margin: 12px 2px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ min-height: 26px; border-radius: 2px; background: {_rgba(theme.colors.border, 150)}; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {_rgba(theme.colors.border_strong, 190)}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def set_artwork(self, artwork: MockArtwork) -> None:
        self.canvas.set_artwork(artwork)

    def set_document(self, document: LyricsDocument | None) -> None:
        self.canvas.set_document(document)

    def set_active_line(self, line: LyricLine | None) -> None:
        self.canvas.set_active_line(line)

    def set_active_segment(self, line: LyricLine, segment_index: int, progress: float) -> None:
        self.canvas.set_active_segment(line, segment_index, progress)

    def set_language(self, language: str) -> None:
        self.canvas.set_language(language)

    def set_translation_visible(self, visible: bool) -> None:
        self.canvas.set_translation_visible(visible)

    def set_romanization_visible(self, _visible: bool) -> None:
        self.canvas.set_romanization_visible(False)


class PreviewControls(QFrame):
    more_requested = Signal()
    back_requested = Signal()
    interaction_changed = Signal(bool)

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._playing = True
        self._adapter: PlaybackAdapter | None = None
        self._seeking = False
        self._surface_opacity = 35
        self.setObjectName("floatingControls")
        self.back_button = QToolButton(self)
        self.back_button.setText("返回")
        self.back_button.setToolTip("返回视觉预览")
        self.previous_button = PlaybackButton("previous", "上一首", theme, self)
        self.play_button = PlaybackButton("pause", "暂停预览", theme, self, primary=True)
        self.next_button = PlaybackButton("next", "下一首", theme, self)
        self.current_label = QLabel("2:18", self)
        self.total_label = QLabel("4:02", self)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setValue(57)
        self.volume_button = PlaybackButton("volume", "音量", theme, self)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(72)
        self.more_button = QToolButton(self)
        self.more_button.setToolTip("打开沉浸歌词设置")
        self.more_button.setIcon(icon("settings", theme))
        self.back_button.clicked.connect(self.back_requested)
        self.previous_button.clicked.connect(self._play_previous)
        self.play_button.clicked.connect(self._toggle_play)
        self.next_button.clicked.connect(self._play_next)
        self.progress_slider.sliderPressed.connect(self._begin_interaction)
        self.progress_slider.sliderReleased.connect(self._finish_seek)
        self.progress_slider.sliderMoved.connect(self._preview_seek)
        self.volume_slider.sliderPressed.connect(self._begin_interaction)
        self.volume_slider.sliderReleased.connect(self._end_interaction)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.volume_button.clicked.connect(self._toggle_mute)
        self.more_button.clicked.connect(self.more_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(7)
        layout.addWidget(self.back_button)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.play_button)
        layout.addWidget(self.next_button)
        layout.addSpacing(4)
        layout.addWidget(self.current_label)
        layout.addWidget(self.progress_slider, 1)
        layout.addWidget(self.total_label)
        layout.addSpacing(6)
        layout.addWidget(self.volume_button)
        layout.addWidget(self.volume_slider)
        layout.addWidget(self.more_button)
        self.set_theme(theme)

    @property
    def surface_opacity(self) -> int:
        return self._surface_opacity

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        alpha = round(255 * self._surface_opacity / 100)
        self.setStyleSheet(
            f"QFrame#floatingControls {{ background: {_rgba(theme.colors.elevated_background, alpha)}; border: 1px solid {_rgba(theme.colors.border, min(120, alpha + 30))}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QLabel {{ background: transparent; color: {theme.colors.secondary_text}; font-size: {theme.fonts.caption}px; }}"
            f"QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {_rgba(theme.colors.border_strong, 145)}; }}"
            f"QSlider::sub-page:horizontal {{ border-radius: 2px; background: {theme.colors.accent}; }}"
            f"QSlider::handle:horizontal {{ width: 10px; margin: -3px 0; border-radius: 5px; background: {theme.colors.primary_text}; }}"
        )
        for button in (self.previous_button, self.play_button, self.next_button, self.volume_button):
            button.set_theme(theme)
        for button in (self.back_button, self.more_button):
            button.setFixedSize(36, 36)
            button.setStyleSheet(
                f"QToolButton {{ border: 0; padding: 0; border-radius: 18px; background: transparent; color: {theme.colors.secondary_text}; }}"
                f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {_rgba(theme.colors.hover_background, 150)}; }}"
                f"QToolButton:pressed {{ background: {_rgba(theme.colors.selected_background, 170)}; }}"
            )
        self.back_button.setIcon(icon("previous", theme))
        self.more_button.setIcon(icon("settings", theme))
        self.back_button.setIconSize(QSize(17, 17))
        self.more_button.setIconSize(QSize(18, 18))

    def set_surface_opacity(self, value: int) -> None:
        self._surface_opacity = max(0, min(100, int(value)))
        self.set_theme(self._theme)

    def bind_playback(self, adapter: PlaybackAdapter) -> None:
        """Render one shared PlaybackAdapter without retaining a second state."""
        if adapter is self._adapter:
            return
        self._adapter = adapter
        adapter.track_changed.connect(self._on_track_changed)
        adapter.playing_changed.connect(self.set_playing)
        adapter.position_changed.connect(self._on_position_changed)
        adapter.duration_changed.connect(self._on_duration_changed)
        adapter.volume_changed.connect(self._on_volume_changed)
        state = adapter.state
        self._on_track_changed(state.current_track)
        self.set_playing(state.is_playing)
        self._on_duration_changed(state.duration_ms)
        self._on_position_changed(state.position_ms)
        self._on_volume_changed(state.volume)

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        self.play_button.set_icon_name("pause" if self._playing else "play")
        self.play_button.setToolTip("暂停" if self._playing else "播放")

    def set_compact(self, compact: bool) -> None:
        self.volume_slider.setVisible(not compact)
        self.current_label.setVisible(not compact)
        self.total_label.setVisible(not compact)
        self.back_button.setText("")

    def _toggle_play(self) -> None:
        if self._adapter is not None:
            self._adapter.toggle_playback()
            return
        self._playing = not self._playing
        self.set_playing(self._playing)

    def _play_previous(self) -> None:
        if self._adapter is not None:
            self._adapter.play_previous()

    def _play_next(self) -> None:
        if self._adapter is not None:
            self._adapter.play_next()

    def _begin_interaction(self) -> None:
        self._seeking = True
        self.interaction_changed.emit(True)

    def _end_interaction(self) -> None:
        self._seeking = False
        self.interaction_changed.emit(False)

    def _preview_seek(self, position_ms: int) -> None:
        self.current_label.setText(format_duration(position_ms))

    def _finish_seek(self) -> None:
        if self._adapter is not None:
            self._adapter.seek(self.progress_slider.value())
        self._end_interaction()

    def _set_volume(self, value: int) -> None:
        if self._adapter is not None:
            self._adapter.set_volume(value)

    def _toggle_mute(self) -> None:
        if self._adapter is not None:
            self._adapter.set_volume(0 if self._adapter.state.volume else 70)

    def _on_track_changed(self, track: Track | None) -> None:
        enabled = track is not None
        for control in (self.previous_button, self.play_button, self.next_button, self.progress_slider):
            control.setEnabled(enabled)

    def _on_duration_changed(self, duration_ms: int | None) -> None:
        duration = max(0, int(duration_ms or 0))
        blocker = QSignalBlocker(self.progress_slider)
        self.progress_slider.setRange(0, duration)
        del blocker
        self.total_label.setText(format_duration(duration_ms))
        self.progress_slider.setEnabled(self._adapter is not None and duration > 0)

    def _on_position_changed(self, position_ms: int) -> None:
        if self._seeking:
            return
        blocker = QSignalBlocker(self.progress_slider)
        self.progress_slider.setValue(max(0, int(position_ms)))
        del blocker
        self.current_label.setText(format_duration(position_ms))

    def _on_volume_changed(self, value: int) -> None:
        blocker = QSignalBlocker(self.volume_slider)
        self.volume_slider.setValue(max(0, min(100, int(value))))
        del blocker
        self.volume_button.set_icon_name("volume_mute" if value == 0 else "volume")


class SettingsPanel(QFrame):
    """Compact floating settings surface; all continuous values use sliders."""

    closed = Signal()
    theme_requested = Signal(str)
    background_mode_requested = Signal(str)
    background_opacity_changed = Signal(int)
    overlay_strength_changed = Signal(int)
    control_surface_opacity_changed = Signal(int)
    lyric_protection_changed = Signal(bool)
    lyric_protection_strength_changed = Signal(int)
    global_lyric_scale_changed = Signal(int)
    font_sizes_changed = Signal(int, int, int, int)
    weight_changed = Signal(str)
    inactive_opacity_changed = Signal(int)
    text_protection_changed = Signal(str)
    translation_changed = Signal(bool)
    cover_scale_changed = Signal(int)
    lyrics_width_changed = Signal(int)
    auto_hide_changed = Signal(bool)
    fullscreen_requested = Signal(bool)
    immersive_exit_requested = Signal()
    reset_lyric_sizes_requested = Signal()
    reset_all_requested = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._combos: list[QComboBox] = []
        self.setObjectName("immersivePreviewSettings")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.title_label = QLabel("沉浸歌词设置", self)
        self.close_button = QToolButton(self)
        self.close_button.setText("关闭")
        self.close_button.setToolTip("关闭设置")
        header = QHBoxLayout()
        header.setContentsMargins(16, 14, 12, 10)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.close_button)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(self.scroll)
        body.setObjectName("settingsBody")
        self.body = body
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(16, 4, 16, 18)
        self._body_layout.setSpacing(10)
        self._add_section("外观")
        self.theme_combo = self._add_combo("主题", (("深色", "dark"), ("浅色", "light")))
        self.background_combo = self._add_combo("背景模式", (("封面背景", "artwork"), ("渐变背景", "gradient"), ("纯色背景", "solid"), ("透明背景", "transparent")))
        self.background_opacity_slider = self._add_slider("背景透明度", 0, 100, 55, "%")
        self.overlay_strength_slider = self._add_slider("遮罩强度", 0, 90, 45, "%")
        self.control_surface_opacity_slider = self._add_slider("控制层透明度", 0, 100, 35, "%")
        self.lyric_protection_check = self._add_check("歌词背景保护", True)
        self.lyric_protection_strength_slider = self._add_slider("保护层强度", 0, 100, 58, "%")
        self._add_section("歌词")
        self.global_lyric_scale_slider = self._add_slider("整体歌词大小", 75, 160, 100, "%")
        self.inactive_opacity_slider = self._add_slider("非当前歌词透明度", 25, 100, 68, "%")
        self.weight_combo = self._add_combo("字重", tuple((value, value) for value in ("Normal", "Medium", "Semibold", "Bold")))
        self.text_protection_combo = self._add_combo("文字保护", tuple((value, value) for value in PreviewLyricsCanvas.PROTECTION_MODES))
        self.translation_check = self._add_check("显示翻译", True)
        self.advanced_sizes_toggle = QToolButton(self)
        self.advanced_sizes_toggle.setText("高级字号设置")
        self.advanced_sizes_toggle.setCheckable(True)
        self.advanced_sizes_toggle.setToolTip("展开或折叠单项字号设置")
        self._body_layout.addWidget(self.advanced_sizes_toggle)
        self.advanced_sizes_container = QWidget(self)
        self.advanced_sizes_container.setObjectName("advancedSizesContainer")
        self._advanced_sizes_layout = QVBoxLayout(self.advanced_sizes_container)
        self._advanced_sizes_layout.setContentsMargins(8, 2, 0, 4)
        self._advanced_sizes_layout.setSpacing(8)
        self.active_font_slider = self._add_slider("当前歌词字号", 32, 72, 46, "px", self._advanced_sizes_layout)
        self.inactive_font_slider = self._add_slider("普通歌词字号", 22, 48, 30, "px", self._advanced_sizes_layout)
        self.translation_font_slider = self._add_slider("翻译字号", 14, 32, 14, "px", self._advanced_sizes_layout)
        self._body_layout.addWidget(self.advanced_sizes_container)
        self.advanced_sizes_container.hide()
        reset_row = QHBoxLayout()
        reset_row.setContentsMargins(0, 0, 0, 0)
        self.reset_lyric_sizes_button = QToolButton(self)
        self.reset_lyric_sizes_button.setText("重置歌词大小")
        self.reset_all_button = QToolButton(self)
        self.reset_all_button.setText("重置全部沉浸设置")
        reset_row.addWidget(self.reset_lyric_sizes_button)
        reset_row.addWidget(self.reset_all_button)
        reset_row.addStretch(1)
        self._body_layout.addLayout(reset_row)
        self._add_section("布局")
        self.cover_scale_slider = self._add_slider("封面大小", 70, 130, 100, "%")
        self.lyrics_width_slider = self._add_slider("歌词最大宽度", 420, 920, 780, "px")
        self.auto_hide_check = self._add_check("自动隐藏控制层", True)
        self.fullscreen_check = self._add_check("全屏", False)
        self.exit_immersive_button = QToolButton(self)
        self.exit_immersive_button.setText("退出沉浸模式")
        self.exit_immersive_button.setToolTip("返回普通歌词")
        self._body_layout.addWidget(self.exit_immersive_button)
        self._body_layout.addStretch(1)
        self.scroll.setWidget(body)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self.scroll, 1)
        self.close_button.clicked.connect(self.closed)
        self.theme_combo.currentIndexChanged.connect(lambda _: self.theme_requested.emit(str(self.theme_combo.currentData())))
        self.background_combo.currentIndexChanged.connect(lambda _: self.background_mode_requested.emit(str(self.background_combo.currentData())))
        self.background_opacity_slider.valueChanged.connect(self.background_opacity_changed)
        self.overlay_strength_slider.valueChanged.connect(self.overlay_strength_changed)
        self.control_surface_opacity_slider.valueChanged.connect(self.control_surface_opacity_changed)
        self.lyric_protection_check.toggled.connect(self.lyric_protection_changed)
        self.lyric_protection_strength_slider.valueChanged.connect(self.lyric_protection_strength_changed)
        self.global_lyric_scale_slider.valueChanged.connect(self.global_lyric_scale_changed)
        for slider in (self.active_font_slider, self.inactive_font_slider, self.translation_font_slider):
            slider.valueChanged.connect(self._emit_font_sizes)
        self.weight_combo.currentIndexChanged.connect(lambda _: self.weight_changed.emit(str(self.weight_combo.currentData())))
        self.inactive_opacity_slider.valueChanged.connect(self.inactive_opacity_changed)
        self.text_protection_combo.currentIndexChanged.connect(lambda _: self.text_protection_changed.emit(str(self.text_protection_combo.currentData())))
        self.translation_check.toggled.connect(self.translation_changed)
        self.cover_scale_slider.valueChanged.connect(self.cover_scale_changed)
        self.lyrics_width_slider.valueChanged.connect(self.lyrics_width_changed)
        self.auto_hide_check.toggled.connect(self.auto_hide_changed)
        self.fullscreen_check.toggled.connect(self.fullscreen_requested)
        self.exit_immersive_button.clicked.connect(self.immersive_exit_requested)
        self.advanced_sizes_toggle.toggled.connect(self._set_advanced_sizes_visible)
        self.reset_lyric_sizes_button.clicked.connect(self.reset_lyric_sizes_requested)
        self.reset_all_button.clicked.connect(self.reset_all_requested)
        self.set_theme(theme)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.setStyleSheet(
            f"QFrame#immersivePreviewSettings {{ background: {_rgba(theme.colors.elevated_background, 225)}; border: 1px solid {_rgba(theme.colors.border, 150)}; border-radius: {theme.metrics.radius_lg}px; }}"
            f"QLabel {{ color: {theme.colors.secondary_text}; font-size: {theme.fonts.secondary}px; }}"
            f"QLabel#sectionLabel {{ color: {theme.colors.primary_text}; font-size: {theme.fonts.section_title}px; font-weight: 600; margin-top: 8px; }}"
            f"QComboBox {{ min-height: 28px; border: 1px solid {_rgba(theme.colors.border, 180)}; border-radius: {theme.metrics.radius_sm}px; padding: 0 8px; background: {_rgba(theme.colors.content_background, 130)}; color: {theme.colors.primary_text}; }}"
            f"QComboBox:hover {{ border-color: {_rgba(theme.colors.border_strong, 220)}; }}"
            f"QComboBox::drop-down {{ width: 24px; border: 0; background: transparent; }}"
            f"QCheckBox {{ color: {theme.colors.primary_text}; spacing: 8px; }}"
            f"QToolButton {{ border: 0; border-radius: {theme.metrics.radius_sm}px; padding: 4px 8px; color: {theme.colors.secondary_text}; background: transparent; }}"
            f"QToolButton:hover {{ color: {theme.colors.primary_text}; background: {_rgba(theme.colors.hover_background, 150)}; }}"
            f"QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {_rgba(theme.colors.border_strong, 150)}; }}"
            f"QSlider::sub-page:horizontal {{ background: {theme.colors.accent}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ width: 10px; margin: -3px 0; border-radius: 5px; background: {theme.colors.primary_text}; }}"
            "QScrollArea, QAbstractScrollArea::viewport, QWidget#settingsBody { background: transparent; border: 0; }"
        )
        self.title_label.setStyleSheet(f"color: {theme.colors.primary_text}; font-size: {theme.fonts.section_title}px; font-weight: 600;")
        for combo in self._combos:
            self._configure_combo_popup(combo)

    def set_values(self, preview: "ImmersiveLyricsPreview") -> None:
        self._set_combo_data(self.theme_combo, preview._theme.mode)
        self._set_combo_data(self.background_combo, preview.background_mode)
        self._set_slider(self.background_opacity_slider, preview.background_opacity_percent)
        self._set_slider(self.overlay_strength_slider, preview.overlay_strength)
        self._set_slider(self.control_surface_opacity_slider, preview.control_surface_opacity)
        self._set_check(self.lyric_protection_check, preview.lyric_protection.enabled)
        self._set_slider(self.lyric_protection_strength_slider, preview.lyric_protection.strength)
        canvas = preview.lyrics_view.canvas
        self._set_slider(self.global_lyric_scale_slider, canvas.global_scale)
        self._set_slider(self.active_font_slider, canvas.active_font_size)
        self._set_slider(self.inactive_font_slider, canvas.inactive_font_size)
        self._set_slider(self.translation_font_slider, canvas.translation_font_size)
        self._set_combo_data(self.weight_combo, canvas._weight_name)
        self._set_slider(self.inactive_opacity_slider, canvas.inactive_opacity)
        self._set_combo_data(self.text_protection_combo, canvas.text_protection)
        self._set_check(self.translation_check, preview._translation_visible)
        self._set_slider(self.cover_scale_slider, preview._cover_scale)
        self._set_slider(self.lyrics_width_slider, preview._lyrics_max_width)
        self._set_check(self.auto_hide_check, preview.auto_hide_controls)
        self._set_check(self.fullscreen_check, preview.is_fullscreen)

    def _add_section(self, title: str) -> None:
        label = QLabel(title, self)
        label.setObjectName("sectionLabel")
        self._body_layout.addWidget(label)

    def _add_combo(self, label_text: str, values: tuple[tuple[str, str], ...]) -> QComboBox:
        row = QWidget(self)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel(label_text, row))
        combo = QComboBox(row)
        for label, value in values:
            combo.addItem(label, value)
        self._combos.append(combo)
        self._configure_combo_popup(combo)
        layout.addWidget(combo)
        self._body_layout.addWidget(row)
        return combo

    def _add_slider(
        self,
        label_text: str,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str,
        target_layout: QVBoxLayout | None = None,
    ) -> QSlider:
        row = QWidget(self)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(QLabel(label_text, row))
        value_label = QLabel(row)
        value_label.setObjectName("valueLabel")
        title_row.addStretch(1)
        title_row.addWidget(value_label)
        layout.addLayout(title_row)
        slider = QSlider(Qt.Orientation.Horizontal, row)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setProperty("value_label", value_label)
        slider.setProperty("suffix", suffix)
        slider.valueChanged.connect(lambda current, label=value_label, unit=suffix: label.setText(f"{current}{unit}"))
        value_label.setText(f"{value}{suffix}")
        layout.addWidget(slider)
        (target_layout or self._body_layout).addWidget(row)
        return slider

    def _add_check(self, label_text: str, checked: bool) -> QCheckBox:
        check = QCheckBox(label_text, self)
        check.setChecked(checked)
        self._body_layout.addWidget(check)
        return check

    def _emit_font_sizes(self, value: int) -> None:
        self.font_sizes_changed.emit(
            self.active_font_slider.value(),
            self.inactive_font_slider.value(),
            self.translation_font_slider.value(),
            15,
        )

    def _set_advanced_sizes_visible(self, visible: bool) -> None:
        self.advanced_sizes_container.setVisible(visible)
        self.advanced_sizes_toggle.setText("收起高级字号设置" if visible else "高级字号设置")

    def close_open_popup(self) -> bool:
        for combo in self._combos:
            if combo.view().isVisible():
                combo.hidePopup()
                return True
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Show:
            for combo in self._combos:
                if watched is combo.view():
                    self._configure_combo_popup(combo)
                    break
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape and self.close_open_popup():
            return True
        return super().eventFilter(watched, event)

    def _configure_combo_popup(self, combo: QComboBox) -> None:
        view = combo.view()
        popup = view.window()
        view.setObjectName("immersiveSettingsComboPopup")
        view.setAutoFillBackground(True)
        view.viewport().setAutoFillBackground(True)
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        view.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        if popup is not self.window():
            popup.setObjectName("immersiveSettingsComboContainer")
            popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            popup.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            popup.setAutoFillBackground(True)
        view.installEventFilter(self)
        palette = view.palette()
        surface = _color(self._theme.colors.elevated_background)
        text = _color(self._theme.colors.primary_text)
        highlight = _color(self._theme.colors.selected_background)
        palette.setColor(QPalette.ColorRole.Base, surface)
        palette.setColor(QPalette.ColorRole.Window, surface)
        palette.setColor(QPalette.ColorRole.Text, text)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Highlight, highlight)
        palette.setColor(QPalette.ColorRole.HighlightedText, text)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, surface)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, surface)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, _color(self._theme.colors.disabled_text))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, _color(self._theme.colors.disabled_text))
        view.setPalette(palette)
        view.viewport().setPalette(palette)
        if popup is not self.window():
            popup.setPalette(palette)
            popup.setStyleSheet(
                f"QFrame#immersiveSettingsComboContainer {{ background: {surface.name()}; color: {text.name()}; border: 1px solid {_rgba(self._theme.colors.border, 255)}; }}"
            )
        view.setStyleSheet(
            f"QAbstractItemView#immersiveSettingsComboPopup {{ background: {surface.name()}; color: {text.name()}; border: 1px solid {_rgba(self._theme.colors.border, 255)}; outline: 0; selection-background-color: {highlight.name()}; selection-color: {text.name()}; }}"
            f"QAbstractItemView#immersiveSettingsComboPopup::item {{ min-height: 28px; padding: 4px 8px; background: {surface.name()}; color: {text.name()}; }}"
            f"QAbstractItemView#immersiveSettingsComboPopup::item:hover {{ background: {_color(self._theme.colors.hover_background).name()}; color: {text.name()}; }}"
            f"QAbstractItemView#immersiveSettingsComboPopup::item:selected {{ background: {highlight.name()}; color: {text.name()}; }}"
            f"QScrollBar:vertical {{ width: 6px; background: {surface.name()}; }}"
            f"QScrollBar::handle:vertical {{ min-height: 24px; border-radius: 3px; background: {_color(self._theme.colors.border_strong).name()}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    @staticmethod
    def _set_slider(slider: QSlider, value: int) -> None:
        slider.blockSignals(True)
        slider.setValue(value)
        slider.blockSignals(False)
        label = slider.property("value_label")
        if isinstance(label, QLabel):
            label.setText(f"{value}{slider.property('suffix')}")

    @staticmethod
    def _set_check(check: QCheckBox, value: bool) -> None:
        check.blockSignals(True)
        check.setChecked(value)
        check.blockSignals(False)

    @staticmethod
    def _set_combo_data(combo: QComboBox, data: str) -> None:
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, combo.findData(data)))
        combo.blockSignals(False)


class ImmersiveLyricsPreview(QWidget):
    """Isolated visual-review window with persistent, separately composited layers."""

    fullscreen_requested = Signal(bool)
    immersive_exit_requested = Signal()
    transparency_mode_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None, *, standalone: bool = True) -> None:
        super().__init__(parent)
        self._standalone = bool(standalone)
        self._host_fullscreen = False
        self._controls_interacting = False
        self._theme = get_theme("dark")
        self._artwork = MOCK_ARTWORKS[0]
        self._language = "中文"
        self._translation_visible = True
        self._romanization_visible = False
        self._background_mode = "artwork"
        self._background_opacity = 55
        self._overlay_strength = 45
        self._control_surface_opacity = 35
        self._cover_scale = 100
        self._lyrics_max_width = 780
        self._auto_hide_controls = True
        self._normal_geometry: QRect | None = None
        self._transparency_supported = True
        self._layout_band = "wide"
        self.setObjectName("immersiveLyricsPreview")
        self.setWindowTitle("沉浸歌词视觉预览")
        self.setMinimumSize(780, 520)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        if self._standalone:
            # Keep native transparency capability stable for this widget's lifetime.
            # Switching it after show() can make Qt recreate the native window on Windows.
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self._transparency_supported = self.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.background = BackgroundLayer(self._theme, self)
        self.readability_overlay = ReadabilityOverlay(self._theme, self)
        self.lyric_protection = LyricsReadabilityProtection(self._theme, self)
        self.content = QWidget(self)
        self.content.setObjectName("contentLayer")
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content.setAutoFillBackground(False)
        self.track_info = PreviewTrackInfo(self._theme, self.content)
        self.lyrics_view = PreviewLyricsView(self._theme, self.content)
        self._content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.content)
        self._content_layout.addWidget(self.track_info)
        self._content_layout.addWidget(self.lyrics_view, 1)
        self.controls = PreviewControls(self._theme, self)
        self.controls.set_surface_opacity(self._control_surface_opacity)
        self._controls_effect = QGraphicsOpacityEffect(self.controls)
        self._controls_effect.setOpacity(1.0)
        self.controls.setGraphicsEffect(self._controls_effect)
        self._controls_fade = QPropertyAnimation(self._controls_effect, b"opacity", self)
        self._controls_fade.setDuration(180)
        self._controls_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._controls_hide_timer = QTimer(self)
        self._controls_hide_timer.setSingleShot(True)
        self._controls_hide_timer.setInterval(2200)
        self._controls_hide_timer.timeout.connect(self._hide_controls_preview)
        self.controls.more_requested.connect(self.toggle_settings_panel)
        self.controls.back_requested.connect(self._request_immersive_exit)
        self.controls.interaction_changed.connect(self._set_controls_interacting)
        self.settings_panel = SettingsPanel(self._theme, self)
        self.settings_panel.hide()
        self._connect_settings_panel()
        self._fullscreen_action = QAction(self)
        self._fullscreen_action.setShortcut("F11")
        self._fullscreen_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self._fullscreen_action)
        self._escape_action = QAction(self)
        self._escape_action.setShortcut("Esc")
        self._escape_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._escape_action.triggered.connect(self._handle_escape)
        self.addAction(self._escape_action)
        for widget in (self, self.content, self.track_info, self.lyrics_view, self.lyrics_view.viewport(), self.lyrics_view.canvas, self.controls, self.settings_panel):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)
        self._apply_root_surface()
        self._apply_responsive_layout()
        self._refresh_settings_panel()

    @property
    def is_fullscreen(self) -> bool:
        return self.isFullScreen() if self._standalone else self._host_fullscreen

    @property
    def normal_geometry(self) -> QRect | None:
        return QRect(self._normal_geometry) if self._normal_geometry is not None else None

    @property
    def background_mode(self) -> str:
        return self._background_mode

    @property
    def background_opacity_percent(self) -> int:
        return self._background_opacity

    @property
    def overlay_strength(self) -> int:
        return self._overlay_strength

    @property
    def control_surface_opacity(self) -> int:
        return self._control_surface_opacity

    @property
    def transparency_supported(self) -> bool:
        return self._transparency_supported

    @property
    def root_background_alpha(self) -> int:
        return 0 if self._background_mode == "transparent" else 255

    @property
    def content_layer_alpha(self) -> int:
        return 255

    @property
    def auto_hide_controls(self) -> bool:
        return self._auto_hide_controls

    @property
    def controls_visible(self) -> bool:
        return self._controls_effect.opacity() > 0.1

    @property
    def global_lyric_scale(self) -> int:
        return self.lyrics_view.canvas.global_scale

    def instance_snapshot(self) -> dict[str, object]:
        """Return the persistent preview state used by focused lifetime tests."""
        canvas = self.lyrics_view.canvas
        preview_count = sum(isinstance(widget, ImmersiveLyricsPreview) for widget in QApplication.topLevelWidgets())
        return {
            "window_id": id(self),
            "top_level_widget_count": len(QApplication.topLevelWidgets()),
            "preview_top_level_count": preview_count,
            "lyrics_canvas_id": id(canvas),
            "floating_controls_id": id(self.controls),
            "settings_panel_id": id(self.settings_panel),
            "geometry": self.geometry().getRect(),
            "theme": self._theme.mode,
            "background_mode": self._background_mode,
            "background_opacity": self._background_opacity,
            "overlay_strength": self._overlay_strength,
            "control_surface_opacity": self._control_surface_opacity,
            "global_lyric_scale": canvas.global_scale,
            "font_sizes": (
                canvas.active_font_size,
                canvas.inactive_font_size,
                canvas.translation_font_size,
                canvas.romanization_font_size,
            ),
            "settings_visible": self.settings_panel.isVisible(),
        }

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in {QEvent.Type.MouseMove, QEvent.Type.Enter}:
            self.wake_controls()
        if event.type() == QEvent.Type.MouseButtonPress and self.settings_panel.isVisible() and watched in {self, self.content, self.lyrics_view, self.lyrics_view.viewport(), self.lyrics_view.canvas}:
            self.hide_settings_panel()
            return False
        if event.type() == QEvent.Type.MouseButtonDblClick and watched in {self, self.content, self.track_info, self.lyrics_view, self.lyrics_view.viewport(), self.lyrics_view.canvas}:
            self.toggle_fullscreen()
            return True
        return super().eventFilter(watched, event)

    def set_theme_mode(self, mode: str) -> None:
        self._theme = get_theme(mode)
        if not hasattr(self, "_overlay_user_adjusted"):
            self._overlay_user_adjusted = False
        if not self._overlay_user_adjusted:
            self._overlay_strength = 45 if self._theme.mode == "dark" else 25
        self.background.set_theme(self._theme)
        self.readability_overlay.set_theme(self._theme)
        self.readability_overlay.set_strength(self._overlay_strength)
        self.lyric_protection.set_theme(self._theme)
        self.track_info.set_theme(self._theme)
        self.lyrics_view.set_theme(self._theme)
        self.controls.set_theme(self._theme)
        self.settings_panel.set_theme(self._theme)
        self._apply_root_surface()
        self._refresh_settings_panel()

    def set_background_mode(self, mode: str) -> None:
        value = mode if mode in BackgroundLayer.MODES else "artwork"
        if value == "transparent" and not self._transparency_supported:
            value = "artwork"
        self._background_mode = value
        self.background.set_mode(value)
        self._apply_root_surface()
        self._refresh_settings_panel()
        self.transparency_mode_changed.emit(value == "transparent")

    def set_background_opacity(self, value: int) -> None:
        self._background_opacity = max(0, min(100, int(value)))
        self.background.set_opacity_percent(self._background_opacity)
        self._refresh_settings_panel()

    def set_overlay_strength(self, value: int) -> None:
        self._overlay_user_adjusted = True
        self._overlay_strength = max(0, min(90, int(value)))
        self.readability_overlay.set_strength(self._overlay_strength)
        self._refresh_settings_panel()

    def set_control_surface_opacity(self, value: int) -> None:
        self._control_surface_opacity = max(0, min(100, int(value)))
        self.controls.set_surface_opacity(self._control_surface_opacity)
        self._refresh_settings_panel()

    def set_lyric_protection_enabled(self, enabled: bool) -> None:
        self.lyric_protection.set_enabled(enabled)
        self._refresh_settings_panel()

    def set_lyric_protection_strength(self, value: int) -> None:
        self.lyric_protection.set_strength(value)
        self._refresh_settings_panel()

    def set_lyric_font_sizes(self, active: int, inactive: int, translation: int, romanization: int) -> None:
        self.lyrics_view.canvas.set_font_sizes(active, inactive, translation, romanization)
        self._refresh_settings_panel()

    def set_global_lyric_scale(self, value: int) -> None:
        self.lyrics_view.canvas.set_global_scale(value)
        self._refresh_settings_panel()

    def reset_lyric_sizes(self) -> None:
        self.lyrics_view.canvas.set_global_scale(100)
        self.lyrics_view.canvas.set_font_sizes(46, 30, 14, 15)
        self._refresh_settings_panel()

    def reset_all_immersive_settings(self) -> None:
        self.set_theme_mode("dark")
        self.set_background_mode("artwork")
        self.set_background_opacity(55)
        self._overlay_user_adjusted = False
        self._overlay_strength = 45
        self.readability_overlay.set_strength(self._overlay_strength)
        self.set_control_surface_opacity(35)
        self.set_lyric_protection_enabled(True)
        self.set_lyric_protection_strength(58)
        self.reset_lyric_sizes()
        self.set_lyric_weight("Semibold")
        self.set_inactive_lyric_opacity(68)
        self.set_text_protection("轻微阴影")
        self.set_translation_visible(True)
        self.set_romanization_visible(False)
        self.set_cover_scale(100)
        self.set_lyrics_max_width(780)
        self.set_auto_hide_controls(True)
        self._refresh_settings_panel()

    def set_lyric_weight(self, value: str) -> None:
        self.lyrics_view.canvas.set_weight_name(value)
        self._refresh_settings_panel()

    def set_inactive_lyric_opacity(self, value: int) -> None:
        self.lyrics_view.canvas.set_inactive_opacity(value)
        self._refresh_settings_panel()

    def set_text_protection(self, value: str) -> None:
        self.lyrics_view.canvas.set_text_protection(value)
        self._refresh_settings_panel()

    def set_cover_scale(self, value: int) -> None:
        self._cover_scale = max(70, min(130, int(value)))
        self.track_info.set_cover_scale(self._cover_scale)
        self._apply_responsive_layout()
        self._refresh_settings_panel()

    def set_lyrics_max_width(self, value: int) -> None:
        self._lyrics_max_width = max(420, min(920, int(value)))
        self._apply_responsive_layout()
        self._refresh_settings_panel()

    def set_auto_hide_controls(self, enabled: bool) -> None:
        self._auto_hide_controls = bool(enabled)
        self.wake_controls()
        self._refresh_settings_panel()

    def set_track(self, track: Track | None, document: LyricsDocument | None) -> None:
        """Update visual metadata from the formal V2 lyric document."""
        artwork = artwork_for_track(track)
        self._artwork = artwork
        self.background.set_artwork(artwork)
        self.track_info.set_track(track, document)
        self.lyrics_view.set_artwork(artwork)
        self.lyrics_view.set_document(document)

    def bind_playback(self, adapter: PlaybackAdapter) -> None:
        self.controls.bind_playback(adapter)
        adapter.playing_changed.connect(self._on_playing_changed)

    def set_host_fullscreen(self, fullscreen: bool) -> None:
        self._host_fullscreen = bool(fullscreen)
        self._refresh_settings_panel()

    def set_active(self, active: bool) -> None:
        if active:
            self.wake_controls()
        else:
            self._controls_hide_timer.stop()
            self._fade_controls_to(1.0)

    def set_artwork_key(self, key: str) -> None:
        self._artwork = artwork_for_key(key)
        self.background.set_artwork(self._artwork)
        self.track_info.set_artwork(self._artwork)
        self.lyrics_view.set_artwork(self._artwork)

    def set_language(self, language: str) -> None:
        self._language = "英文" if language == "英文" else "中文"
        self.lyrics_view.set_language(self._language)
        self._refresh_settings_panel()

    def set_translation_visible(self, visible: bool) -> None:
        self._translation_visible = bool(visible)
        self.lyrics_view.set_translation_visible(self._translation_visible)
        self._refresh_settings_panel()

    def set_romanization_visible(self, _visible: bool) -> None:
        self._romanization_visible = False
        self.lyrics_view.set_romanization_visible(False)
        self._refresh_settings_panel()

    def enter_fullscreen(self) -> None:
        if self.is_fullscreen:
            return
        if not self._standalone:
            self.fullscreen_requested.emit(True)
            return
        self._normal_geometry = QRect(self.geometry())
        self.showFullScreen()
        self._apply_responsive_layout()
        self._refresh_settings_panel()

    def exit_fullscreen(self) -> None:
        if not self.is_fullscreen:
            return
        if not self._standalone:
            self.fullscreen_requested.emit(False)
            return
        self.showNormal()
        if self._normal_geometry is not None:
            self.setGeometry(self._normal_geometry)
        self._apply_responsive_layout()
        self._refresh_settings_panel()

    def toggle_fullscreen(self) -> None:
        self.exit_fullscreen() if self.is_fullscreen else self.enter_fullscreen()

    def show_settings_panel(self) -> None:
        self.settings_panel.show()
        self.settings_panel.raise_()
        self.wake_controls()
        self._refresh_settings_panel()

    def hide_settings_panel(self) -> None:
        self.settings_panel.hide()
        self.wake_controls()

    def toggle_settings_panel(self) -> None:
        self.hide_settings_panel() if self.settings_panel.isVisible() else self.show_settings_panel()

    def wake_controls(self) -> None:
        self._controls_hide_timer.stop()
        self._fade_controls_to(1.0)
        if self._auto_hide_controls and not self.settings_panel.isVisible() and not self._controls_interacting:
            self._controls_hide_timer.start()

    def hide_controls_preview(self) -> None:
        self._hide_controls_preview()

    def _hide_controls_preview(self) -> None:
        if self._auto_hide_controls and not self.settings_panel.isVisible() and not self._controls_interacting:
            self._fade_controls_to(0.06)

    def _set_controls_interacting(self, interacting: bool) -> None:
        self._controls_interacting = bool(interacting)
        if self._controls_interacting:
            self.wake_controls()
        elif self._auto_hide_controls and not self.settings_panel.isVisible():
            self._controls_hide_timer.start()

    def _on_playing_changed(self, playing: bool) -> None:
        if not playing:
            self.wake_controls()

    def _request_immersive_exit(self) -> None:
        if self._standalone:
            self.close()
        else:
            self.immersive_exit_requested.emit()

    def _fade_controls_to(self, target: float) -> None:
        if abs(self._controls_effect.opacity() - target) < 0.01:
            return
        self._controls_fade.stop()
        self._controls_fade.setStartValue(self._controls_effect.opacity())
        self._controls_fade.setEndValue(target)
        self._controls_fade.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_responsive_layout()
        self._refresh_content_layer()
        QTimer.singleShot(30, self._refresh_content_layer)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._controls_hide_timer.stop()
        super().hideEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif key == Qt.Key.Key_Escape:
            self._handle_escape()
        elif key == Qt.Key.Key_1:
            self.set_artwork_key("cool")
        elif key == Qt.Key.Key_2:
            self.set_artwork_key("warm")
        elif key == Qt.Key.Key_3:
            self.set_artwork_key("muted")
        elif key == Qt.Key.Key_C:
            self.set_language("中文")
        elif key == Qt.Key.Key_E:
            self.set_language("英文")
        elif key == Qt.Key.Key_T:
            self.set_theme_mode("light" if self._theme.mode == "dark" else "dark")
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _handle_escape(self) -> None:
        if self.settings_panel.close_open_popup():
            return
        if self.settings_panel.isVisible():
            self.hide_settings_panel()
        elif self.is_fullscreen:
            self.exit_fullscreen()
        elif not self._standalone:
            self.immersive_exit_requested.emit()

    def _set_transparent_window(self, enabled: bool) -> bool:
        # Compatibility hook for callers from earlier preview revisions.  Window
        # capability is fixed before first show, so no native handle is recreated.
        return not enabled or self._transparency_supported

    def _apply_root_surface(self) -> None:
        root_background = "transparent" if self._background_mode == "transparent" else self._theme.colors.window_background
        self.setStyleSheet(f"QWidget#immersiveLyricsPreview {{ background: {root_background}; }}")
        self.content.setStyleSheet("background: transparent;")

    def _apply_responsive_layout(self) -> None:
        width = max(1, self.width())
        height = max(1, self.height())
        if width < 900:
            band, direction, margins, spacing = "small", QBoxLayout.Direction.TopToBottom, (24, 22, 24, 118), 18
            scale, band_max_width, control_width, control_bottom = 0.80, 620, min(max(620, width - 36), round(width * 0.94)), 20
        elif width < 1100:
            band, direction, margins, spacing = "compact", QBoxLayout.Direction.LeftToRight, (32, 30, 32, 118), 26
            scale, band_max_width, control_width, control_bottom = 0.88, 680, min(round(width * 0.92), max(620, width - 48)), 22
        elif width < 1400:
            band, direction, margins, spacing = "standard", QBoxLayout.Direction.LeftToRight, (54, 44, 54, 132), 42
            scale, band_max_width, control_width, control_bottom = 0.94, 740, min(1120, max(760, round(width * 0.80))), 26
        elif width < 1700:
            band, direction, margins, spacing = "wide", QBoxLayout.Direction.LeftToRight, (72, 54, 72, 136), 54
            scale, band_max_width, control_width, control_bottom = 1.0, 820, min(1240, max(900, round(width * 0.78))), 30
        else:
            band, direction, margins, spacing = "ultra", QBoxLayout.Direction.LeftToRight, (76, 60, 76, 142), 58
            scale, band_max_width, control_width, control_bottom = 1.06, 880, min(1320, max(960, round(min(width, 1640) * 0.80))), 34
        content_width = min(width, 1640) if band == "ultra" else width
        content_x = max(0, (width - content_width) // 2)
        self.background.setGeometry(self.rect())
        self.readability_overlay.setGeometry(self.rect())
        self.content.setGeometry(content_x, 0, content_width, height)
        self.track_info.set_cover_scale(self._cover_scale)
        self.track_info.set_responsive(content_width)
        self._content_layout.setDirection(direction)
        self._content_layout.setContentsMargins(*margins)
        self._content_layout.setSpacing(spacing)
        self._content_layout.setStretch(0, 30 if band in {"standard", "wide", "ultra"} else 28)
        self._content_layout.setStretch(1, 70 if band in {"standard", "wide", "ultra"} else 72)
        self.lyrics_view.canvas.set_responsive_scale(scale)
        self.lyrics_view.canvas.set_max_line_width(min(self._lyrics_max_width, band_max_width))
        self.lyric_protection.setGeometry(self.lyrics_view.geometry())
        self.controls.set_compact(band in {"small", "compact"})
        controls_height = self.controls.sizeHint().height()
        control_width = min(width - 24, max(360, control_width))
        self.controls.setGeometry(max(12, (width - control_width) // 2), max(12, height - controls_height - control_bottom), control_width, controls_height)
        self._layout_settings_panel(width, height)
        self._layout_band = band
        self.background.lower()
        self.readability_overlay.stackUnder(self.lyric_protection)
        self.lyric_protection.stackUnder(self.content)
        self.content.raise_()
        self.controls.raise_()
        self.settings_panel.raise_()

    def _refresh_content_layer(self) -> None:
        """Prompt one content-layer repaint after a native layered-window show."""
        self.content.update()
        self.track_info.update()
        self.track_info.artwork.update()
        self.lyrics_view.update()
        self.lyrics_view.canvas.update()

    def _layout_settings_panel(self, width: int, height: int) -> None:
        if width < 900:
            panel_width = min(round(width * 0.88), 520)
            panel_height = min(max(360, height - 124), 500)
            x = max(12, (width - panel_width) // 2)
            y = max(20, height - panel_height - 92)
        else:
            panel_width = min(420, max(340, round(width * 0.29)))
            panel_height = min(max(420, height - 96), 680)
            x = width - panel_width - 28
            y = max(24, (height - panel_height) // 2)
        self.settings_panel.setGeometry(x, y, panel_width, panel_height)

    def _connect_settings_panel(self) -> None:
        panel = self.settings_panel
        panel.closed.connect(self.hide_settings_panel)
        panel.theme_requested.connect(self.set_theme_mode)
        panel.background_mode_requested.connect(self.set_background_mode)
        panel.background_opacity_changed.connect(self.set_background_opacity)
        panel.overlay_strength_changed.connect(self.set_overlay_strength)
        panel.control_surface_opacity_changed.connect(self.set_control_surface_opacity)
        panel.lyric_protection_changed.connect(self.set_lyric_protection_enabled)
        panel.lyric_protection_strength_changed.connect(self.set_lyric_protection_strength)
        panel.global_lyric_scale_changed.connect(self.set_global_lyric_scale)
        panel.font_sizes_changed.connect(self.set_lyric_font_sizes)
        panel.weight_changed.connect(self.set_lyric_weight)
        panel.inactive_opacity_changed.connect(self.set_inactive_lyric_opacity)
        panel.text_protection_changed.connect(self.set_text_protection)
        panel.translation_changed.connect(self.set_translation_visible)
        panel.cover_scale_changed.connect(self.set_cover_scale)
        panel.lyrics_width_changed.connect(self.set_lyrics_max_width)
        panel.auto_hide_changed.connect(self.set_auto_hide_controls)
        panel.fullscreen_requested.connect(self._set_fullscreen_checked)
        panel.immersive_exit_requested.connect(self._request_immersive_exit)
        panel.reset_lyric_sizes_requested.connect(self.reset_lyric_sizes)
        panel.reset_all_requested.connect(self.reset_all_immersive_settings)

    def _set_fullscreen_checked(self, enabled: bool) -> None:
        if enabled and not self.is_fullscreen:
            self.enter_fullscreen()
        elif not enabled and self.is_fullscreen:
            self.exit_fullscreen()

    def _refresh_settings_panel(self) -> None:
        if hasattr(self, "settings_panel"):
            self.settings_panel.set_values(self)


PreviewBackground = BackgroundLayer

__all__ = [
    "CHINESE_LINES",
    "ENGLISH_LINES",
    "MOCK_ARTWORKS",
    "BackgroundLayer",
    "ImmersiveLyricsPreview",
    "MockArtwork",
    "PreviewBackground",
    "PreviewLyricsView",
    "SettingsPanel",
    "artwork_for_key",
]
