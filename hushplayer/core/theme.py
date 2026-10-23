"""主题系统：调色板、尺寸度量、字体与全局样式表。

设计原则（对应产品定位）：
* 深色以中性炭黑为底，莓果红只做强调，不做大面积铺色；
* 浅色干净通透，靠层次和留白而不是靠边框；
* 所有控件共享同一套圆角、间距与字号阶梯，保持整体一致。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

BRAND_ACCENT = "#C95770"


def qcolor(value: str | QColor) -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    return QColor(value)


def text_origin(painter, rect, flags: int, text: str) -> QPoint:
    """Integer text origin so glyphs land on whole pixels (no half-pixel blur).

    Qt's ``AlignVCenter`` on a fractional ``QRectF`` frequently resolves to a
    .5 baseline, which makes bold CJK strokes look soft. We reproduce the same
    alignment rules with integer maths.
    """
    metrics = painter.fontMetrics()
    width = metrics.horizontalAdvance(text)
    if flags & int(Qt.AlignmentFlag.AlignHCenter):
        x = rect.x() + (rect.width() - width) / 2.0
    elif flags & int(Qt.AlignmentFlag.AlignRight):
        x = rect.x() + rect.width() - width
    else:
        x = rect.x()
    if flags & int(Qt.AlignmentFlag.AlignVCenter):
        y = rect.y() + (rect.height() - metrics.height()) / 2.0 + metrics.ascent()
    elif flags & int(Qt.AlignmentFlag.AlignBottom):
        y = rect.y() + rect.height() - metrics.descent()
    else:
        y = rect.y() + metrics.ascent()
    return QPoint(int(round(x)), int(round(y)))


def draw_text(painter, rect, flags: int, text: str) -> None:
    """Crisp replacement for ``painter.drawText(QRectF, flags, text)``."""
    painter.drawText(text_origin(painter, rect, flags, text), text)


def rgba(value: str | QColor, alpha: float) -> QColor:
    color = qcolor(value)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def mix(first: str | QColor, second: str | QColor, t: float) -> QColor:
    a, b = qcolor(first), qcolor(second)
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def css_rgba(value: str | QColor, alpha: float) -> str:
    color = qcolor(value)
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha:.3f})"


def luminance(value: str | QColor) -> float:
    color = qcolor(value)
    channels = []
    for part in (color.redF(), color.greenF(), color.blueF()):
        channels.append(part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def readable_on(background: str | QColor) -> str:
    return "#FFFFFF" if luminance(background) < 0.45 else "#14141A"


@dataclass(frozen=True)
class Palette:
    mode: str
    window: str
    sidebar: str
    surface: str
    surface_alt: str
    surface_hover: str
    elevated: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_tertiary: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_text: str
    hover: str
    selection: str
    scrim: str
    shadow: str
    danger: str
    success: str
    warning: str
    player: str
    row_alt: str

    @property
    def is_dark(self) -> bool:
        return self.mode in {"dark", "pure"}

    def get(self, name: str) -> str:
        return getattr(self, name)


DARK = Palette(
    mode="dark",
    window="#0F0F12",
    sidebar="#0A0A0D",
    surface="#15151A",
    surface_alt="#1B1B21",
    surface_hover="#232329",
    elevated="#1E1E25",
    border="#262630",
    border_strong="#35353F",
    text="#F4F4F6",
    text_secondary="#A2A2AE",
    text_tertiary="#6D6D79",
    accent="#C95770",
    accent_hover="#D96C82",
    accent_pressed="#AF4460",
    accent_soft="#2B1820",
    accent_text="#FFFFFF",
    hover="#FFFFFF0D",
    selection="#C9577026",
    scrim="#000000A8",
    shadow="#00000066",
    danger="#E06060",
    success="#4FBF8B",
    warning="#E0A33E",
    player="#121216",
    row_alt="#FFFFFF05",
)

LIGHT = Palette(
    mode="light",
    window="#F2F2F5",
    sidebar="#EBEBF0",
    surface="#FFFFFF",
    surface_alt="#F7F7FA",
    surface_hover="#EFEFF4",
    elevated="#FFFFFF",
    border="#E3E3EA",
    border_strong="#D0D0DA",
    text="#15151B",
    text_secondary="#5B5B67",
    text_tertiary="#8B8B98",
    accent="#C24E68",
    accent_hover="#B3455E",
    accent_pressed="#9C3B52",
    accent_soft="#FBECEF",
    accent_text="#FFFFFF",
    hover="#0000000A",
    selection="#C957701F",
    scrim="#00000066",
    shadow="#1A1A2433",
    danger="#C94A4A",
    success="#2E9E6B",
    warning="#C98A2E",
    player="#FAFAFC",
    row_alt="#00000003",
)


PURE = Palette(
    mode="pure",
    window="#000000",
    sidebar="#000000",
    surface="#0A0A0B",
    surface_alt="#121214",
    surface_hover="#1B1B1E",
    elevated="#101012",
    border="#1E1E22",
    border_strong="#2C2C31",
    text="#F5F5F7",
    text_secondary="#9C9CA8",
    text_tertiary="#666670",
    accent="#C95770",
    accent_hover="#D96C82",
    accent_pressed="#AF4460",
    accent_soft="#1E1014",
    accent_text="#FFFFFF",
    hover="#FFFFFF0D",
    selection="#C9577026",
    scrim="#000000B8",
    shadow="#000000AA",
    danger="#E06060",
    success="#4FBF8B",
    warning="#E0A33E",
    player="#050506",
    row_alt="#FFFFFF04",
)

_PALETTES = {"dark": DARK, "light": LIGHT, "pure": PURE}


@dataclass(frozen=True)
class Metrics:
    radius_xs: int = 6
    radius_sm: int = 8
    radius: int = 12
    radius_lg: int = 16
    radius_xl: int = 22
    titlebar_h: int = 48
    sidebar_w: int = 244
    sidebar_rail_w: int = 76
    player_h: int = 94
    page_pad: int = 30
    gap: int = 16
    row_h: int = 50
    row_h_compact: int = 38
    control: int = 34
    hit: int = 30
    motion_fast: int = 110
    motion: int = 190
    motion_slow: int = 300


_metrics = Metrics()


class Theme(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode = "dark"
        self._palette = DARK
        self._reduce_motion = False
        self._font_scale = 1.0
        self._ui_scale = 1.0
        self._accent = BRAND_ACCENT
        self._density = "comfortable"
        self._families = _detect_families()

    # ------------------------------------------------------------------ 状态
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def metrics(self) -> Metrics:
        return _metrics

    @property
    def is_dark(self) -> bool:
        return self._palette.is_dark

    @property
    def reduce_motion(self) -> bool:
        return self._reduce_motion

    @property
    def font_scale(self) -> float:
        return self._font_scale

    @property
    def ui_scale(self) -> float:
        """Layout-independent type scale for high-resolution screens.

        Keeping the device pixel ratio at 1.0 and enlarging type/metrics here
        keeps glyphs on whole pixels (crisp) while still looking comfortable on
        a 1440p panel.
        """
        return self._ui_scale

    @property
    def type_scale(self) -> float:
        return self._ui_scale * self._font_scale

    def scaled(self, value: int | float, *, factor: float = 0.85) -> int:
        """Scale a layout constant with the type scale (nav rows, chips, …)."""
        scale = 1.0 + (self.type_scale - 1.0) * factor
        return int(round(float(value) * scale))

    def px(self, size: float) -> int:
        """Final pixel size for both QSS and QPainter text."""
        scaled = (size + self.FONT_LEGIBILITY_BONUS) * self.type_scale * self.TEXT_LEGIBILITY
        return max(12, round(scaled))

    def pt(self, size: float) -> float:
        """Point equivalent of :meth:`px`, so QSS text matches painted text."""
        return self.px(size) * 0.75

    @property
    def accent(self) -> str:
        return self._accent

    @property
    def families(self) -> list[str]:
        return self._families

    def color(self, name: str) -> QColor:
        return qcolor(getattr(self._palette, name))

    def apply(
        self,
        *,
        mode: str | None = None,
        accent: str | None = None,
        reduce_motion: bool | None = None,
        font_scale: float | None = None,
        density: str | None = None,
        ui_scale: float | None = None,
    ) -> None:
        changed = False
        if mode is not None and mode != self._mode:
            self._mode = mode
            base = _PALETTES.get(mode, DARK)
            self._palette = base
            changed = True
        if accent and accent.lower() != self._accent.lower():
            self._accent = accent
            self._palette = _with_accent(self._palette, accent)
            changed = True
        elif changed:
            self._palette = _with_accent(self._palette, self._accent)
        if reduce_motion is not None and reduce_motion != self._reduce_motion:
            self._reduce_motion = reduce_motion
            changed = True
        if font_scale is not None and abs(font_scale - self._font_scale) > 1e-3:
            self._font_scale = font_scale
            changed = True
        if ui_scale is not None and abs(ui_scale - self._ui_scale) > 1e-3:
            self._ui_scale = ui_scale
            changed = True
        if density is not None and density != self._density:
            self._density = density
            changed = True
        if changed:
            self.changed.emit()

    @property
    def density(self) -> str:
        return self._density

    def row_height(self) -> int:
        return _metrics.row_h_compact if self._density == "compact" else _metrics.row_h

    # ------------------------------------------------------------------ 字体
    #: Small UI text looked washed out on high-DPI screens: a slight floor plus
    #: full hinting keeps glyph stems on whole device pixels.
    FONT_LEGIBILITY_BONUS = 1.0
    # Qt draws QSS text and QPainter text through different paths; keeping one
    # multiplier here is what stops the sidebar from looking bolder/smaller than
    # the search field (they now resolve to the same pixel size).
    TEXT_LEGIBILITY = 1.27

    def font(self, size: float, weight: int = 400, *, display: bool = False) -> QFont:
        families = self._families
        font = QFont()
        font.setFamilies(families)
        font.setPixelSize(self.px(size))
        font.setWeight(QFont.Weight(weight))
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        font.setKerning(True)
        return font

    def mono_font(self, size: float, weight: int = 400) -> QFont:
        font = QFont()
        font.setFamilies(["Cascadia Mono", "Consolas", "Segoe UI"])
        font.setPixelSize(self.px(size))
        font.setWeight(QFont.Weight(weight))
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        return font

    # ------------------------------------------------------------------ 动画
    def duration(self, base: int) -> int:
        if self._reduce_motion:
            return 0
        return base

    # ------------------------------------------------------------------ 样式表
    def qss(self) -> str:
        p = self._palette
        hover_bg = css_rgba("#FFFFFF" if p.is_dark else "#000000", 0.07)
        return f"""
