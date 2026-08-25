"""Formal V4 immersive lyrics page sharing V2 playback and lyric adapters."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QSlider, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.legacy_settings_bridge import LegacySettingsBridge
from app.ui_v2.adapters.legacy_settings_bridge import SettingsBridgeError
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.artwork_atmosphere import ArtworkAtmosphere, ReadabilityOverlay
from app.ui_v2.widgets.immersive_controls import ImmersiveControls
from app.ui_v2.widgets.immersive_settings_panel import ImmersiveSettingsPanel
from app.ui_v2.widgets.immersive_track_identity import ImmersiveTrackIdentity
from app.ui_v2.widgets.immersive_queue_panel import ImmersiveQueuePanel
from app.ui_v2.widgets.immersive_overlay import ImmersiveOverlayHost
from app.ui_v2.widgets.lyrics_quick_settings_panel import LyricsQuickSettingsFloatingPanel
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2
from app.ui_v2.widgets.lyrics_state_view import LyricsStateView
from app.ui_v2.pages.now_playing_page import NowPlayingPage
from app.ui_v2.theme.icons import FLUENT_IMMERSIVE_ASSETS, fluent_immersive_interactive_icon, icon


@dataclass(slots=True)
class _LyricProtection:
    """Settings compatibility state; the canvas remains free of row overlays."""

    enabled: bool = True
    strength: int = 58
    paint_profile: str = "soft_text_shadow"
    is_row_bound: bool = False


class _ImmersiveHeader(QFrame):
    """Drag surface for the frameless host while normal chrome is hidden."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self.window().isMaximized():
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = self.window().pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and self._window_origin is not None:
            self.window().move(self._window_origin + event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self._window_origin = None
        super().mouseReleaseEvent(event)


class ImmersiveLyricsPage(QWidget):
    """A cached V4 immersive surface, never a second top-level window."""

    fullscreen_requested = Signal(bool)
    immersive_exit_requested = Signal()
    transparency_mode_changed = Signal(bool)
    options_changed = Signal(object)
    mode_changed = Signal(str)

    def __init__(
        self,
        lyrics: LyricsAdapter,
        playback: PlaybackAdapter,
        theme: Theme,
        options: ImmersiveLyricsOptions | None = None,
        parent: QWidget | None = None,
        settings_bridge: LegacySettingsBridge | None = None,
        settings_apply_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.lyrics_adapter = lyrics
        self.playback_adapter = playback
        self.options = options or ImmersiveLyricsOptions(theme=theme.mode)
        self.settings_bridge = settings_bridge
        self._settings_apply_callback = settings_apply_callback
        self._theme = theme
        self._host_fullscreen = False
        self._active = False
        self._layout_band = "wide"
        self._auto_hide_controls = True
        self._reduce_motion = False
        self._controls_interacting = False
        self._controls_hovered = False
        self._applying_options = False
        self._control_surface_opacity = self.options.control_surface_opacity
        self._text_protection = self.options.text_protection_mode
        self._mode = "lyrics"
        self.lyric_protection = _LyricProtection(
            self.options.lyrics_protection_enabled, self.options.protection_strength
        )
        self.setObjectName("immersiveLyricsPage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.background = ArtworkAtmosphere(theme, self)
        self.readability_overlay = ReadabilityOverlay(theme, self)
        self.header = self._build_header(theme)
        self.content_stack = QStackedWidget(self)
        self.content = QWidget(self.content_stack)
        self.content.setObjectName("immersiveLyricsContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content.setAutoFillBackground(False)
        self.identity_column = QWidget(self.content)
        self.identity_column.setObjectName("immersiveIdentityColumn")
        self.identity_column.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.identity = ImmersiveTrackIdentity(theme, self.identity_column)
        self.controls = ImmersiveControls(theme, self)
        self._identity_layout = QVBoxLayout(self.identity_column)
        self._identity_layout.setContentsMargins(0, 0, 0, 0)
        self._identity_layout.setSpacing(18)
        self._identity_layout.addStretch(1)
        self._identity_layout.addWidget(self.identity)
        self._identity_layout.addStretch(1)
        self.canvas = LyricsCanvasV2(theme, self.content)
        self.canvas.set_mode("immersive")
        self.lyrics_view = self.canvas  # Public semantic alias: one visual surface, no scroll list.
        self.lyrics_state_view = LyricsStateView(theme, self.content)
        self.lyrics_state_view.hide()
        self.lyrics_state_view.retry_requested.connect(self.lyrics_adapter.retry)
        self.lyrics_state_view.source_button.hide()
        self._content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(54)
        self._content_layout.addWidget(self.identity_column, 36)
        self._content_layout.addWidget(self.canvas, 64)
        self.content_stack.addWidget(self.content)
        self.now_playing_page = NowPlayingPage(playback, theme, self.content_stack)
        self.content_stack.addWidget(self.now_playing_page)
        self.lyrics_page = self.content
        self.now_playing = self.now_playing_page
        self.overlay_host = ImmersiveOverlayHost(self)
        self.settings_panel = LyricsQuickSettingsFloatingPanel(
            theme,
            self.overlay_host,
            settings_bridge=settings_bridge,
        )
        self.queue_panel = ImmersiveQueuePanel(playback, theme, self.overlay_host)
        self.queue_panel.hide()
        self.settings_panel.hide()
        self._controls_hide_timer = QTimer(self)
        self._controls_hide_timer.setSingleShot(True)
        self._controls_hide_timer.setInterval(2600)
        self._controls_hide_timer.timeout.connect(self.hide_controls_preview)
        self._connect_components()
        self._connect_adapters()
        self.apply_options()
        self._on_document_changed(lyrics.document)
        self._on_state_changed(lyrics.state)
        self._on_active_line_changed(lyrics.active_line)
        self._on_display_options_changed(lyrics.display_options)
        self._apply_responsive_layout()

    def _build_header(self, theme: Theme) -> QFrame:
        header = _ImmersiveHeader(self)
        header.setObjectName("immersiveHeader")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(6)
        self.header_back_button = self._header_button("back", "返回普通页面")
        self.header_now_playing = self._header_mode_button("正在播放", "正在播放", "now_playing", 112)
        self.header_lyrics = self._header_mode_button("歌词", "歌词", "lyrics", 82)
        self.header_translation_button = self._header_toggle_button("翻译", "显示或隐藏翻译", 64)
        self.header_romanization_button = self._header_toggle_button("罗马音", "显示或隐藏罗马音", 76)
        self.header_fullscreen_button = self._header_text_button("全屏", "进入全屏（F11）", 60)
        self.header_back_button.clicked.connect(self.immersive_exit_requested)
        self.header_now_playing.clicked.connect(lambda: self.mode_changed.emit("now_playing"))
        self.header_lyrics.clicked.connect(lambda: self.mode_changed.emit("lyrics"))
        self.header_translation_button.toggled.connect(self.set_translation_visible)
        self.header_romanization_button.toggled.connect(self.set_romanization_visible)
        self.header_fullscreen_button.clicked.connect(self.toggle_fullscreen)
        layout.addWidget(self.header_back_button)
        layout.addStretch(1)
        layout.addWidget(self.header_now_playing)
        layout.addSpacing(24)
        layout.addWidget(self.header_lyrics)
        layout.addSpacing(8)
        layout.addWidget(self.header_translation_button)
        layout.addWidget(self.header_romanization_button)
        layout.addSpacing(8)
        layout.addWidget(self.header_fullscreen_button)
        self._window_buttons: list[QToolButton] = []
        for name, tip, callback in (
            ("window_minimize", "最小化", lambda: self.window().showMinimized()),
            ("window_maximize", "最大化", self._toggle_host_maximized),
            ("window_close", "关闭", lambda: self.window().close()),
        ):
            button = self._header_button(name, tip)
            button.clicked.connect(callback)
            self._window_buttons.append(button)
            layout.addWidget(button)
        self.header = header
        self._style_header(theme)
        return header

    def _header_button(self, name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(icon(name, self._theme))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(36, 36)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _header_mode_button(self, text: str, tooltip: str, icon_name: str, width: int) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("immersiveModeButton")
        button.setText(text)
        button.setIcon(fluent_immersive_interactive_icon(icon_name, self._theme, 18))
        button.setIconSize(QSize(18, 18))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(True)
        button.setFixedSize(width, 36)
        button.setToolTip(tooltip)
        button.setProperty("fluentIconFamily", "fluent_immersive")
        button.setProperty("fluentIconName", icon_name)
        button.setProperty("fluentIconFile", FLUENT_IMMERSIVE_ASSETS[icon_name])
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _header_toggle_button(self, text: str, tooltip: str, width: int) -> QToolButton:
        button = self._header_text_button(text, tooltip, width)
        button.setObjectName("immersiveToggleButton")
        button.setCheckable(True)
        return button

    def _header_text_button(self, text: str, tooltip: str, width: int) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("immersiveTextButton")
        button.setText(text)
        button.setFixedSize(width, 36)
        button.setToolTip(tooltip)
        button.setAccessibleName(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _style_header(self, theme: Theme) -> None:
        colors = theme.colors
        self.header.setStyleSheet(
            f"QFrame#immersiveHeader {{ background: transparent; }}"
            f"QToolButton {{ border: 0; border-radius: 18px; background: transparent; }}"
            f"QToolButton:hover {{ background: {colors.surface_hover}; }}"
            f"QToolButton#immersiveModeButton {{ border: 0; border-bottom: 2px solid transparent; "
            f"border-radius: 0px; background: transparent; padding: 0 0 3px 0; color: {colors.text_secondary}; }}"
            f"QToolButton#immersiveModeButton:hover {{ background: transparent; color: {colors.text_primary}; }}"
            f"QToolButton#immersiveModeButton:checked {{ background: transparent; color: {colors.text_primary}; "
            f"border-bottom: 2px solid {colors.accent}; }}"
            f"QToolButton#immersiveModeButton:pressed {{ background: transparent; }}"
            f"QToolButton#immersiveToggleButton, QToolButton#immersiveTextButton {{ min-width: 0; "
            f"padding: 0 8px; border: 1px solid transparent; border-radius: 16px; background: transparent; "
            f"color: {colors.text_secondary}; }}"
            f"QToolButton#immersiveToggleButton:hover, QToolButton#immersiveTextButton:hover {{ "
            f"background: {colors.surface_hover}; color: {colors.text_primary}; }}"
            f"QToolButton#immersiveToggleButton:checked {{ background: {colors.selected_background}; "
            f"border-color: {colors.border}; color: {colors.text_primary}; }}"
            f"QToolButton#immersiveToggleButton:pressed, QToolButton#immersiveTextButton:pressed {{ "
            f"background: {colors.surface_pressed}; }}"
            f"QToolButton#immersiveModeButton[hushKeyboardFocus=\"true\"]:focus {{ background: transparent; border-bottom: 2px solid {colors.focus_ring}; }}"
        )
        for name, button in (("back", self.header_back_button), ("window_minimize", self._window_buttons[0]), ("window_maximize", self._window_buttons[1]), ("window_close", self._window_buttons[2])):
            button.setIcon(icon(name, theme, "normal"))
        self.header_now_playing.setIcon(fluent_immersive_interactive_icon("now_playing", theme, 18))
        self.header_lyrics.setIcon(fluent_immersive_interactive_icon("lyrics", theme, 18))
        self._sync_mode_buttons()
        self._sync_fullscreen_button()

    def _toggle_host_maximized(self) -> None:
        window = self.window()
        window.showNormal() if window.isMaximized() else window.showMaximized()

    def set_mode(self, mode: str) -> None:
        mode = "now_playing" if str(mode) in {"now_playing", "now-playing"} else "lyrics"
        self._mode = mode
        self.content_stack.setCurrentWidget(self.now_playing_page if mode == "now_playing" else self.content)
        self.controls.show()
        self._sync_mode_buttons()
        self._on_state_changed(self.lyrics_adapter.state)
        self._apply_responsive_layout()

    def _place_controls_for_mode(self) -> None:
        """Keep one stable control panel below either content mode."""

        self.controls.show()

    @property
    def mode(self) -> str:
        return self._mode

    def _sync_mode_buttons(self) -> None:
        if not hasattr(self, "header_now_playing"):
            return
        self.header_now_playing.setChecked(self._mode == "now_playing")
        self.header_lyrics.setChecked(self._mode == "lyrics")
        self._sync_display_buttons()

    def _sync_display_buttons(self) -> None:
        options = self.lyrics_adapter.display_options
        for button, value in (
            (self.header_translation_button, options.get("translation", True)),
            (self.header_romanization_button, options.get("romanization", False)),
        ):
            previous = button.blockSignals(True)
            button.setChecked(bool(value))
            button.blockSignals(previous)

    def toggle_queue_panel(self) -> None:
        if self.queue_panel.isVisible():
            self.hide_queue_panel()
        else:
            self.show_queue_panel()

    def show_queue_panel(self) -> None:
        self.hide_settings_panel()
        self.queue_panel.show()
        self.queue_panel.raise_()
        self._apply_responsive_layout()

    def hide_queue_panel(self) -> None:
        self.queue_panel.hide()
        self._apply_responsive_layout()

    def _on_overlay_background_pressed(self) -> None:
        """Close the active floating panel when its host receives an outside click."""

        if self.settings_panel.isVisible():
            self.hide_settings_panel()
        elif self.queue_panel.isVisible():
            self.hide_queue_panel()

    @property
    def queue_panel_visible(self) -> bool:
        return self.queue_panel.isVisible()

    @property
    def queue_model(self):
        """Compatibility view exposing the single adapter-owned queue."""

        return self.playback_adapter

    @property
    def document(self) -> LyricsDocument | None:
        return self.lyrics_adapter.document

    @property
    def is_fullscreen(self) -> bool:
        return self._host_fullscreen

    @property
    def background_mode(self) -> str:
        return self.options.background_mode

    @property
    def background_opacity_percent(self) -> int:
        return self.options.background_opacity

    @property
    def overlay_strength(self) -> int:
        return self.options.overlay_strength

    @property
    def control_surface_opacity(self) -> int:
        return self._control_surface_opacity

    @property
    def auto_hide_controls(self) -> bool:
        return self._auto_hide_controls

    @property
    def controls_visible(self) -> bool:
        return self.controls.isVisible()

    @property
    def root_background_alpha(self) -> int:
        return 0 if self.options.background_mode == "transparent" else 255

    @property
    def content_layer_alpha(self) -> int:
        return 255

    def _connect_components(self) -> None:
        self.controls.bind_playback(self.playback_adapter)
        self.controls.more_button.clicked.connect(self.toggle_settings_panel)
        self.controls.queue_requested.connect(self.show_queue_panel)
        self.controls.lyrics_requested.connect(lambda: self.mode_changed.emit("lyrics"))
        self.overlay_host.background_pressed.connect(self._on_overlay_background_pressed)
        self.queue_panel.closed.connect(self.hide_queue_panel)
        self.controls.interaction_started.connect(self._begin_controls_interaction)
        self.controls.interaction_finished.connect(self._end_controls_interaction)
        self.canvas.seek_requested.connect(self.lyrics_adapter.seek_to_line)
        self.lyrics_adapter.seek_requested.connect(
            lambda position: self.canvas.set_playback_position(position, force=True)
        )
        self.now_playing_page.queue_requested.connect(self.show_queue_panel)
        self.now_playing_page.lyrics_requested.connect(lambda: self.mode_changed.emit("lyrics"))
        self.now_playing_page.more_requested.connect(self.show_settings_panel)
        self.settings_panel.changed.connect(self._apply_panel_options)
        self.settings_panel.exit_requested.connect(self.immersive_exit_requested)
        self.settings_panel.closed.connect(self._on_settings_panel_closed)
        self.settings_panel.save_requested.connect(self._save_quick_settings)
        self.settings_panel.cancel_requested.connect(self._cancel_quick_settings)
        self.settings_panel.reset_requested.connect(self._reset_quick_settings)
        tracked_widgets = [self, self.content, self.canvas, self.controls, self.header]
        tracked_widgets.extend(self.findChildren(QWidget))
        seen_widgets: set[int] = set()
        for widget in tracked_widgets:
            if id(widget) in seen_widgets:
                continue
            seen_widgets.add(id(widget))
            widget.setMouseTracking(True)
            widget.installEventFilter(self)
        self._fullscreen_action = QAction(self)
        self._fullscreen_action.setShortcut("F11")
        self._fullscreen_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self._fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self._fullscreen_action)

    def _connect_adapters(self) -> None:
        self.lyrics_adapter.document_changed.connect(self._on_document_changed)
        self.lyrics_adapter.state_changed.connect(self._on_state_changed)
        self.lyrics_adapter.active_line_changed.connect(self._on_active_line_changed)
        self.lyrics_adapter.position_changed.connect(self.canvas.set_playback_position)
        self.lyrics_adapter.active_segment_changed.connect(self._on_active_segment_changed)
        self.lyrics_adapter.display_options_changed.connect(self._on_display_options_changed)
        self.playback_adapter.playing_changed.connect(self._on_playing_changed)
        self.canvas.set_playback_position(self.playback_adapter.state.position_ms)
        self.canvas.set_playback_active(self.playback_adapter.state.is_playing)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._style_header(theme)
        self.background.set_theme(theme)
        self.readability_overlay.set_theme(theme)
        self.identity.set_theme(theme)
        self.canvas.set_theme(theme)
        self.lyrics_state_view.set_theme(theme)
        self.controls.set_theme(theme)
        self.now_playing_page.set_theme(theme)
        self.queue_panel.set_theme(theme)
        self.settings_panel.set_theme(theme)
        self.options.theme = theme.mode
        self._sync_options()

    def set_theme_mode(self, mode: str) -> None:
        self.set_theme(get_theme("light" if mode == "light" else "dark"))

    def set_responsive_reference_width(self, width: int) -> None:
        self._apply_responsive_layout(width)

    def set_read_only(self, read_only: bool) -> None:
        self.now_playing_page.set_read_only(read_only)

    def set_translation_visible(self, visible: bool) -> None:
        if bool(self.lyrics_adapter.display_options["translation"]) != bool(visible):
            self.lyrics_adapter.toggle_translation()
        self._sync_display_buttons()

    def set_romanization_visible(self, visible: bool) -> None:
        if bool(self.lyrics_adapter.display_options["romanization"]) != bool(visible):
            self.lyrics_adapter.toggle_romanization()
        self._sync_display_buttons()

    def set_background_mode(self, mode: str) -> None:
        normalized = mode if mode in {"artwork", "gradient", "solid", "transparent", "custom"} else "artwork"
        self.options.background_mode = normalized
        self.background.set_mode(normalized)
        self.transparency_mode_changed.emit(normalized == "transparent")
        self._sync_options()

    def set_background_opacity(self, value: int) -> None:
        self.options.background_opacity = max(0, min(100, int(value)))
        self.options.background_image_opacity = self.options.background_opacity
        self.background.set_opacity(self.options.background_opacity)
        self._sync_options()

    def set_overlay_strength(self, value: int) -> None:
        self.options.overlay_strength = max(15, min(85, int(value)))
        self.options.background_darkness = self.options.overlay_strength
        self.background.set_overlay_strength(self.options.overlay_strength)
        self.readability_overlay.set_strength(self.options.overlay_strength)
        self._sync_options()

    def set_background_blur(self, value: int) -> None:
        self.options.background_blur = max(0, min(100, int(value)))
        self.background.set_blur(self.options.background_blur)
        self._sync_options()

    def set_background_transparency(self, value: int) -> None:
        self.options.background_transparency = max(0, min(100, int(value)))
        self.background.set_transparency(self.options.background_transparency)
        self._sync_options()

    def set_background_custom_path(self, value: str) -> None:
        path = str(value or "")
        self.options.background_custom_path = path
        self.background.set_custom_path(path)
        self._sync_options()

    def set_control_surface_opacity(self, value: int) -> None:
        self._control_surface_opacity = max(20, min(80, int(value)))
        self.options.control_surface_opacity = self._control_surface_opacity
        self._sync_options()

    def set_lyric_protection_enabled(self, enabled: bool) -> None:
        self.lyric_protection.enabled = bool(enabled)
        self.options.lyrics_protection_enabled = bool(enabled)
        self.canvas.update()
        self._sync_options()

    def set_lyric_protection_strength(self, value: int) -> None:
        self.lyric_protection.strength = max(0, min(100, int(value)))
        self.options.protection_strength = self.lyric_protection.strength
        self._sync_options()

    def set_global_lyric_scale(self, value: int) -> None:
        self.options.global_font_scale = max(75, min(160, int(value)))
        self.canvas.set_global_scale(self.options.global_font_scale)
        self._sync_options()

    def set_lyric_font_sizes(self, active: int, inactive: int, translation: int, romanization: int) -> None:
        self.options.active_font_size = max(28, min(72, int(active)))
        self.options.normal_font_size = max(18, min(52, int(inactive)))
        self.options.translation_font_size = max(11, min(30, int(translation)))
        self.options.romanization_font_size = max(11, min(30, int(romanization)))
        self.canvas.set_font_sizes(active, inactive, translation, romanization)
        self._sync_options()

    def set_lyric_weight(self, value: str) -> None:
        self.options.font_weight = str(value)
        self.canvas.set_font_weight(self.options.font_weight)
        self._sync_options()

    def set_inactive_lyric_opacity(self, value: int) -> None:
        self.options.inactive_lyric_opacity = max(40, min(92, int(value)))
        self.canvas.set_inactive_opacity(self.options.inactive_lyric_opacity)
        self._sync_options()

    def set_text_protection(self, value: str) -> None:
        self._text_protection = str(value)
        self.options.text_protection_mode = self._text_protection
        self.canvas.set_text_protection(self._text_protection)
        self._sync_options()

    def set_cover_scale(self, value: int) -> None:
        self.options.artwork_size = max(70, min(130, int(value)))
        self._apply_responsive_layout()
        self._sync_options()

    def set_lyrics_max_width(self, value: int) -> None:
        self.options.lyrics_max_width = max(420, min(920, int(value)))
        self.canvas.set_max_text_width(self.options.lyrics_max_width)
        self._sync_options()

    def set_auto_hide_controls(self, enabled: bool) -> None:
        self._auto_hide_controls = bool(enabled)
        self.options.controls_auto_hide = self._auto_hide_controls
        if not self._auto_hide_controls:
            self.wake_controls()
        else:
            self._schedule_controls_hide()
        self._sync_options()

    def reset_lyric_sizes(self) -> None:
        self.set_global_lyric_scale(100)
        self.set_lyric_font_sizes(46, 30, 14, 15)

    def reset_all_immersive_settings(self) -> None:
        fresh = ImmersiveLyricsOptions(theme=self._theme.mode)
        self.apply_options(fresh)

    def apply_options(self, options: ImmersiveLyricsOptions | None = None) -> None:
        source = options or self.options
        self.options = source
        self._applying_options = True
        try:
            self.set_theme_mode(source.theme)
            self.set_background_mode(source.background_mode)
            self.set_background_opacity(source.background_opacity)
            self.set_overlay_strength(source.overlay_strength)
            self.set_background_blur(source.background_blur)
            self.set_background_transparency(source.background_transparency)
            self.set_background_custom_path(source.background_custom_path)
            self.set_control_surface_opacity(source.control_surface_opacity)
            self.set_lyric_protection_enabled(source.lyrics_protection_enabled)
            self.set_lyric_protection_strength(source.protection_strength)
            self.set_global_lyric_scale(source.global_font_scale)
            self.set_lyric_font_sizes(source.active_font_size, source.normal_font_size, source.translation_font_size, source.romanization_font_size)
            self.set_lyric_weight(source.font_weight)
            self.set_inactive_lyric_opacity(source.inactive_lyric_opacity)
            self.set_text_protection(source.text_protection_mode)
            self.set_lyrics_max_width(source.lyrics_max_width)
            self.set_auto_hide_controls(source.controls_auto_hide)
            self._sync_panel_from_options()
        finally:
            self._applying_options = False
        self._sync_options()

    def set_reduce_motion(self, enabled: bool) -> None:
        self._reduce_motion = bool(enabled)
        self.settings_panel.set_reduce_motion(self._reduce_motion)

    def enter_fullscreen(self) -> None:
        self.fullscreen_requested.emit(True)

    def exit_fullscreen(self) -> None:
        self.fullscreen_requested.emit(False)

    def toggle_fullscreen(self) -> None:
        self.fullscreen_requested.emit(not self._host_fullscreen)

    def set_host_fullscreen(self, enabled: bool) -> None:
        self._host_fullscreen = bool(enabled)
        self._sync_fullscreen_button()
        self._apply_responsive_layout()

    def _sync_fullscreen_button(self) -> None:
        if not hasattr(self, "header_fullscreen_button"):
            return
        text = "退出全屏" if self._host_fullscreen else "全屏"
        tooltip = f"{text}（F11）"
        self.header_fullscreen_button.setText(text)
        self.header_fullscreen_button.setToolTip(tooltip)
        self.header_fullscreen_button.setAccessibleName(tooltip)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.canvas.set_playback_active(
            self._active and self.playback_adapter.state.is_playing
        )
        if not active:
            self._controls_hide_timer.stop()
            self._controls_hovered = False
            self.settings_panel.hide()
            self.queue_panel.hide()
            self._sync_overlay_hit_testing()
        else:
            self.wake_controls()

    def show_settings_panel(self) -> None:
        self.hide_queue_panel()
        self.settings_panel.begin_session()
        self.wake_controls()
        self.settings_panel.show()
        self._apply_responsive_layout()

    def hide_settings_panel(self) -> None:
        if self.settings_panel.is_dirty:
            self._cancel_quick_settings()
            return
        self.settings_panel.hide()
        self._apply_responsive_layout()
        self._schedule_controls_hide()

    def _on_settings_panel_closed(self) -> None:
        # The panel's local close action must restore the content allocation too.
        self._apply_responsive_layout()
        self.wake_controls()

    def _save_quick_settings(self) -> None:
        panel = self.settings_panel
        session = panel.session
        if session is None or not panel.is_dirty:
            return
        if self.settings_bridge is None:
            panel.mark_saved(session.working_snapshot)
            return
        try:
            saved = self.settings_bridge.save_snapshot(session.working_snapshot)
        except SettingsBridgeError as error:
            panel.mark_failed(str(error))
            return
        panel.mark_saved(saved)

    def _cancel_quick_settings(self) -> None:
        snapshot = self.settings_panel.cancel_session()
        if snapshot is not None:
            self._apply_formal_settings(snapshot.to_dict())
        self.settings_panel.hide()
        self._apply_responsive_layout()
        self.wake_controls()

    def _reset_quick_settings(self) -> None:
        """Preview the documented immersive defaults without saving immediately."""

        self.apply_options(ImmersiveLyricsOptions(theme=self._theme.mode))
        sync_session = getattr(self.settings_panel, "_sync_session_from_controls", None)
        if callable(sync_session):
            sync_session()
        self.wake_controls()

    def _apply_formal_settings(self, values: dict[str, object]) -> None:
        if self._settings_apply_callback is not None and not self._applying_options:
            self._settings_apply_callback(dict(values))

    def _preview_formal_settings(self) -> None:
        panel = self.settings_panel
        if panel.session is not None and panel.is_dirty:
            self._apply_formal_settings(panel.session.working_snapshot.to_dict())

    def toggle_settings_panel(self) -> None:
        self.hide_settings_panel() if self.settings_panel.isVisible() else self.show_settings_panel()

    def _cursor_over_controls(self) -> bool:
        """Use the stable control geometry even while the widget is hidden."""

        if not self.controls.geometry().isValid():
            return False
        local_position = self.mapFromGlobal(QCursor.pos())
        return self.controls.geometry().contains(local_position)

    def _cursor_near_controls(self) -> bool:
        """Return whether the pointer is close enough to intentionally wake controls."""

        if not self.controls.geometry().isValid():
            return False
        local_position = self.mapFromGlobal(QCursor.pos())
        return self.controls.geometry().adjusted(-140, -90, 140, 90).contains(local_position)

    def _update_controls_hover(self) -> None:
        if not self._active:
            return
        self._controls_hovered = self._cursor_over_controls()
        if self._controls_hovered:
            self.controls.show()
            self._controls_hide_timer.stop()
            return
        # Only movement near the control band should wake a hidden control layer;
        # moving the pointer while reading lyrics must not interrupt the view.
        if not self.controls.isVisible() and not self._cursor_near_controls():
            return
        self.controls.show()
        self._schedule_controls_hide()

    def wake_controls(self) -> None:
        self.controls.show()
        self._controls_hovered = self._cursor_over_controls()
        self._schedule_controls_hide()

    def hide_controls_preview(self) -> None:
        if not self._auto_hide_controls or self.settings_panel.isVisible() or self._controls_interacting:
            return
        if not self.playback_adapter.state.is_playing:
            return
        if self._cursor_over_controls():
            self._controls_hovered = True
            self._controls_hide_timer.stop()
            self.controls.show()
            return
        self._controls_hovered = False
        self.controls.hide()

    def _begin_controls_interaction(self) -> None:
        self._controls_interacting = True
        self.wake_controls()
        self._controls_hide_timer.stop()

    def _end_controls_interaction(self) -> None:
        self._controls_interacting = False
        self._schedule_controls_hide()

    def _schedule_controls_hide(self) -> None:
        self._controls_hide_timer.stop()
        if self._cursor_over_controls():
            self._controls_hovered = True
            return
        self._controls_hovered = False
        if self._active and self._auto_hide_controls and self.playback_adapter.state.is_playing and not self.settings_panel.isVisible() and not self._controls_interacting:
            self._controls_hide_timer.start()

    def _on_document_changed(self, document: LyricsDocument | None) -> None:
        self.canvas.set_document(document)
        self.identity.set_track(self.lyrics_adapter.track)
        self.background.set_track(self.lyrics_adapter.track)

    def _sync_lyrics_empty_layout(self) -> None:
        """Use one centered empty state until a current track exists."""

        empty = self._mode == "lyrics" and self.playback_adapter.state.current_track is None
        self._content_layout.activate()
        self.identity_column.setVisible(not empty)
        if empty:
            self.canvas.hide()
            self.lyrics_state_view.setGeometry(self.content.rect())
            self.lyrics_state_view.show()
            self.lyrics_state_view.raise_()
            return
        self.canvas.setVisible(
            self.lyrics_adapter.state.phase == "ready" or self._mode == "now_playing"
        )
        self.lyrics_state_view.setGeometry(self.canvas.geometry())
        self.lyrics_state_view.setVisible(
            self.lyrics_adapter.state.phase != "ready" and self._mode == "lyrics"
        )
        if self.lyrics_state_view.isVisible():
            self.lyrics_state_view.raise_()

    def _on_state_changed(self, state) -> None:
        ready = state.phase == "ready"
        self.lyrics_state_view.set_state(state)
        self.lyrics_state_view.source_button.hide()
        self._sync_lyrics_empty_layout()

    def _on_active_line_changed(self, line: LyricLine | None) -> None:
        self.canvas.set_active_line(line)

    def _on_active_segment_changed(self, line: LyricLine, index: int, progress: float) -> None:
        self.canvas.set_active_segment(line, index, progress)

    def _on_display_options_changed(self, options: dict[str, object]) -> None:
        # Immersive global scale belongs to ImmersiveLyricsOptions.  The shared
        # adapter only owns translation and romanization visibility here.
        self.canvas.set_display_options(options, update_font_scale=False)
        self._sync_display_buttons()

    def _on_playing_changed(self, playing: bool) -> None:
        self.canvas.set_playback_active(playing)
        if not playing:
            self.wake_controls()
        else:
            self._schedule_controls_hide()

    def _apply_panel_options(self) -> None:
        if self._applying_options:
            return
        panel = self.settings_panel
        mode = panel.theme_combo.currentData()
        if mode:
            self.set_theme_mode(str(mode))
        self.set_background_mode(str(panel.background_combo.currentData()))
        self.set_background_opacity(panel.background_opacity_slider.value())
        self.set_overlay_strength(panel.overlay_strength_slider.value())
        self.set_control_surface_opacity(panel.control_surface_opacity_slider.value())
        self.set_global_lyric_scale(panel.global_lyric_scale_slider.value())
        self.set_lyric_font_sizes(panel.active_font_slider.value(), panel.normal_font_slider.value(), panel.translation_font_slider.value(), panel.romanization_font_slider.value())
        self.set_inactive_lyric_opacity(panel.inactive_opacity_slider.value())
        self.set_lyric_weight(str(panel.weight_combo.currentData()))
        self.set_text_protection(str(panel.text_protection_combo.currentData()))
        self.set_auto_hide_controls(panel.auto_hide_check.isChecked())
        self.set_background_blur(panel.background_blur_slider.value())
        self.set_background_transparency(panel.background_transparency_slider.value())
        self.set_overlay_strength(max(15, panel.background_darkness_slider.value()))
        self.set_background_custom_path(panel.custom_path)
        self._preview_formal_settings()

    def _sync_panel_from_options(self) -> None:
        panel = self.settings_panel
        controls = (
            (panel.theme_combo, self.options.theme),
            (panel.background_combo, self.options.background_mode),
            (panel.weight_combo, self.options.font_weight),
            (panel.text_protection_combo, self.options.text_protection_mode),
        )
        for combo, value in controls:
            previous = combo.blockSignals(True)
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(previous)
        for slider, value in (
            (panel.background_opacity_slider, self.options.background_opacity),
            (panel.overlay_strength_slider, self.options.overlay_strength),
            (panel.control_surface_opacity_slider, self.options.control_surface_opacity),
            (panel.global_lyric_scale_slider, self.options.global_font_scale),
            (panel.active_font_slider, self.options.active_font_size),
            (panel.normal_font_slider, self.options.normal_font_size),
            (panel.translation_font_slider, self.options.translation_font_size),
            (panel.romanization_font_slider, self.options.romanization_font_size),
            (panel.inactive_opacity_slider, self.options.inactive_lyric_opacity),
            (panel.background_blur_slider, self.options.background_blur),
            (panel.background_darkness_slider, self.options.background_darkness),
            (panel.background_transparency_slider, self.options.background_transparency),
        ):
            previous = slider.blockSignals(True)
            slider.setValue(int(value))
            slider.blockSignals(previous)
        previous = panel.auto_hide_check.blockSignals(True)
        panel.auto_hide_check.setChecked(self.options.controls_auto_hide)
        panel.auto_hide_check.blockSignals(previous)
        panel._set_custom_path(self.options.background_custom_path)

    def _sync_options(self) -> None:
        if self._applying_options:
            return
        self.options_changed.emit(self.options)

    def _apply_responsive_layout(self, width: int | None = None) -> None:
        """Resize stable children without changing the content geometry for panels."""

        width = max(1, int(width or self.width() or 1400))
        height = max(1, self.height())
        if width < 1100:
            self._layout_band = "compact"
            compact = True
            direction = QBoxLayout.Direction.TopToBottom
            margins, spacing, canvas_scale = 22, 16, 0.82
        elif width < 1400:
            self._layout_band = "standard"
            compact = False
            direction = QBoxLayout.Direction.LeftToRight
            margins, spacing, canvas_scale = 42, 34, 0.92
        elif width < 1700:
            self._layout_band = "wide"
            compact = False
            direction = QBoxLayout.Direction.LeftToRight
            margins, spacing, canvas_scale = 56, 44, 1.0
        else:
            self._layout_band = "ultra"
            compact = False
            direction = QBoxLayout.Direction.LeftToRight
            margins, spacing, canvas_scale = 64, 48, 1.04

        top_margin = 70 if height > 500 else 60
        control_width = min(860, max(320, width - 40))
        control_height = max(132, self.controls.sizeHint().height())
        content_height = max(180, height - top_margin - control_height - 24)
        content_width = max(320, width - margins * 2)
        content_x = max(0, (width - content_width) // 2)
        self.content_stack.setVisible(True)
        self.content_stack.setGeometry(content_x, top_margin, content_width, content_height)
        self.content.setGeometry(self.content_stack.rect())
        self.controls.setGeometry(
            max(20, (width - control_width) // 2),
            max(top_margin + 20, height - control_height - 18),
            control_width,
            control_height,
        )
        self.controls.set_compact(width <= 960)

        self._content_layout.setDirection(direction)
        self._content_layout.setSpacing(spacing)
        if compact:
            self.identity_column.setMaximumWidth(16_777_215)
        else:
            self.identity_column.setMaximumWidth(min(560, max(390, round(content_width * 0.32))))
        self._content_layout.setStretch(0, 0 if compact else 36)
        self._content_layout.setStretch(1, 1 if compact else 64)
        self._content_layout.activate()
        self.lyrics_state_view.setGeometry(self.canvas.geometry())
        self._on_state_changed(self.lyrics_adapter.state)
        identity_inset = 0 if compact else 36 if self._layout_band == "standard" else 64 if self._layout_band == "wide" else 96
        self._identity_layout.setContentsMargins(identity_inset, 0, 0, 0)
        identity_width = max(300, (self.identity_column.width() or content_width) - identity_inset)
        self.identity.apply_responsive_layout(
            identity_width,
            compact,
            self.options.artwork_size,
            reference_width=content_width,
        )
        self.now_playing_page.set_responsive_reference_width(width, height)
        self.canvas.set_responsive_scale(canvas_scale)
        if self._mode == "lyrics":
            identity_allowance = 40 if compact else max(260, round(content_width * 0.36))
            max_text_width = min(
                760 if self._layout_band == "ultra" else self.options.lyrics_max_width,
                max(360, content_width - identity_allowance - spacing - 28),
            )
            self.canvas.set_max_text_width(max_text_width)

        panel_width = 400 if width >= 1400 else 365 if width >= 1100 else 325
        panel_top = 70 if height > 500 else 54
        panel_bottom_gap = 16
        controls_top = self.controls.geometry().top()
        panel_bottom = max(panel_top + 1, controls_top - panel_bottom_gap)
        available_panel_height = panel_bottom - panel_top
        if available_panel_height >= 220:
            panel_y = panel_top
            panel_height = min(660, available_panel_height)
        else:
            # Keep the panel above the control band even in a short window;
            # its own scroll area handles the reduced available height.
            panel_height = max(1, min(660, panel_bottom - 12))
            panel_y = max(12, panel_bottom - panel_height)
        panel_x = max(12, width - panel_width - 18)
        self.overlay_host.setGeometry(self.rect())
        self.queue_panel.setGeometry(panel_x, panel_y, panel_width, panel_height)
        self.settings_panel.setGeometry(panel_x, panel_y, panel_width, panel_height)
        self.header.setGeometry(0, 0, width, 60 if height > 500 else 54)
        self._place_overlays()

    def _place_overlays(self, compact_sheet: bool = False) -> None:
        self.background.setGeometry(self.rect())
        self.background.lower()
        self.readability_overlay.setGeometry(self.rect())
        self.readability_overlay.raise_()
        if self.content_stack.isVisible():
            self.readability_overlay.stackUnder(self.content_stack)
        if self.content_stack.isVisible() and self._mode == "lyrics":
            self._content_layout.activate()
            identity_origin = self.identity.mapTo(self, QPoint(0, 0))
            lyrics_origin = self.canvas.mapTo(self, QPoint(0, 0))
            controls_origin = self.controls.mapTo(self, QPoint(0, 0))
            self.readability_overlay.set_regions(
                QRect(identity_origin, self.identity.size()),
                QRect(lyrics_origin, self.canvas.size()),
                QRect(controls_origin, self.controls.size()) if self.controls.isVisible() else QRect(),
            )
        else:
            self.readability_overlay.set_regions(QRect(), QRect(), self.controls.geometry())
        self.overlay_host.setGeometry(self.rect())
        self._sync_overlay_hit_testing()
        self.overlay_host.raise_()
        self.header.raise_()
        self.controls.raise_()
        if self.settings_panel.isVisible():
            self.settings_panel.raise_()
        if self.queue_panel.isVisible():
            self.queue_panel.raise_()

    def _sync_overlay_hit_testing(self) -> None:
        """Let the lyric surface receive input unless a popup is open.

        The overlay host spans the complete immersive page so it can dismiss
        an open queue/settings panel when the user clicks outside it.  Keeping
        it interactive while both panels are hidden also makes it swallow
        wheel events destined for the lyrics canvas and clicks destined for
        the shared playback controls.
        """

        panel_visible = self.settings_panel.isVisible() or self.queue_panel.isVisible()
        self.overlay_host.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            not panel_visible,
        )

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.Enter,
            QEvent.Type.Leave,
        ):
            self._update_controls_hover()
        elif event.type() == QEvent.Type.MouseButtonPress and watched in (self, self.content, self.canvas):
            local_position = self.mapFromGlobal(event.globalPosition().toPoint())
            if self.settings_panel.isVisible() and not self.settings_panel.geometry().contains(local_position):
                self.hide_settings_panel()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.set_active(True)
        self._apply_responsive_layout()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.set_active(False)
        super().hideEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self.handle_escape()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space and not event.modifiers() and not isinstance(self.focusWidget(), QSlider):
            self.playback_adapter.toggle_playback()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and not event.modifiers() and not isinstance(self.focusWidget(), QSlider):
            delta = 5 if event.key() == Qt.Key.Key_Up else -5
            self.playback_adapter.set_volume(self.playback_adapter.state.volume + delta)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and not event.modifiers() and not isinstance(self.focusWidget(), QSlider):
            delta = -5_000 if event.key() == Qt.Key.Key_Left else 5_000
            state = self.playback_adapter.state
            self.playback_adapter.seek(state.position_ms + delta)
            event.accept()
            return
        if event.key() == Qt.Key.Key_L and not event.modifiers():
            self.mode_changed.emit("lyrics" if self._mode == "now_playing" else "now_playing")
            event.accept()
            return
        super().keyPressEvent(event)

    def handle_escape(self) -> None:
        """Close the foremost immersive surface before leaving the shell."""

        self._handle_escape()

    def _handle_escape(self) -> None:
        if self.settings_panel.close_popup():
            return
        if self.queue_panel.isVisible():
            self.hide_queue_panel()
            return
        if self.settings_panel.isVisible():
            self.hide_settings_panel()
            return
        if self._host_fullscreen:
            self.exit_fullscreen()
            return
        self.immersive_exit_requested.emit()

    def shutdown(self) -> None:
        """Stop owned timers and close stable overlays before app shutdown."""

        self._controls_hide_timer.stop()
        self.settings_panel.hide()
        self.queue_panel.hide()
        self.set_active(False)
