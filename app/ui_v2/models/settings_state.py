"""Typed, copyable in-memory state for the UI V2 settings center."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass(slots=True)
class GeneralSettings:
    restore_last_session: bool = True
    auto_open_floating_lyrics: bool = False
    minimize_to_tray: bool = True
    close_behavior: str = "ask"
    remember_close_choice: bool = False
    language: str = "zh_CN"


@dataclass(slots=True)
class AppearanceSettings:
    theme_mode: str = "dark"
    accent_mode: str = "system"
    ui_scale: int = 100
    compact_density: bool = False
    reduce_motion: bool = False


@dataclass(slots=True)
class PlaybackSettings:
    autoplay_on_start: bool = False
    default_volume: int = 70
    remember_volume: bool = True
    gapless_enabled: bool = True
    crossfade_enabled: bool = False
    crossfade_seconds: int = 3
    replay_gain_mode: str = "off"
    output_device_mock: str = "default"


@dataclass(slots=True)
class LyricsSettings:
    show_translation: bool = True
    show_romanization: bool = False
    lyrics_font_scale: float = 1.0
    lyrics_alignment: str = "center"
    auto_follow: bool = True
    manual_browse_timeout: int = 6
    lyrics_offset_ms: int = 0


@dataclass(slots=True)
class ImmersiveSettings:
    theme: str = "dark"
    background_mode: str = "artwork"
    background_opacity: int = 55
    overlay_strength: int = 45
    control_surface_opacity: int = 35
    lyrics_protection_enabled: bool = True
    protection_strength: int = 58
    global_font_scale: int = 100
    active_font_size: int = 46
    normal_font_size: int = 30
    translation_font_size: int = 14
    romanization_font_size: int = 15
    font_weight: str = "Semibold"
    inactive_lyric_opacity: int = 68
    text_protection_mode: str = "轻微阴影"
    artwork_size: int = 100
    lyrics_max_width: int = 780
    controls_auto_hide: bool = True


@dataclass(slots=True)
class LibrarySettings:
    mock_music_folders: list[str] = field(default_factory=lambda: ["D:\\Music\\HushPlayer Mock"])
    scan_on_start: bool = False
    include_subfolders: bool = True
    import_mode: str = "review"
    ignore_short_tracks_seconds: int = 15
    watch_folder_changes: bool = False


@dataclass(slots=True)
class CacheSettings:
    artwork_cache_enabled: bool = True
    lyrics_cache_enabled: bool = True
    online_audio_cache_enabled: bool = False
    cache_limit_mb: int = 1024
    clear_incomplete_on_start: bool = True


@dataclass(slots=True)
class UpdateSettings:
    auto_check_updates: bool = True
    update_channel: str = "stable"
    startup_check_delay_seconds: int = 8
    download_updates_automatically: bool = False


@dataclass(slots=True)
class SettingsState:
    """The complete draftable V2 settings state; it never reads or writes disk."""

    general: GeneralSettings = field(default_factory=GeneralSettings)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    playback: PlaybackSettings = field(default_factory=PlaybackSettings)
    lyrics: LyricsSettings = field(default_factory=LyricsSettings)
    immersive: ImmersiveSettings = field(default_factory=ImmersiveSettings)
    library: LibrarySettings = field(default_factory=LibrarySettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    updates: UpdateSettings = field(default_factory=UpdateSettings)

    def copy(self) -> "SettingsState":
        return deepcopy(self)

    def get_value(self, path: str) -> Any:
        category, field_name = _split_path(path)
        return getattr(getattr(self, category), field_name)

    def set_value(self, path: str, value: Any) -> None:
        category, field_name = _split_path(path)
        setattr(getattr(self, category), field_name, deepcopy(value))

    def flat_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for category_field in fields(self):
            category_name = category_field.name
            group = getattr(self, category_name)
            for value_field in fields(group):
                result[f"{category_name}.{value_field.name}"] = deepcopy(
                    getattr(group, value_field.name)
                )
        return result

    def dirty_fields_against(self, other: "SettingsState") -> frozenset[str]:
        ours = self.flat_values()
        theirs = other.flat_values()
        return frozenset(path for path, value in ours.items() if value != theirs[path])


def _split_path(path: str) -> tuple[str, str]:
    category, separator, field_name = str(path).partition(".")
    if not separator or not category or not field_name:
        raise ValueError(f"Invalid settings path: {path!r}")
    return category, field_name