QWidget {{
    color: {p.text};
    background: transparent;
    selection-background-color: transparent;
    selection-color: {p.text};
}}
QWidget#RootWindow {{ background: {p.window}; }}
QWidget#ContentHost {{ background: {p.window}; }}
QToolTip {{
    background: {p.elevated};
    color: {p.text};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 12px;
}}
QMenu {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 28px 7px 12px;
    margin: 1px 5px;
    border-radius: 7px;
    color: {p.text};
    font-size: 13px;
}}
QMenu::item:selected {{ background: {css_rgba(p.accent, 0.16)}; color: {p.text}; }}
QMenu::item:disabled {{ color: {css_rgba(p.text, 0.42)}; }}
QLabel:disabled {{ color: {css_rgba(p.text, 0.55)}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {css_rgba(p.text, 0.16)};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {css_rgba(p.text, 0.30)}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {css_rgba(p.text, 0.16)};
    border-radius: 4px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{ background: {css_rgba(p.text, 0.30)}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 7px 10px;
    color: {p.text};
    selection-background-color: {p.accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {p.accent}; }}
QComboBox {{
    background: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 20px;
    color: {p.text};
}}
QComboBox:hover {{ background: {p.surface_hover}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 6px;
    outline: none;
    selection-background-color: {css_rgba(p.accent, 0.20)};
    selection-color: {p.text};
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    padding: 2px 8px;
    border-radius: 8px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {css_rgba(p.accent, 0.12)};
}}
QMenu {{
    background: {p.elevated};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 18px 7px 12px;
    margin: 1px 4px;
    border-radius: 8px;
    color: {p.text};
}}
QMenu::item:selected {{
    background: {css_rgba(p.accent, 0.16)};
    color: {p.text};
}}
QMenu::item:disabled {{ color: {css_rgba(p.text, 0.35)}; }}
QMenu::separator {{
    height: 1px;
    background: {p.border};
    margin: 5px 12px;
}}
QMenu::icon {{ padding-left: 6px; }}
QPushButton#LinkButton {{
    background: transparent;
    border: none;
    padding: 4px 2px;
    color: {css_rgba(p.text, 0.55)};
    text-align: left;
}}
QPushButton#LinkButton:hover {{ color: {p.accent}; }}
QPushButton {{
    background: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 7px 14px;
    color: {p.text};
}}
QPushButton:hover {{ background: {p.surface_hover}; }}
QPushButton:pressed {{ background: {p.surface}; }}
QPushButton:disabled {{ color: {p.text_tertiary}; }}
QCheckBox {{ color: {p.text}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {p.border_strong};
    background: {p.surface_alt};
}}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}
QCheckBox::indicator:checked:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QCheckBox::indicator:disabled {{ border-color: {p.border}; background: transparent; }}
QMessageBox, QDialog {{ background: {p.window}; }}
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 12px; background: {p.surface}; }}
QTabBar::tab {{
    background: transparent;
    padding: 7px 14px;
    border-radius: 8px;
    color: {p.text_secondary};
}}
QTabBar::tab:selected {{ background: {p.accent_soft}; color: {p.accent}; }}
QSplitter::handle {{ background: transparent; }}
QSlider::groove:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {css_rgba(p.text, 0.14)};
}}
QSlider::sub-page:horizontal {{
    height: 4px;
    border-radius: 2px;
    background: {p.accent};
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
    background: {p.accent};
    border: 2px solid {p.surface};
}}
QSlider::handle:horizontal:hover {{ background: {p.accent_hover}; }}
QSlider::handle:horizontal:disabled {{ background: {css_rgba(p.text, 0.35)}; }}
QListView {{ background: transparent; border: none; outline: none; }}
/* BUG-10: the global QWidget selection colour painted a solid berry block
   behind selected rows, and the "now playing" title was berry too -> red on
   red. Item views paint their own tinted selection in the delegate, so keep
   the native selection fill transparent here. */
