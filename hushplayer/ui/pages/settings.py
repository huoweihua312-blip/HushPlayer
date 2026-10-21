"""Settings centre: a section list on the left, grouped cards on the right."""

from __future__ import annotations

import os
import platform
import sys

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QPushButton,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import icons, paths
from ...core.logging_setup import get_logger, log_exception
from ...core.settings import settings as settings_singleton
from ...core import brand
from ...core.theme import Metrics, css_rgba, qcolor, rgba, theme
from ...core.display import (
    SCALE_LABELS,
    physical_screen_size,
    recommended_scale,
    scale_text,
)
from ...model.track import format_duration
from ...online.models import build_sources
from ..context import ctx
from ..widgets.common import IconButton, TextButton
from ..widgets.settings_widgets import (
    ActionCard,
    FolderEditor,
    SegmentedPicker,
    SettingCombo,
    SettingField,
    SettingRow,
    SettingSlider,
    SettingsCard,
    ThemePicker,
    ToggleSwitch,
)
from .page import CenteredBox, Page, PageHeader

log = get_logger(__name__)

#: How many online sources stay visible while the list is collapsed.
SOURCES_COLLAPSED_VISIBLE = 4


def source_window(total: int, expanded: bool, limit: int = SOURCES_COLLAPSED_VISIBLE) -> tuple[int, int]:
    """Return ``(visible, hidden)`` for the collapsible source list."""
    if expanded or total <= limit:
        return total, 0
    return limit, total - limit


SECTIONS = [
    ("general", "常规", "settings"),
    ("appearance", "外观与主题", "palette"),
    ("playback", "播放", "play"),
    ("lyrics", "歌词", "lyrics"),
    ("desktop_lyrics", "桌面歌词", "monitor"),
    ("library", "音乐库", "folder"),
    ("online", "在线音源", "cloud"),
    ("cache", "缓存与下载", "download"),
    ("about", "关于", "info"),
]


