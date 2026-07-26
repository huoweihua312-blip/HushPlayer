"""Formal V2 immersive lyrics page built from the accepted preview surface."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.adapters.playback_adapter import PlaybackAdapter
from app.ui_v2.experiments.immersive_lyrics_preview import ImmersiveLyricsPreview
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.models.lyric_line import LyricLine
from app.ui_v2.models.lyrics_document import LyricsDocument
from app.ui_v2.theme.tokens import Theme


class ImmersiveLyricsPage(ImmersiveLyricsPreview):
    """One cached immersive surface sharing V2 playback and lyric state."""

    def __init__(
        self,
        lyrics: LyricsAdapter,
        playback: PlaybackAdapter,
        theme: Theme,
        parent: QWidget | None = None,
    ) -> None:
        self.lyrics_adapter = lyrics
        self.playback_adapter = playback
        self.options = ImmersiveLyricsOptions(theme=theme.mode)
        super().__init__(parent, standalone=False)
        self.setObjectName("immersiveLyricsPage")
        self.bind_playback(playback)
        self._connect_adapters()
        self._connect_options()
        self.set_theme(theme)
        self._on_document_changed(lyrics.document)
        self._on_active_line_changed(lyrics.active_line)
        self._on_display_options_changed(lyrics.display_options)
        self._sync_options()

    @property
    def document(self) -> LyricsDocument | None:
        return self.lyrics_adapter.document

    def set_theme(self, theme: Theme) -> None:
        self.set_theme_mode(theme.mode)
        self._sync_options()

    def set_responsive_reference_width(self, width: int) -> None:
        # Geometry is owned by the cached page itself; this only refreshes bands.
        self._apply_responsive_layout()

    def set_translation_visible(self, visible: bool) -> None:
        super().set_translation_visible(visible)
        if bool(self.lyrics_adapter.display_options["translation"]) != bool(visible):
            self.lyrics_adapter.toggle_translation()
        self._sync_options()

    def set_romanization_visible(self, visible: bool) -> None:
        super().set_romanization_visible(visible)
        if bool(self.lyrics_adapter.display_options["romanization"]) != bool(visible):
            self.lyrics_adapter.toggle_romanization()
        self._sync_options()

    def set_global_lyric_scale(self, value: int) -> None:
        super().set_global_lyric_scale(value)
        self._sync_options()

    def set_lyric_font_sizes(self, active: int, inactive: int, translation: int, romanization: int) -> None:
        super().set_lyric_font_sizes(active, inactive, translation, romanization)
        self._sync_options()

    def set_background_mode(self, mode: str) -> None:
        super().set_background_mode(mode)
        self._sync_options()

    def set_theme_mode(self, mode: str) -> None:
        super().set_theme_mode(mode)
        self._sync_options()

    def set_background_opacity(self, value: int) -> None:
        super().set_background_opacity(value)
        self._sync_options()

    def set_overlay_strength(self, value: int) -> None:
        super().set_overlay_strength(value)
        self._sync_options()

    def set_control_surface_opacity(self, value: int) -> None:
        super().set_control_surface_opacity(value)
        self._sync_options()

    def set_lyric_protection_enabled(self, enabled: bool) -> None:
        super().set_lyric_protection_enabled(enabled)
        self._sync_options()

    def set_lyric_protection_strength(self, value: int) -> None:
        super().set_lyric_protection_strength(value)
        self._sync_options()

    def set_lyric_weight(self, value: str) -> None:
        super().set_lyric_weight(value)
        self._sync_options()

    def set_inactive_lyric_opacity(self, value: int) -> None:
        super().set_inactive_lyric_opacity(value)
        self._sync_options()

    def set_text_protection(self, value: str) -> None:
        super().set_text_protection(value)
        self._sync_options()

    def set_cover_scale(self, value: int) -> None:
        super().set_cover_scale(value)
        self._sync_options()

    def set_lyrics_max_width(self, value: int) -> None:
        super().set_lyrics_max_width(value)
        self._sync_options()

    def set_auto_hide_controls(self, enabled: bool) -> None:
        super().set_auto_hide_controls(enabled)
        self._sync_options()

    def reset_lyric_sizes(self) -> None:
        super().reset_lyric_sizes()
        self._sync_options()

    def reset_all_immersive_settings(self) -> None:
        super().reset_all_immersive_settings()
        self._sync_options()

    def _connect_adapters(self) -> None:
        self.lyrics_adapter.document_changed.connect(self._on_document_changed)
        self.lyrics_adapter.active_line_changed.connect(self._on_active_line_changed)
        self.lyrics_adapter.active_segment_changed.connect(self._on_active_segment_changed)
        self.lyrics_adapter.display_options_changed.connect(self._on_display_options_changed)

    def _connect_options(self) -> None:
        panel = self.settings_panel
        for signal in (
            panel.theme_requested,
            panel.background_mode_requested,
            panel.background_opacity_changed,
            panel.overlay_strength_changed,
            panel.control_surface_opacity_changed,
            panel.lyric_protection_changed,
            panel.lyric_protection_strength_changed,
            panel.global_lyric_scale_changed,
            panel.font_sizes_changed,
            panel.weight_changed,
            panel.inactive_opacity_changed,
            panel.text_protection_changed,
            panel.cover_scale_changed,
            panel.lyrics_width_changed,
            panel.auto_hide_changed,
            panel.reset_lyric_sizes_requested,
            panel.reset_all_requested,
        ):
            signal.connect(self._sync_options)

    def _on_document_changed(self, document: LyricsDocument | None) -> None:
        self.set_track(self.lyrics_adapter.track, document)
        self._on_active_line_changed(self.lyrics_adapter.active_line)

    def _on_active_line_changed(self, line: LyricLine | None) -> None:
        self.lyrics_view.set_active_line(line)

    def _on_active_segment_changed(
        self, line: LyricLine, segment_index: int, progress: float
    ) -> None:
        self.lyrics_view.set_active_segment(line, segment_index, progress)

    def _on_display_options_changed(self, options: dict[str, object]) -> None:
        # Use base setters so a change made in the ordinary LyricsPage does not
        # toggle the adapter a second time.
        super().set_translation_visible(bool(options.get("translation")))
        super().set_romanization_visible(bool(options.get("romanization")))
        self._sync_options()

    def _sync_options(self, *_args: object) -> None:
        canvas = self.lyrics_view.canvas
        self.options.update(
            theme=self._theme.mode,
            background_mode=self.background_mode,
            background_opacity=self.background_opacity_percent,
            overlay_strength=self.overlay_strength,
            control_surface_opacity=self.control_surface_opacity,
            lyrics_protection_enabled=self.lyric_protection.enabled,
            protection_strength=self.lyric_protection.strength,
            global_font_scale=canvas.global_scale,
            active_font_size=canvas.active_font_size,
            normal_font_size=canvas.inactive_font_size,
            translation_font_size=canvas.translation_font_size,
            romanization_font_size=canvas.romanization_font_size,
            font_weight=canvas._weight_name,
            inactive_lyric_opacity=canvas.inactive_opacity,
            text_protection_mode=canvas.text_protection,
            artwork_size=self._cover_scale,
            lyrics_max_width=self._lyrics_max_width,
            controls_auto_hide=self.auto_hide_controls,
        )
