"""Formal V4 immersive lyrics page sharing V2 playback and lyric adapters."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QBoxLayout, QVBoxLayout, QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.theme.tokens import Theme, get_theme
from app.ui_v2.widgets.artwork_atmosphere import ArtworkAtmosphere, ReadabilityOverlay
from app.ui_v2.widgets.immersive_controls import ImmersiveControls
from app.ui_v2.widgets.immersive_settings_panel import ImmersiveSettingsPanel
from app.ui_v2.widgets.immersive_track_identity import ImmersiveTrackIdentity
from app.ui_v2.widgets.lyrics_canvas_v2 import LyricsCanvasV2


@dataclass(slots=True)
class _LyricProtection:
    """Settings compatibility state; the canvas remains free of row overlays."""

    enabled: bool = True
    strength: int = 58
    paint_profile: str = "soft_text_shadow"
    is_row_bound: bool = False


class ImmersiveLyricsPage(QWidget):
    """A cached V4 immersive surface, never a second top-level window."""

    fullscreen_requested = Signal(bool)
    immersive_exit_requested = Signal()
    transparency_mode_changed = Signal(bool)
    options_changed = Signal(object)

    def __init__(
        self,
        lyrics: LyricsAdapter,
        playback: PlaybackAdapter,
        theme: Theme,
        options: ImmersiveLyricsOptions | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.lyrics_adapter = lyrics
        self.playback_adapter = playback
        self.options = options or ImmersiveLyricsOptions(theme=theme.mode)
        self._theme = theme
        self._host_fullscreen = False
        self._active = False
        self._layout_band = "wide"
        self._auto_hide_controls = True
        self._reduce_motion = False
        self._controls_interacting = False
        self._applying_options = False
        self._control_surface_opacity = self.options.control_surface_opacity
        self._text_protection = self.options.text_protection_mode
        self.lyric_protection = _LyricProtection(
            self.options.lyrics_protection_enabled, self.options.protection_strength
        )
        self.setObjectName("immersiveLyricsPage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.background = ArtworkAtmosphere(theme, self)
        self.readability_overlay = ReadabilityOverlay(theme, self)
        self.content = QWidget(self)
        self.content.setObjectName("immersiveLyricsContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content.setAutoFillBackground(False)
        self.identity_column = QWidget(self.content)
        self.identity_column.setObjectName("immersiveIdentityColumn")
        self.identity = ImmersiveTrackIdentity(theme, self.identity_column)
        self.controls = ImmersiveControls(theme, self.identity_column)
        self._identity_layout = QVBoxLayout(self.identity_column)
        self._identity_layout.setContentsMargins(0, 0, 0, 0)
        self._identity_layout.setSpacing(18)
        self._identity_layout.addStretch(1)
        self._identity_layout.addWidget(self.identity)
        self._identity_layout.addWidget(self.controls)
        self._identity_layout.addStretch(1)
        self.canvas = LyricsCanvasV2(theme, self.content)
        self.canvas.set_mode("immersive")
        self.lyrics_view = self.canvas  # Public semantic alias: one visual surface, no scroll list.
        self._content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(54)
        self._content_layout.addWidget(self.identity_column, 36)
        self._content_layout.addWidget(self.canvas, 64)
        self.settings_panel = ImmersiveSettingsPanel(theme, self)
        self.settings_panel.hide()
        self._controls_hide_timer = QTimer(self)
        self._controls_hide_timer.setSingleShot(True)
        self._controls_hide_timer.setInterval(2200)
        self._controls_hide_timer.timeout.connect(self.hide_controls_preview)
        self._connect_components()
        self._connect_adapters()
        self.apply_options()
        self._on_document_changed(lyrics.document)
        self._on_active_line_changed(lyrics.active_line)
        self._on_display_options_changed(lyrics.display_options)
        self._apply_responsive_layout()

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
        self.controls.back_button.clicked.connect(self.immersive_exit_requested)
        self.controls.more_button.clicked.connect(self.toggle_settings_panel)
        self.controls.interaction_started.connect(self._begin_controls_interaction)
        self.controls.interaction_finished.connect(self._end_controls_interaction)
        self.canvas.seek_requested.connect(self.lyrics_adapter.seek_to_line)
        self.settings_panel.changed.connect(self._apply_panel_options)
        self.settings_panel.exit_requested.connect(self.immersive_exit_requested)
        self.settings_panel.closed.connect(self._on_settings_panel_closed)
        for widget in (self, self.content, self.canvas, self.controls):
            widget.installEventFilter(self)
        self._fullscreen_action = QAction(self)
        self._fullscreen_action.setShortcut("F11")
        self._fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self._fullscreen_action)

    def _connect_adapters(self) -> None:
        self.lyrics_adapter.document_changed.connect(self._on_document_changed)
        self.lyrics_adapter.active_line_changed.connect(self._on_active_line_changed)
        self.lyrics_adapter.active_segment_changed.connect(self._on_active_segment_changed)
        self.lyrics_adapter.display_options_changed.connect(self._on_display_options_changed)
        self.playback_adapter.playing_changed.connect(self._on_playing_changed)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.background.set_theme(theme)
        self.readability_overlay.set_theme(theme)
        self.identity.set_theme(theme)
        self.canvas.set_theme(theme)
        self.controls.set_theme(theme)
        self.settings_panel.set_theme(theme)
        self.options.theme = theme.mode
        self._sync_options()

    def set_theme_mode(self, mode: str) -> None:
        self.set_theme(get_theme("light" if mode == "light" else "dark"))

    def set_responsive_reference_width(self, width: int) -> None:
        self._apply_responsive_layout(width)

    def set_translation_visible(self, visible: bool) -> None:
        if bool(self.lyrics_adapter.display_options["translation"]) != bool(visible):
            self.lyrics_adapter.toggle_translation()

    def set_romanization_visible(self, visible: bool) -> None:
        if bool(self.lyrics_adapter.display_options["romanization"]) != bool(visible):
            self.lyrics_adapter.toggle_romanization()

    def set_background_mode(self, mode: str) -> None:
        normalized = mode if mode in {"artwork", "gradient", "solid", "transparent"} else "artwork"
        self.options.background_mode = normalized
        self.background.set_mode(normalized)
        self.transparency_mode_changed.emit(normalized == "transparent")
        self._sync_options()

    def set_background_opacity(self, value: int) -> None:
        self.options.background_opacity = max(0, min(100, int(value)))
        self.background.set_opacity(self.options.background_opacity)
        self._sync_options()

    def set_overlay_strength(self, value: int) -> None:
        self.options.overlay_strength = max(15, min(85, int(value)))
        self.background.set_overlay_strength(self.options.overlay_strength)
        self.readability_overlay.set_strength(self.options.overlay_strength)
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
        self._apply_responsive_layout()

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if not active:
            self._controls_hide_timer.stop()
            self.settings_panel.hide()
        else:
            self.wake_controls()

    def show_settings_panel(self) -> None:
        self.wake_controls()
        self.settings_panel.show()
        self._apply_responsive_layout()

    def hide_settings_panel(self) -> None:
        self.settings_panel.hide()
        self._apply_responsive_layout()
        self._schedule_controls_hide()

    def _on_settings_panel_closed(self) -> None:
        # The panel's local close action must restore the content allocation too.
        self._apply_responsive_layout()
        self.wake_controls()

    def toggle_settings_panel(self) -> None:
        self.hide_settings_panel() if self.settings_panel.isVisible() else self.show_settings_panel()

    def wake_controls(self) -> None:
        self.controls.show()
        self._schedule_controls_hide()

    def hide_controls_preview(self) -> None:
        if not self._auto_hide_controls or self.settings_panel.isVisible() or self._controls_interacting:
            return
        if not self.playback_adapter.state.is_playing:
            return
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
        if self._active and self._auto_hide_controls and self.playback_adapter.state.is_playing and not self.settings_panel.isVisible() and not self._controls_interacting:
            self._controls_hide_timer.start()

    def _on_document_changed(self, document: LyricsDocument | None) -> None:
        self.canvas.set_document(document)
        self.identity.set_track(self.lyrics_adapter.track)
        self.background.set_track(self.lyrics_adapter.track)

    def _on_active_line_changed(self, line: LyricLine | None) -> None:
        self.canvas.set_active_line(line)

    def _on_active_segment_changed(self, line: LyricLine, index: int, progress: float) -> None:
        self.canvas.set_active_segment(line, index, progress)

    def _on_display_options_changed(self, options: dict[str, object]) -> None:
        # Immersive global scale belongs to ImmersiveLyricsOptions.  The shared
        # adapter only owns translation and romanization visibility here.
        self.canvas.set_display_options(options, update_font_scale=False)

    def _on_playing_changed(self, playing: bool) -> None:
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
        ):
            previous = slider.blockSignals(True)
            slider.setValue(int(value))
            slider.blockSignals(previous)
        previous = panel.auto_hide_check.blockSignals(True)
        panel.auto_hide_check.setChecked(self.options.controls_auto_hide)
        panel.auto_hide_check.blockSignals(previous)

    def _sync_options(self) -> None:
        if self._applying_options:
            return
        self.options_changed.emit(self.options)

    def _apply_responsive_layout(self, width: int | None = None) -> None:
        width = int(width or self.width() or 1400)
        height = max(1, self.height())
        if width < 900:
            self._layout_band = "compact"
            compact = True
            direction = QBoxLayout.Direction.TopToBottom
            margins, spacing, canvas_scale = 22, 16, 0.76
        elif width < 1100:
            self._layout_band = "compact"
            compact = True
            direction = QBoxLayout.Direction.TopToBottom
            margins, spacing, canvas_scale = 30, 20, 0.84
        elif width < 1400:
            self._layout_band = "standard"
            compact = False
            direction = QBoxLayout.Direction.LeftToRight
            margins, spacing, canvas_scale = 46, 42, 0.92
        elif width < 1700:
            self._layout_band = "wide"
            compact = False
            direction = QBoxLayout.Direction.LeftToRight
            margins, spacing, canvas_scale = 58, 52, 1.0
        else:
            self._layout_band = "ultra"
            compact = False
            direction = QBoxLayout.Direction.LeftToRight
            margins, spacing, canvas_scale = 0, 56, 1.06
        panel_open = self.settings_panel.isVisible()
        panel_width = min(380, max(320, self.settings_panel.maximumWidth()))
        panel_gap = 30
        top_margin = 26 if height > 500 else 14
        # Controls now live below the left identity block, so the lyric canvas
        # no longer reserves a bottom transport strip.
        content_height = max(220, height - top_margin * 2)

        # A narrow window gets a sheet instead of squeezing lyrics beside it.
        compact_sheet = panel_open and width < 1100
        if compact_sheet:
            sheet_width = min(round(width * 0.88), panel_width)
            sheet_height = min(max(300, round(height * 0.78)), max(240, height - 82))
            self.settings_panel.setGeometry(
                max(12, (width - sheet_width) // 2),
                max(58, height - sheet_height - 16),
                sheet_width,
                sheet_height,
            )
            # Preserve the page and its children but avoid any hidden/cropped
            # lyric surface behind a compact settings sheet.
            self.content.setGeometry(0, 0, 0, 0)
            self.content.setVisible(False)
        else:
            self.content.setVisible(True)
            if panel_open:
                content_area_left = margins
                content_area_right = max(content_area_left + 480, width - panel_width - panel_gap)
                available_content_width = max(480, content_area_right - content_area_left)
                content_width = min(1360, available_content_width)
                content_x = content_area_left + max(0, (available_content_width - content_width) // 2)
                self.settings_panel.setGeometry(
                    max(12, width - panel_width - 26),
                    top_margin,
                    panel_width,
                    min(max(300, height - 72), 620),
                )
            else:
                content_width = min(1360, max(320, width - margins * 2))
                content_x = max(0, (width - content_width) // 2)
                self.settings_panel.setGeometry(
                    max(12, width - panel_width - 26),
                    top_margin,
                    panel_width,
                    min(max(300, height - 72), 620),
                )
            self.content.setGeometry(content_x, top_margin, content_width, content_height)
        self._content_layout.setDirection(direction)
        self._content_layout.setSpacing(spacing)
        if compact:
            self._content_layout.setStretch(0, 0)
            self._content_layout.setStretch(1, 1)
        else:
            # Keep the identity and its controls inside the requested 34–38% band.
            self._content_layout.setStretch(0, 36)
            self._content_layout.setStretch(1, 64)
        self._content_layout.activate()
        layout_reference_width = self.content.width() if self.content.isVisible() else width
        identity_width = self.identity_column.width() if self.content.isVisible() else layout_reference_width
        self.identity.apply_responsive_layout(identity_width, compact, self.options.artwork_size)
        self.canvas.set_responsive_scale(canvas_scale)
        if self.content.isVisible():
            identity_allowance = 40 if compact else max(260, round(self.content.width() * 0.36))
            max_text_width = min(
                760 if self._layout_band == "ultra" else self.options.lyrics_max_width,
                max(360, self.content.width() - identity_allowance - spacing - 28),
            )
            self.canvas.set_max_text_width(max_text_width)
        self.controls.set_compact(width < 900)
        self._place_overlays(compact_sheet)

    def _place_overlays(self, compact_sheet: bool = False) -> None:
        self.background.setGeometry(self.rect())
        self.background.lower()
        self.readability_overlay.setGeometry(self.rect())
        self.readability_overlay.raise_()
        if self.content.isVisible():
            self.readability_overlay.stackUnder(self.content)
        if self.content.isVisible():
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
        if self.settings_panel.isVisible():
            self.settings_panel.raise_()

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.MouseMove:
            self.wake_controls()
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
        if event.key() == Qt.Key.Key_Escape:
            self._handle_escape()
            event.accept()
            return
        super().keyPressEvent(event)

    def _handle_escape(self) -> None:
        if self.settings_panel.close_popup():
            return
        if self.settings_panel.isVisible():
            self.hide_settings_panel()
            return
        if self._host_fullscreen:
            self.exit_fullscreen()
            return
        self.immersive_exit_requested.emit()