class _SectionList(QWidget):
    changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(self.preferred_width())
        self._compact = False

    def set_compact(self, compact: bool) -> None:
        if compact != self._compact:
            self._compact = compact
            self.updateGeometry()
            self.update()

    def current(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if 0 <= index < len(SECTIONS) and index != self._current:
            self._current = index
            self.update()
            self.changed.emit(index)

    def _row_h(self) -> int:
        from ...core.theme import theme

        return theme().scaled(30 if self._compact else 36)

    def preferred_width(self) -> int:
        """Widest label plus icon/padding; below this the labels would elide."""
        from PySide6.QtGui import QFontMetrics

        from ...core.theme import theme

        metrics = QFontMetrics(theme().font(9.6, 500))
        text = max(metrics.horizontalAdvance(label) for _key, label, _icon in SECTIONS)
        pad = theme().scaled(11, factor=1.0)
        icon = theme().scaled(18, factor=1.0)
        gap = theme().scaled(10, factor=1.0)
        return int(pad * 2 + icon + gap + text + theme().scaled(12, factor=1.0))

    def sizeHint(self) -> QSize:
        return QSize(self.preferred_width(), len(SECTIONS) * self._row_h() + 8)

    def _rect(self, index: int):
        from PySide6.QtCore import QRectF

        row = self._row_h()
        return QRectF(0, index * row + 4, self.width(), row - 4)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = -1
        for index in range(len(SECTIONS)):
            if self._rect(index).contains(event.position()):
                hover = index
                break
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.PointingHandCursor if hover >= 0 else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            for index in range(len(SECTIONS)):
                if self._rect(index).contains(event.position()):
                    self.set_current(index)
                    break
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme().palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for index, (_key, label, icon_name) in enumerate(SECTIONS):
            rect = self._rect(index)
            selected = index == self._current
            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(rgba(palette.accent, 0.16))
                painter.drawRoundedRect(rect, 7, 7)
            elif index == self._hover:
                painter.setPen(Qt.NoPen)
                painter.setBrush(rgba(palette.text, 0.05))
                painter.drawRoundedRect(rect, 7, 7)
            from PySide6.QtCore import QRectF

            # Icon box and label offset both follow the type scale, so at 150%
            # the glyphs stay the same optical size as the text instead of
            # shrinking into a fixed 18px column.
            icon_size = theme().scaled(18, factor=1.0)
            pad = theme().scaled(14, factor=1.0)
            gap = theme().scaled(2, factor=1.0)
            font = theme().font(9.6, 500 if selected else 400)
            fm = QFontMetrics(font)
            # Align the glyph with the *ink* of the label, not with the row box:
            # AlignVCenter centres the font box, whose ink sits slightly lower
            # (the ascent carries air above the cap height).
            baseline = rect.center().y() + (fm.ascent() - fm.descent()) / 2.0
            icon_cy = baseline - fm.capHeight() / 2.0
            target = QRectF(
                rect.left() + pad,
                icon_cy - icon_size / 2.0,
                icon_size,
                icon_size,
            )
            icons.draw(
                painter,
                icon_name,
                target,
                qcolor(palette.accent) if selected else rgba(palette.text, 0.6 if index == self._hover else 0.5),
            )
            painter.setFont(font)
            painter.setPen(QPen(qcolor(palette.accent) if selected else rgba(palette.text, 0.86)))
            painter.drawText(
                rect.adjusted(pad + icon_size + gap, 0, -theme().scaled(10), 0),
                int(Qt.AlignLeft | Qt.AlignVCenter),
                label,
            )
        painter.end()


class SettingsPage(Page):
    route = "settings"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings_singleton()
        self.header = PageHeader("设置", "所有更改都会立即保存")
        self.header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # PageHeader paints itself without a layout, so sizeHint() is invalid;
        # keep the height it computed instead of feeding -1 to Qt.
        self.header.setMinimumHeight(self.header.height())
        layout = self.content_layout
        layout.setContentsMargins(Metrics.page_pad, 14, Metrics.page_pad, 8)
        layout.setSpacing(10)
        layout.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 4, 0, 0)
        body.setSpacing(22)
        self._nav = _SectionList()
        self._nav.changed.connect(self._show_section)
        self._nav_scroll = QScrollArea()
        self._nav_scroll.setWidget(self._nav)
        self._nav_scroll.setWidgetResizable(True)
        self._nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._nav_scroll.setFixedWidth(self._nav.preferred_width())
        self._nav_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        body.addWidget(self._nav_scroll)
        self._stack = QStackedWidget()
        body.addWidget(self._stack, 1)
        layout.addLayout(body, 1)

        self._builders = {
            "general": self._build_general,
            "appearance": self._build_appearance,
            "playback": self._build_playback,
            "lyrics": self._build_lyrics,
            "desktop_lyrics": self._build_desktop_lyrics,
            "library": self._build_library,
            "online": self._build_online,
            "cache": self._build_cache,
            "about": self._build_about,
        }
        self._sections: dict[str, QWidget] = {}
        self._initial_section = "general"

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Narrow windows give the section list less room so the content column
        # keeps a usable width instead of forcing a horizontal squeeze.
        target = self._nav.preferred_width()
        if self._nav_scroll.width() != target:
            self._nav_scroll.setFixedWidth(target)
            self._nav.setFixedWidth(target)
        self._nav.set_compact(self.height() < 660)

    # ------------------------------------------------------------- utilities
    def _section(self, key: str) -> QWidget:
        if key in self._sections:
            return self._sections[key]
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        host = QWidget()
        host.setStyleSheet("background:transparent;")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        column_host = QWidget()
        column_host.setStyleSheet("background:transparent;")
        # Cap the measure on wide screens without relying on an alignment flag:
        # an aligned child would keep its sizeHint and stop filling the page.
        column_host.setMaximumWidth(theme().scaled(1040, factor=1.0))
        column = QVBoxLayout(column_host)
        column.setContentsMargins(0, 0, 12, 18)
        column.setSpacing(theme().scaled(14, factor=0.8))
        builder = self._builders[key]
        builder(column)
        column.addStretch(1)
        host_layout.addWidget(column_host, 1)
        scroll.setWidget(host)
        self._sections[key] = scroll
        self._stack.addWidget(scroll)
        return scroll

    def _toggle(self, key: str, default: bool = False, *, on_change=None) -> ToggleSwitch:
        switch = ToggleSwitch(bool(self.settings.get(key, default)))
        def apply(value: bool) -> None:
            self.settings.set(key, bool(value))
            if on_change is not None:
                on_change(bool(value))
        switch.toggled.connect(apply)
        return switch

    def _combo(self, key: str, items: list[tuple[str, object]], default: object = None, *, on_change=None) -> SettingCombo:
        combo = SettingCombo(items)
        combo.set_value(self.settings.get(key, default if default is not None else items[0][1]))
        def apply(_index: int) -> None:
            self.settings.set(key, combo.value())
            if on_change is not None:
                on_change(combo.value())
        combo.currentIndexChanged.connect(apply)
        return combo

    def _slider(
        self,
        key: str,
        minimum: float,
        maximum: float,
        *,
        default: float | None = None,
        suffix: str = "",
        formatter=None,
        on_change=None,
    ) -> SettingSlider:
        value = float(self.settings.get(key, default if default is not None else minimum))
        slider = SettingSlider(minimum, maximum, value, suffix=suffix, formatter=formatter)
        def apply(new_value: float) -> None:
            self.settings.set(key, new_value)
            if on_change is not None:
                on_change(new_value)
        # Apply on release / after a short pause, not on every pixel of the
        # drag: restyle, cache prune and disk writes are far too expensive to
        # run dozens of times per second (visible stutter while dragging).
        slider.committed.connect(apply)
        return slider

    def _row(self, title: str, description: str, control: QWidget) -> SettingRow:
        return SettingRow(title, description, control=control)

    # --------------------------------------------------------------- general
    def _build_general(self, column: QVBoxLayout) -> None:
        card = SettingsCard("启动", "HushPlayer 启动时的行为")
        card.add_row(self._row(
            "启动页面",
            "打开应用时首先显示的页面",
            self._combo("general.start_page", [
                ("首页", "home"), ("歌曲", "songs"), ("专辑", "albums"), ("最近播放", "recent"),
            ]),
        ))
        card.add_row(self._row("恢复上次浏览的页面", "重新打开应用时回到上次离开的位置", self._toggle("general.restore_last_page", True)))
        card.add_row(self._row("记住播放队列", "退出后保留队列与播放进度", self._toggle("general.remember_queue", True)))
        column.addWidget(card)

        card = SettingsCard("窗口", "关闭与最小化行为")
        card.add_row(self._row(
            "关闭窗口时",
            "选择退出应用，或收起到系统托盘继续播放",
            self._combo("general.close_action", [
                    ("每次询问", "ask"), ("退出应用", "quit"), ("最小化到托盘", "tray"),
                ]),
        ))
        card.add_row(self._row("最小化到托盘", "最小化时隐藏任务栏按钮", self._toggle("general.minimize_to_tray", False)))
        card.add_row(self._row("开机时自动启动", "登录 Windows 后自动运行（可在系统设置中撤销）", self._toggle("general.launch_at_startup", False)))
        column.addWidget(card)

        card = SettingsCard("系统集成", "与 Windows 桌面和系统媒体的协作方式")
        card.add_row(self._row(
            "系统媒体控制",
            "在系统媒体面板、锁屏与硬件媒体键上控制播放",
            self._toggle("general.system_media_controls", True),
        ))
        card.add_row(self._row(
            "任务栏播放进度",
            "在任务栏按钮上显示当前播放进度",
            self._toggle("general.taskbar_progress", True),
        ))
        card.add_row(self._row(
            "全局快捷键",
            "Ctrl+Alt+Space 播放/暂停，Ctrl+Alt+←/→ 上一首/下一首，Ctrl+Alt+M 静音，Ctrl+Alt+H 显示主窗口",
            self._toggle("general.global_hotkeys", True),
        ))
        column.addWidget(card)

        card = SettingsCard("更新", "")
        card.add_row(self._row("启动时检查更新", "连接发布服务器检查新版本，不会自动安装", self._toggle("general.check_updates_on_start", True)))
        column.addWidget(card)

    # ------------------------------------------------------------- appearance
    def _build_appearance(self, column: QVBoxLayout) -> None:
        card = SettingsCard("主题", "选择浅色、深色，或跟随 Windows 系统设置")
        picker = ThemePicker(str(self.settings.get("appearance.theme", "system")))
        def change_theme(value: str) -> None:
            self.settings.set("appearance.theme", value)
        picker.changed.connect(change_theme)
        card.add(picker)
        column.addWidget(card)

        card = SettingsCard("动效与密度", "")
        card.add_row(self._row("减少动画效果", "关闭页面切换、悬停与歌词动画，适合低性能设备", self._toggle("appearance.reduce_motion", False)))
        card.add_row(
            self._row(
                "主题切换动画",
                "全屏日月动画：中央弹出太阳或月亮，再用黑白全屏过渡切到新配色；过渡动画只从标题栏按钮扩散",
                self._combo(
                    "appearance.theme_animation_mode",
                    [
                        ("过渡动画（从标题栏按钮扩散）", "reveal"),
                        ("全屏日月动画", "sunrise"),
                        ("关闭", "off"),
                    ],
                    "reveal",
                ),
            )
        )
        card.add_row(
            self._row(
                "日月图标弹出时长",
                "太阳/月亮放大出现的时间，只在「全屏日月动画」下生效",
                self._slider("appearance.theme_anim_pop_ms", 150, 1200, default=420, suffix=" ms"),
            )
        )
        card.add_row(
            self._row(
                "日月图标大小",
                "1.0 为默认大小，可放大到 160%",
                self._slider(
                    "appearance.theme_anim_icon_scale",
                    0.6,
                    1.6,
                    default=1.0,
                    formatter=lambda value: f"{value * 100:.0f}%",
                ),
            )
        )
        card.add_row(
            self._row(
                "定格时长",
                "界面已经切到新配色后，太阳/月亮在中央停留的时间（界面始终可见）",
                self._slider("appearance.theme_anim_hold_ms", 0, 900, default=260, suffix=" ms"),
            )
        )
        card.add_row(self._row(
            "界面密度",
            "紧凑模式会缩小列表行高，一屏显示更多歌曲",
            self._segmented("appearance.density", [("舒适", "comfortable"), ("紧凑", "compact")], "comfortable"),
        ))
        card.add_row(self._row("显示来源徽章", "在歌曲列表中标记本地或在线来源", self._toggle("appearance.show_source_badge", True)))
        card.add_row(self._row("显示侧边栏", "隐藏后可通过标题栏左侧按钮恢复", self._toggle("appearance.sidebar_visible", True)))
        column.addWidget(card)

        card = SettingsCard("界面缩放", "针对 2K / 4K 显示器整体放大界面；切换后需要重启程序")
        width, height = physical_screen_size()
        recommended = SCALE_LABELS[recommended_scale(width)]
        screen_note = f"（屏幕 {width}×{height}）" if width else ""
        self._scale_hint = QLabel(f"当前生效 {scale_text()} · 推荐 {recommended}{screen_note}")
        self._scale_hint.setFont(theme().font(8.8))
        self._scale_hint.setWordWrap(True)
        self._scale_hint.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.55)};")
        card.add_row(self._row(
            "缩放比例",
            self._scale_hint,
            self._combo(
                "appearance.ui_scale",
                [(label, key) for key, label in SCALE_LABELS.items()],
                "auto",
                on_change=self._on_scale_changed,
            ),
        ))
        card.add_row(self._row(
            "立即重启",
            "保存设置并重新打开 HushPlayer，使新的缩放比例生效",
            self._action_button("重启程序", "refresh", self._restart_app),
        ))
        column.addWidget(card)

        card = SettingsCard("文字", "字号会按比例应用到整个界面")
        card.add_row(self._row(
            "界面字号",
            "",
            self._slider(
                "appearance.font_scale", 0.80, 1.80, default=1.0,
                formatter=lambda v: f"{int(round(v * 100))}%",
            ),
        ))
        column.addWidget(card)

    def _segmented(self, key: str, items: list[tuple[str, object]], default: object) -> SegmentedPicker:
        picker = SegmentedPicker(items, self.settings.get(key, default))
        def apply(value: object) -> None:
            self.settings.set(key, value)
        picker.changed.connect(apply)
        return picker

    # --------------------------------------------------------------- playback
    def _build_playback(self, column: QVBoxLayout) -> None:
        card = SettingsCard("播放", "")
        card.add_row(self._row(
            "在线音质",
            "音源实际提供的最高音质可能低于此设置",
            self._combo("playback.quality", [
                ("标准", "standard"), ("较高", "higher"), ("极高", "exhigh"), ("无损", "lossless"),
            ], "higher"),
        ))
        card.add_row(self._row("启动时恢复播放", "恢复上次退出时的歌曲与进度", self._toggle("playback.resume_on_start", True)))
        card.add_row(self._row("自动跳过无法播放的歌曲", "连续失败时提示并跳到下一首", self._toggle("playback.skip_unavailable", True)))
        card.add_row(self._row(
            "音量归一化",
            "按本地文件的 ReplayGain 标签自动修正音量（不改变音量滑块）",
            self._combo("playback.replaygain", [
                ("关闭", "off"), ("按曲目", "track"), ("按专辑", "album"),
            ], "off"),
        ))
        card.add_row(self._row(
            "睡眠定时",
            "到时间后自动暂停播放（下次启动不会保留）",
            self._combo("playback.sleep_timer_minutes", [
                ("关闭", 0), ("15 分钟", 15), ("30 分钟", 30), ("60 分钟", 60), ("90 分钟", 90),
            ], 0),
        ))
        column.addWidget(card)

        card = SettingsCard("音频输出", "使用系统当前可用的音频设备")
        devices = self._audio_devices()
        combo = SettingCombo(devices)
        current = str(self.settings.get("playback.audio_device", ""))
        index = 0
        for i, (_label, value) in enumerate(devices):
            if str(value) == current:
                index = i
                break
        combo.setCurrentIndex(index)
        def change_device(_i: int) -> None:
            value = str(combo.value() or "")
            self.settings.set("playback.audio_device", value)
            try:
                ctx().player.set_audio_device(value)
            except Exception as exc:  # noqa: BLE001
                log_exception("切换音频设备失败", exc)
        combo.currentIndexChanged.connect(change_device)
        card.add_row(self._row("输出设备", "更改后立即生效", combo))
        column.addWidget(card)

        card = SettingsCard("快捷键", "在任意页面均可使用")
        for keys, text in [
            ("Space", "播放 / 暂停"),
            ("Ctrl + ← / →", "快退 / 快进 5 秒"),
            ("Ctrl + M", "静音"),
            ("Ctrl + L", "打开歌词页面"),
            ("Ctrl + F", "搜索"),
            ("Esc", "退出沉浸式播放器"),
        ]:
            card.add(self._shortcut_row(keys, text))
        column.addWidget(card)

    def _shortcut_row(self, keys: str, text: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        key_label = QLabel(keys)
        key_label.setFont(theme().font(8.8, 600))
        key_label.setStyleSheet(
            f"color:{css_rgba(theme().palette.text, 0.8)};"
            f"background:{css_rgba(theme().palette.text, 0.06)};"
            f"border:1px solid {css_rgba(theme().palette.text, 0.1)};"
            "border-radius:5px; padding:3px 8px;"
        )
        key_label.setFixedWidth(112)
        key_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(key_label)
        label = QLabel(text)
        label.setFont(theme().font(9.4))
        label.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.72)};")
        layout.addWidget(label, 1)
        return row

    def _audio_devices(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = [("系统默认设备", "")]
        try:
            from PySide6.QtMultimedia import QMediaDevices

            for device in QMediaDevices.audioOutputs():
                items.append((device.description(), device.id().data().decode("utf-8", "ignore") if hasattr(device.id(), "data") else device.description()))
        except Exception:  # noqa: BLE001
            pass
        return items

    # ----------------------------------------------------------------- lyrics
    def _build_lyrics(self, column: QVBoxLayout) -> None:
        card = SettingsCard("歌词来源", "")
        card.add_row(self._row("允许在线获取歌词", "无法在本地找到歌词时，从音源与 LRCLIB 获取", self._toggle("lyrics.online_enabled", True)))
        card.add_row(self._row("优先使用逐字歌词", "音源提供逐字时间时优先显示卡拉 OK 效果", self._toggle("lyrics.prefer_word_timing", True)))
        card.add_row(self._row("显示翻译", "歌词包含翻译时显示第二行", self._toggle("lyrics.translate", True)))
        column.addWidget(card)

        card = SettingsCard("显示", "")
        card.add_row(self._row(
            "歌词字号", "", self._slider("lyrics.font_scale", 0.7, 2.0, default=1.0, formatter=lambda v: f"{int(round(v * 100))}%")
        ))
        card.add_row(self._row(
            "歌词对齐", "沉浸式与歌词页面对齐方式", self._segmented("lyrics.alignment", [("居中", "center"), ("左对齐", "left")], "center")
        ))
        card.add_row(self._row("显示歌曲信息", "在歌词页面顶部显示来源与音质", self._toggle("lyrics.show_metadata", True)))
        column.addWidget(card)

        card = SettingsCard("时间校准", "若歌词整体偏早或偏晚，可在此微调（每首歌也可单独调整）")
        card.add_row(self._row(
            "全局偏移", "", self._slider("lyrics.offset_ms", -2000, 2000, default=0, formatter=lambda v: f"{int(v)} ms")
        ))
        column.addWidget(card)

    # --------------------------------------------------------- desktop lyrics
    def _build_desktop_lyrics(self, column: QVBoxLayout) -> None:
        card = SettingsCard("桌面歌词", "独立于主窗口的悬浮歌词，可在任意应用上方显示")
        card.add_row(self._row("启用桌面歌词", "显示独立悬浮歌词窗口", self._toggle("desktop_lyrics.enabled", False, on_change=self._apply_desktop_lyrics)))
        card.add_row(self._row("总在最前", "保持在其他窗口之上", self._toggle("desktop_lyrics.always_on_top", True, on_change=self._apply_desktop_lyrics)))
        card.add_row(self._row("鼠标穿透", "开启后无法点击歌词窗口，需在设置中关闭", self._toggle("desktop_lyrics.click_through", False, on_change=self._apply_desktop_lyrics)))
        card.add_row(self._row("锁定位置", "防止误拖动", self._toggle("desktop_lyrics.locked", False, on_change=self._apply_desktop_lyrics)))
        column.addWidget(card)

        card = SettingsCard("外观", "")
        card.add_row(self._row("显示行数", "", self._segmented("desktop_lyrics.lines", [("单行", 1), ("双行", 2)], 2)))
        card.add_row(self._row(
            "字号", "", self._slider("desktop_lyrics.font_size", 18, 64, default=32, formatter=lambda v: f"{int(v)} px")
        ))
        card.add_row(self._row(
            "不透明度", "", self._slider("desktop_lyrics.opacity", 0.3, 1.0, default=0.94, formatter=lambda v: f"{int(round(v * 100))}%")
        ))
        card.add_row(self._row("显示翻译", "", self._toggle("desktop_lyrics.show_translation", True)))
        card.add_row(self._row("文字颜色", "", self._swatches("desktop_lyrics.color", "#FFFFFF", ["#FFFFFF", "#F4C36A", "#9BE3C0", "#C95770"])))
        card.add_row(self._row("高亮颜色", "", self._swatches("desktop_lyrics.highlight_color", "#C95770", ["#C95770", "#F4C36A", "#7FC8F8", "#B69CFF"])))
        column.addWidget(card)

    def _swatches(self, key: str, default: str, colors: list[str]) -> QWidget:
        from PySide6.QtCore import Signal as _Signal

        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        current = str(self.settings.get(key, default))
        buttons: list[tuple[str, QWidget]] = []

        class Swatch(QWidget):
            clicked = _Signal(str)

            def __init__(self, color: str, active: bool) -> None:
                super().__init__()
                self.color = color
                self.active = active
                self.setFixedSize(22, 22)
                self.setCursor(Qt.PointingHandCursor)

            def mouseReleaseEvent(self, event):  # noqa: N802
                if event.button() == Qt.LeftButton:
                    self.clicked.emit(self.color)
                super().mouseReleaseEvent(event)

            def paintEvent(self, event):  # noqa: N802
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setPen(QPen(rgba(theme().palette.text, 0.25), 1))
                painter.setBrush(qcolor(self.color))
                painter.drawEllipse(1.5, 1.5, 19, 19)
                if self.active:
                    painter.setPen(QPen(qcolor(theme().palette.accent), 2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(0.5, 0.5, 21, 21)
                painter.end()

        def choose(color: str) -> None:
            self.settings.set(key, color)
            for value, widget in buttons:
                widget.active = value == color
                widget.update()

        for color in colors:
            swatch = Swatch(color, color == current)
            swatch.clicked.connect(choose)
            buttons.append((color, swatch))
            layout.addWidget(swatch)
        layout.addStretch(1)
        return holder

    def _apply_desktop_lyrics(self, _value=None) -> None:
        from ..desktop_lyrics import ensure_desktop_lyrics

        window = ensure_desktop_lyrics()
        if window is None:
            return
        try:
            window.apply_settings()
            if self.settings.get("desktop_lyrics.enabled", False):
                window.show_lyrics()
            else:
                window.hide()
        except Exception as exc:  # noqa: BLE001
            log_exception("更新桌面歌词失败", exc)

    # ---------------------------------------------------------------- library
    def _build_library(self, column: QVBoxLayout) -> None:
        card = SettingsCard("扫描目录", "HushPlayer 会递归扫描这些文件夹中的音频文件")
        editor = FolderEditor(list(self.settings.get("library.folders", []) or []))
        def folders_changed(folders: list[str]) -> None:
            self.settings.set("library.folders", folders)
        editor.changed.connect(folders_changed)
        card.add(editor)
        column.addWidget(card)

        card = SettingsCard("扫描行为", "")
        card.add_row(self._row("启动时自动扫描", "在后台增量扫描音乐库，不阻塞界面", self._toggle("library.auto_scan_on_start", True)))
        card.add_row(self._row("优先使用文件夹封面", "音频内没有封面时查找同目录图片", self._toggle("library.cover_from_folder", True)))
        card.add_row(self._row("立即重新扫描全部目录", "重新读取元数据与封面，可能需要一些时间", self._action_button("重新扫描", "refresh", self._rescan)))
        card.add_row(self._row(
            "修复失效文件",
            "文件被移动或改名后，按新位置重新关联歌曲（不会删除任何数据）",
            self._action_button("检查并修复…", "folder", self._repair_missing),
        ))
        column.addWidget(card)

        stats = ctx().library.stats
        card = SettingsCard("音乐库状态", "")
        info = QLabel(
            f"{stats.track_count} 首歌曲 · {stats.album_count} 张专辑 · {stats.artist_count} 位艺术家 · "
            f"{format_duration(stats.total_duration_ms)}"
        )
        info.setFont(theme().font(9.2))
        info.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.6)};")
        card.add(info)
        column.addWidget(card)

    def _on_scale_changed(self, value: object) -> None:
        """Explain that the choice only takes effect after a restart."""
        label = SCALE_LABELS.get(str(value), str(value))
        hint = getattr(self, "_scale_hint", None)
        if hint is not None and isinstance(hint, QLabel):
            hint.setText(f"已选择 {label} · 重启后生效（当前生效 {scale_text()}）")

    def _restart_app(self) -> None:
        """Restart so a changed QT_SCALE_FACTOR is picked up (BUG-05)."""
        from PySide6.QtCore import QProcess

        from ...core.paths import is_frozen

        program = sys.executable
        args: list[str] = [] if is_frozen() else ["-m", "hushplayer"]
        # The new process waits for us to exit before taking the single-instance
        # mutex; otherwise it would just notify us and quit.
        args = [*args, "--wait-pid", str(os.getpid())]
        try:
            self.settings.flush()
            QProcess.startDetached(program, args)
        except Exception as exc:  # noqa: BLE001
            log_exception("重启程序失败", exc)
            self._toast("重启失败，请手动关闭后重新打开 HushPlayer", "error")
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _action_button(self, text: str, icon_name: str, handler) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        button = TextButton(text, icon_name=icon_name, size=30)
        button.clicked.connect(handler)
        layout.addWidget(button)
        return holder

    def _repair_missing(self) -> None:
        library = ctx().library
        missing = library.missing_tracks()
        if not missing:
            self._toast("没有发现失效文件", "success")
            return
        answer = QMessageBox.question(
            self,
            "修复失效文件",
            f"发现 {len(missing)} 首歌曲的文件已不存在。\n\n"
            "选择一个文件夹，程序会先按原来的相对路径寻找，再按文件名搜索并重新关联。",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        new_root = QFileDialog.getExistingDirectory(self, "选择歌曲现在所在的文件夹")
        if not new_root:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            moved = 0
            for folder in list(self.settings.get("library.folders", []) or []):
                count, _still = library.relocate_folder(str(folder), new_root)
                moved += count
            by_name, still = library.relocate_by_name(new_root)
            moved += by_name
            folders = [str(f) for f in (self.settings.get("library.folders", []) or [])]
            if new_root not in folders:
                folders.append(new_root)
            self.settings.set("library.folders", folders)
        except Exception as exc:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            log_exception("修复失效文件失败", exc)
            self._toast("修复失败，请查看日志", "error")
            return
        QApplication.restoreOverrideCursor()
        if moved:
            self._toast(f"已重新关联 {moved} 首歌曲" + (f"，仍有 {still} 首未找到" if still else ""), "success")
        else:
            self._toast(f"没有找到可关联的文件，仍有 {still} 首失效", "warning")

    def _rescan(self) -> None:
        folders = list(self.settings.get("library.folders", []) or [])
        if not folders:
            self._toast("还没有添加扫描目录", "info")
            return
        ctx().library.scan(folders, force=True)
        self._toast("已开始重新扫描音乐库", "info")

    # ----------------------------------------------------------------- online
    def _build_online(self, column: QVBoxLayout) -> None:
        client = ctx().client
        card = SettingsCard("在线音源", "由社区音源插件提供，搜索与播放能力以实际接口为准")
        self._source_rows = QVBoxLayout()
        self._source_rows.setContentsMargins(0, 0, 0, 0)
        self._source_rows.setSpacing(2)
        card.add(self._source_container())
        column.addWidget(card)

        manager = SettingsCard("音源管理", "安装 MusicFree 兼容插件、订阅或批量导入")
        for icon_name, title, hint, handler in (
            ("plus", "添加音源", "安装本地的 .js / .json 插件，只保存在用户数据目录", self._add_source),
            ("cloud", "从链接添加", "粘贴插件地址，程序会下载并校验大小", self._add_source_url),
            ("download", "导入订阅", "粘贴 MusicFree 订阅地址，一次导入其中的全部音源", self._import_subscription),
            ("refresh", "检查订阅更新", "重新读取已导入的订阅，只安装新增的音源", self._check_subscription),
            ("folder", "批量导入", "选择文件夹，一次性安装里面的插件（不递归子目录）", self._import_source_folder),
        ):
            manager.add(ActionCard(icon_name, title, hint, handler))
        restore = QPushButton("恢复内置音源")
        restore.setObjectName("LinkButton")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.setFixedHeight(theme().scaled(30, factor=0.6))
        restore.clicked.connect(self._restore_sources)
        manager.add(restore)
        column.addWidget(manager)

        card = SettingsCard("网络", "")
        card.add_row(self._row(
            "请求超时", "", self._slider("online.timeout_s", 8, 45, default=22, formatter=lambda v: f"{int(v)} 秒")
        ))
        card.add_row(self._row("跨音源回退", "当前音源无法播放时，自动在其他音源中查找同一首歌", self._toggle("online.cross_source_fallback", True)))
        card.add_row(self._row("刷新音源列表", "重新加载插件目录，安装新音源后使用", self._action_button("刷新", "refresh", self._reload_sources)))
        column.addWidget(card)
        # The Node runtime reports its plugin list asynchronously; subscribe once so
        # the rows appear as soon as the sources arrive instead of staying empty
        # until the user presses 刷新 (they used to see "尚未加载音源插件" forever).
        if not getattr(self, "_sources_wired", False):
            self._sources_wired = True
            try:
                client.sources_changed.connect(self._on_sources_changed)
                client.ensure_started()
            except Exception:  # noqa: BLE001
                log_exception("订阅在线音源列表失败", None)
        self._fill_sources()

    def _on_sources_changed(self, sources) -> None:
        if not hasattr(self, "_source_rows"):
            return
        self._fill_sources()

    def _source_container(self) -> QWidget:
        holder = QWidget()
        holder.setLayout(self._source_rows)
        return holder

    def _fill_sources(self) -> None:
        while self._source_rows.count():
            item = self._source_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # deleteLater() alone leaves the old rows painted until the
                # event loop catches up, so collapsing looked like a flicker of
                # both lists at once.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        try:
            sources = build_sources(ctx().client.sources)
        except Exception as exc:  # noqa: BLE001
            # Never swallow this: a wiring mistake here used to render an empty
            # "尚未加载音源插件" card forever, with the real error hidden.
            log_exception("读取在线音源列表失败", exc)
            sources = []
        if not sources:
            note = QLabel("尚未加载音源插件，点击「刷新」重试")
            note.setFont(theme().font(9.2))
            note.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.5)};")
            self._source_rows.addWidget(note)
            return
        # Several community plugins can share a display name (two "QQ音乐"
        # builds, for example); disambiguate them with a short id suffix.
        label_counts: dict[str, int] = {}
        for source in sources:
            label_counts[source.label] = label_counts.get(source.label, 0) + 1
        expanded = bool(self.settings.get("online.sources_expanded", False))
        visible, hidden = source_window(len(sources), expanded)
        for source in sources[:visible]:
            label = source.label
            if label_counts.get(label, 0) > 1:
                label = f"{label} · {source.id[-4:]}"
            enabled = bool((self.settings.get("online.enabled_sources", {}) or {}).get(source.id, source.enabled))
            state = []
            if source.can_play:
                state.append("播放")
            if source.can_lyrics:
                state.append("歌词")
            if source.can_download:
                state.append("下载")
            detail = " · ".join(state) if state else "仅搜索"
            if source.problem:
                detail = source.problem
            else:
                from ...online import health

                health_text = health.summary(source.id)
                if health_text:
                    detail = f"{detail} · {health_text}"
            switch = ToggleSwitch(enabled)
            def apply(value: bool, sid: str = source.id) -> None:
                mapping = dict(self.settings.get("online.enabled_sources", {}) or {})
                mapping[sid] = bool(value)
                self.settings.set("online.enabled_sources", mapping)
            switch.toggled.connect(apply)
            remove = IconButton("trash", size=28, icon_size=15, tooltip="删除该音源")
            remove.clicked.connect(lambda _=False, sid=source.id, name=label: self._remove_source(sid, name))
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.addWidget(switch)
            row.addWidget(remove)
            self._source_rows.addWidget(SettingRow(label, detail, control=holder))

        if hidden > 0 or expanded:
            label = "收起音源列表" if expanded else f"展开全部音源（还有 {hidden} 个）"
            hint = (
                "只显示前 %d 个，展开后可逐个启用或删除" % SOURCES_COLLAPSED_VISIBLE
                if not expanded
                else f"共 {len(sources)} 个音源"
            )
            toggle = TextButton(
                "收起" if expanded else "展开全部",
                icon_name="chevron_up" if expanded else "chevron_down",
                size=28,
            )
            toggle.clicked.connect(self._toggle_sources_expanded)
            self._source_rows.addWidget(SettingRow(label, hint, control=toggle))

    def _toggle_sources_expanded(self) -> None:
        expanded = bool(self.settings.get("online.sources_expanded", False))
        self.settings.set("online.sources_expanded", not expanded)
        self._fill_sources()

    def _add_source(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择音源插件（可多选）", "", "MusicFree 插件 (*.js *.json)"
        )
        if paths:
            self._install_source_files(paths)

    def _import_source_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择插件文件夹", "")
        if not folder:
            return
        from ...online.registry import collect_plugin_files

        files = collect_plugin_files(folder)
        if not files:
            self._toast("该文件夹里没有 .js / .json 插件", "warning")
            return
        self._install_source_files([str(path) for path in files])

    def _check_subscription(self) -> None:
        url = str(self.settings.get("online.subscription_url", "") or "").strip()
        if not url:
            QInputDialog_msg = "先用「导入订阅」添加一次订阅，之后就能在这里检查更新"
            self._toast(QInputDialog_msg, "info")
            return
        self._toast("正在检查订阅更新…", "info")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = registry().preview_subscription(url)
        except RegistryError as exc:
            QApplication.restoreOverrideCursor()
            self._toast(str(exc), "error")
            return
        except Exception as exc:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            log_exception("检查订阅失败", exc)
            self._toast("检查订阅失败，请查看日志", "error")
            return
        QApplication.restoreOverrideCursor()
        new = int(result.get("new", 0))
        if new <= 0:
            self._toast(f"订阅里的 {result.get('total', 0)} 个音源都已安装", "success")
            return
        names = "、".join(result.get("names", [])[:4])
        answer = QMessageBox.question(
            self,
            "发现订阅更新",
            f"订阅中有 {new} 个新音源（共 {result.get('total', 0)} 个）：\n{names}\n\n现在安装？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._import_subscription_url(url)

    def _install_source_files(self, paths: list[str]) -> None:
        from ...online.registry import registry

        try:
            report = registry().install_many(paths)
        except Exception as exc:  # noqa: BLE001
            log_exception("批量安装音源失败", exc)
            self._toast("批量安装音源失败，请查看日志", "error")
            return
        if report.installed:
            self._toast(report.summary(), "success")
        elif report.duplicates and not report.failed:
            self._toast("这些音源已经安装过了", "info")
        if report.failed:
            QMessageBox.warning(self, "部分音源安装失败", report.failure_text())
        self._reload_sources()

    def _install_source_file(self, path: str) -> None:
        """Install a MusicFree-compatible plugin the user picked from disk."""
        try:
            from ...online.registry import RegistryError, registry

            entry = registry().install_file(path)
        except RegistryError as exc:
            self._toast(str(exc), "error")
            return
        except Exception as exc:  # noqa: BLE001
            log_exception("安装音源失败", exc)
            self._toast("安装音源失败，请查看日志", "error")
            return
        self._toast(f"已安装音源：{entry.get('name', '')}", "success")
        self._reload_sources()

    def _import_subscription(self) -> None:
        from ...online.registry import RegistryError, registry

        url, ok = QInputDialog.getText(
            self,
            "导入音源订阅",
            "MusicFree 订阅地址（通常是 mf.json）：",
            text=getattr(self, "_last_subscription", ""),
        )
        url = (url or "").strip()
        if not ok or not url:
            return
        self._last_subscription = url
        self._import_subscription_url(url)

    def _import_subscription_url(self, url: str) -> None:
        from ...online.registry import RegistryError, registry

        url = (url or "").strip()
        if not url:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = registry().install_subscription(url)
            self.settings.set("online.subscription_url", url)
        except RegistryError as exc:
            QMessageBox.warning(self, "导入订阅失败", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures
            log_exception("导入音源订阅失败", exc)
            QMessageBox.warning(self, "导入订阅失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._toast(report.summary(), "success" if report.installed else "info")
        if report.failed:
            QMessageBox.warning(self, "部分音源导入失败", report.failure_text())
        self._reload_sources()

    def _add_source_url(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        url, ok = QInputDialog.getText(self, "从链接添加音源", "音源地址（http/https）：")
        if not ok or not url.strip():
            return
        try:
            from ...online.registry import RegistryError, registry

            entry = registry().install_url(url.strip())
        except RegistryError as exc:
            self._toast(str(exc), "error")
            return
        except Exception as exc:  # noqa: BLE001
            log_exception("从链接安装音源失败", exc)
            self._toast("安装音源失败，请查看日志", "error")
            return
        self._toast(f"已安装音源：{entry.get('name') or entry.get('id')}", "success")
        self._reload_sources()

    def _restore_sources(self) -> None:
        try:
            from ...online.registry import registry

            added = registry().restore_bundled()
        except Exception as exc:  # noqa: BLE001
            log_exception("恢复内置音源失败", exc)
            self._toast("恢复失败，请查看日志", "error")
            return
        self._toast(f"已恢复 {added} 个内置音源" if added else "内置音源没有缺失", "success")
        self._reload_sources()

    def _remove_source(self, source_id: str, name: str) -> None:
        answer = QMessageBox.question(
            self,
            "删除音源",
            f"确定要删除音源「{name}」吗？插件文件也会一并删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            from ...online.registry import registry

            registry().remove(source_id)
        except Exception as exc:  # noqa: BLE001
            log_exception("删除音源失败", exc)
            self._toast(f"删除失败：{exc}", "error")
            return
        self._toast(f"已删除音源：{name}", "success")
        self._reload_sources()

    def _reload_sources(self) -> None:
        try:
            ctx().client.ensure_started()
            ctx().client.refresh_sources()
            self._toast("正在刷新音源列表…", "info")
        except Exception as exc:  # noqa: BLE001
            log_exception("刷新音源失败", exc)

    # ------------------------------------------------------------------ cache
    def _build_cache(self, column: QVBoxLayout) -> None:
        card = SettingsCard("缓存", "在线播放的音频与封面会缓存在本地，可随时清理")
        self._cache_label = QLabel("正在统计…")
        self._cache_label.setFont(theme().font(9.4))
        self._cache_label.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.68)};")
        card.add(self._cache_label)
        self._refresh_cache_label()
        card.add_row(self._row(
            "缓存上限", "超过上限时自动清理最久未使用的数据",
            self._slider("cache.max_mb", 256, 8192, default=2048, formatter=lambda v: f"{v / 1024:.1f} GB"),
        ))
        card.add_row(self._row("清理缓存", "删除全部在线音频缓存，不影响收藏与歌单", self._action_button("清理", "trash", self._clear_cache)))
        card.add_row(self._row("修复缓存索引", "检测损坏的缓存文件并重建索引", self._action_button("修复", "refresh", self._repair_cache)))
        column.addWidget(card)

        card = SettingsCard("下载", "仅对明确支持下载的音源可用")
        field = SettingField(str(self.settings.get("downloads.dir", "") or str(paths.downloads_dir())), mode="folder")
        def change_dir(text: str) -> None:
            self.settings.set("downloads.dir", text)
        field.text_changed.connect(change_dir)
        card.add_row(self._row("下载目录", "下载的音频文件保存位置", field))
        if hasattr(app_ctx := ctx(), "downloads") and app_ctx.downloads is not None:
            done = app_ctx.downloads.count_done()
            card.add_row(self._row(
                "已下载歌曲", f"共 {done} 首，保存在上方目录",
                self._action_button("打开文件夹", "folder", app_ctx.downloads.open_folder),
            ))
        card.add_row(self._row(
            "下载音质", "",
            self._combo("downloads.quality", [("标准", "standard"), ("较高", "higher"), ("极高", "exhigh"), ("无损", "lossless")], "higher"),
        ))
        column.addWidget(card)

    def _refresh_cache_label(self) -> None:
        try:
            stats = ctx().cache.stats()
            self._cache_label.setText(stats.summary_text() if hasattr(stats, "summary_text") else ctx().cache.summary_text())
        except Exception as exc:  # noqa: BLE001
            self._cache_label.setText("暂时无法读取缓存信息")
            log_exception("读取缓存信息失败", exc)

    def _clear_cache(self) -> None:
        try:
            ctx().cache.clear_all()
            self._refresh_cache_label()
            self._toast("缓存已清理", "success")
        except Exception as exc:  # noqa: BLE001
            log_exception("清理缓存失败", exc)
            self._toast("清理缓存失败，请查看日志", "error")

    def _repair_cache(self) -> None:
        try:
            report = ctx().cache.repair()
            self._refresh_cache_label()
            self._toast(f"已移除 {report.removed} 个损坏文件", "success")
        except Exception as exc:  # noqa: BLE001
            log_exception("修复缓存失败", exc)

    # ------------------------------------------------------------------ about
    def _build_about(self, column: QVBoxLayout) -> None:
        from ...version import VERSION, BUILD_CHANNEL, APP_ID

        card = SettingsCard("HushPlayer", "现代 Windows 桌面音乐播放器")
        logo = QLabel("H")
        logo.setFixedSize(56, 56)
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(theme().font(26, 700))
        logo.setStyleSheet(
            f"color: #FFFFFF; background: {theme().palette.accent}; border-radius: 14px;"
        )
        official = brand.logo_pixmap(56, theme().mode)
        if official is not None:
            logo.setText("")
            logo.setStyleSheet("background: transparent;")
            logo.setPixmap(official)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(14)
        layout.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel("HushPlayer")
        name.setFont(theme().font(15, 700))
        name.setStyleSheet(f"color:{theme().palette.text};")
        version = QLabel(f"版本 {VERSION} · {BUILD_CHANNEL}")
        version.setFont(theme().font(9.2))
        version.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.55)};")
        text.addWidget(name)
        text.addWidget(version)
        layout.addLayout(text, 1)
        card.add(row)
        column.addWidget(card)

        card = SettingsCard("运行环境", "")
        items = [
            ("Python", sys.version.split(" ")[0]),
            ("PySide6", self._pyside_version()),
            ("系统", f"{platform.system()} {platform.release()}"),
            ("数据目录", str(paths.data_dir())),
            ("应用标识", APP_ID),
        ]
        for key, value in items:
            card.add(self._info_row(key, value))
        column.addWidget(card)

        card = SettingsCard("诊断与更新", "")
        card.add_row(self._row("检查更新", "获取最新版本信息", self._action_button("检查", "cloud", self._check_updates)))
        card.add_row(self._row("打开日志文件夹", "反馈问题时请附上日志文件", self._action_button("打开", "folder", self._open_logs)))
        card.add_row(self._row("打开数据目录", "收藏、歌单与设置保存在此", self._action_button("打开", "folder", self._open_data)))
        column.addWidget(card)

        card = SettingsCard("致谢", "")
        thanks = QLabel(
            "音频回放：Qt Multimedia（FFmpeg）\n"
            "元数据解析：Mutagen\n"
            "在线音源：社区 MusicFree 兼容插件运行于本地 Node.js 运行时\n"
            "歌词匹配：LRCLIB\n"
            "HushPlayer 与上述项目没有隶属关系，第三方组件遵循各自许可证。"
        )
        thanks.setFont(theme().font(9.0))
        thanks.setWordWrap(True)
        thanks.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.55)};")
        card.add(thanks)
        column.addWidget(card)

    def _info_row(self, key: str, value: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(16)
        label = QLabel(key)
        label.setFont(theme().font(9.2))
        label.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.5)};")
        label.setFixedWidth(90)
        text = QLabel(value)
        text.setFont(theme().font(9.2))
        text.setStyleSheet(f"color:{css_rgba(theme().palette.text, 0.85)};")
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # A long data path must not widen the whole card; let it clip and keep
        # the full value discoverable via the tooltip.
        text.setToolTip(value)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(label)
        layout.addWidget(text, 1)
        return row

    def _pyside_version(self) -> str:
        try:
            import PySide6

            return PySide6.__version__
        except Exception:  # noqa: BLE001
            return "未知"

    def _check_updates(self) -> None:
        from ...services.updater import UpdateService

        self._toast("正在检查更新…", "info")
        existing = getattr(ctx(), "updater", None)
        service = existing or UpdateService(self)
        if existing is None:
            self._update_service = service

        def on_checked(info) -> None:
            if not info.available:
                self._toast(f"当前已是最新版本（{info.current}）", "info")
                return
            self._toast(f"发现新版本 {info.version}", "success")
            if info.url:
                from PySide6.QtWidgets import QMessageBox

                box = QMessageBox(self.window())
                box.setWindowTitle("发现新版本")
                box.setText(f"HushPlayer {info.version} 已发布")
                detail = info.notes or "点击「打开下载页」前往发布页面。"
                box.setInformativeText(detail[:600])
                open_button = box.addButton("打开下载页", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() is open_button:
                    import webbrowser

                    webbrowser.open(info.url)

        def on_failed(message: str) -> None:
            self._toast(f"检查更新失败：{message}", "error")

        service.checked.connect(on_checked)
        service.failed.connect(on_failed)
        if not service.check_async():
            pass

    def _open_logs(self) -> None:
        self._open_path(str(paths.logs_dir()))

    def _open_data(self) -> None:
        self._open_path(str(paths.data_dir()))

    def _open_path(self, path: str) -> None:
        try:
            os.startfile(path)  # noqa: S606
        except Exception as exc:  # noqa: BLE001
            log_exception("打开文件夹失败", exc)

    def _toast(self, text: str, kind: str) -> None:
        window = ctx().window
        if window is not None:
            window.toast(text, kind)

    # -------------------------------------------------------------- lifecycle
    def _show_section(self, index: int) -> None:
        key = SECTIONS[index][0]
        self._section(key)
        self._stack.setCurrentWidget(self._sections[key])
        self._initial_section = key

    def on_show(self, payload: object = None) -> None:
        super().on_show(payload)
        if isinstance(payload, str) and payload:
            for index, (key, _label, _icon) in enumerate(SECTIONS):
                if key == payload:
                    self._nav.set_current(index)
                    self._show_section(index)
                    break
            else:
                self._show_section(0)
        else:
            index = 0
            for i, (key, _l, _i) in enumerate(SECTIONS):
                if key == self._initial_section:
                    index = i
                    break
            self._nav.set_current(index)
            self._show_section(index)

    def refresh_theme(self) -> None:
        super().refresh_theme()
        # BUG-08: cards and rows bake their colours into inline stylesheets at
        # construction time, so they must be told to re-read the palette when the
        # theme changes while the page is alive (they used to stay white).
        for section in self._sections.values():
            self._refresh_tree(section)
            section.update()
        self._nav.update()

    def _refresh_tree(self, root) -> None:
        for child in root.findChildren(QWidget):
            refresh = getattr(child, "refresh_theme", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:  # noqa: BLE001 - never let a card break theming
                    pass