QTableView, QTreeView, QListView {{
    background: transparent;
    border: none;
    outline: none;
    alternate-background-color: transparent;
    selection-background-color: transparent;
    selection-color: {p.text};
}}
QTableView::item, QTreeView::item, QListView::item {{ background: transparent; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: transparent;
    color: {p.text};
}}
"""

    def window_palette(self) -> QPalette:
        p = self._palette
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, qcolor(p.window))
        pal.setColor(QPalette.ColorRole.WindowText, qcolor(p.text))
        pal.setColor(QPalette.ColorRole.Base, qcolor(p.surface))
        pal.setColor(QPalette.ColorRole.AlternateBase, qcolor(p.surface_alt))
        pal.setColor(QPalette.ColorRole.Text, qcolor(p.text))
        pal.setColor(QPalette.ColorRole.Button, qcolor(p.surface_alt))
        pal.setColor(QPalette.ColorRole.ButtonText, qcolor(p.text))
        pal.setColor(QPalette.ColorRole.Highlight, qcolor(p.accent))
        pal.setColor(QPalette.ColorRole.HighlightedText, qcolor(p.accent_text))
        pal.setColor(QPalette.ColorRole.ToolTipBase, qcolor(p.elevated))
        pal.setColor(QPalette.ColorRole.ToolTipText, qcolor(p.text))
        pal.setColor(QPalette.ColorRole.PlaceholderText, qcolor(p.text_tertiary))
        return pal


def _with_accent(palette: Palette, accent: str) -> Palette:
    from dataclasses import replace

    base = qcolor(accent)
    hover = mix(base, "#FFFFFF" if palette.is_dark else "#FFFFFF", 0.16 if palette.is_dark else 0.12)
    pressed = mix(base, "#000000", 0.18)
    soft = mix(palette.surface, base, 0.16 if palette.is_dark else 0.10)
    return replace(
        palette,
        accent=base.name(),
        accent_hover=hover.name(),
        accent_pressed=pressed.name(),
        accent_soft=soft.name(),
        selection=QColor(base.red(), base.green(), base.blue(), 38 if palette.is_dark else 31).name(
            QColor.NameFormat.HexArgb
        ),
    )


def _detect_families() -> list[str]:
    # Bundled MiSans first: the original HushPlayer ships the same family, so
    # both products render Chinese text with identical metrics and weight.
    from .fonts import load_bundled_fonts

    load_bundled_fonts()
    available = {name.lower(): name for name in QFontDatabase.families()}
    wanted: Iterable[str] = (
        "MiSans",
        "Source Han Sans SC",
        "Noto Sans SC",
        "Segoe UI Variable Text",
        "Segoe UI",
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "PingFang SC",
        "Arial",
    )
    families = [available[name.lower()] for name in wanted if name.lower() in available]
    if not families:
        families = ["Segoe UI"]
    return families


_theme: Theme | None = None


def theme() -> Theme:
    global _theme
    if _theme is None:
        _theme = Theme()
    return _theme


def resolve_mode(preference: str) -> str:
    if preference in _PALETTES:
        return preference
    try:
        from PySide6.QtWidgets import QApplication

        hints = QApplication.styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return "light"
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
    except Exception:
        pass
    return "dark"


def apply_native_title_bar(widget, dark: bool | None = None) -> None:
    """Match the Windows title bar of a native-framed window to the app theme.

    QDialog windows keep their own DWM frame; without this the frame stays dark
    while the page inside switches to light (and vice versa).
    """
    try:
        import ctypes

        if dark is None:
            dark = theme().palette.is_dark
        hwnd = int(widget.winId())
        if not hwnd:
            return
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20) + legacy (19)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:  # noqa: BLE001
        pass


def apply_theme_to_app(app, *, preference: str | None = None, accent: str | None = None, **kwargs) -> str:
    t = theme()
    mode = resolve_mode(preference or "system")
    t.apply(mode=mode, accent=accent or BRAND_ACCENT, **kwargs)
    app.setStyleSheet(t.qss())
    app.setPalette(t.window_palette())
    base = t.font(10)
    app.setFont(base)
    return mode


def alpha_text(base: str, color: str, amount: float) -> str:
    """把 color 以 amount 不透明度叠加到 base 上，得到不透明 hex（用于无 alpha 的绘制）。"""
    return mix(base, color, amount).name()
