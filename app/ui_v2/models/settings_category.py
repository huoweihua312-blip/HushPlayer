"""Static, ordered metadata for the UI V2 settings center."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SettingsCategory:
    """One navigable settings category with a semantic V2 icon."""

    key: str
    title: str
    icon_name: str


SETTINGS_CATEGORIES: tuple[SettingsCategory, ...] = (
    SettingsCategory("general", "常规", "general"),
    SettingsCategory("appearance", "外观", "appearance"),
    SettingsCategory("playback", "播放", "playback"),
    SettingsCategory("lyrics", "歌词", "lyrics"),
    SettingsCategory("library", "音乐库", "library"),
    SettingsCategory("cache", "缓存", "cache"),
    SettingsCategory("updates", "更新", "updates"),
    SettingsCategory("about", "关于", "about"),
)


def category_for_key(key: str) -> SettingsCategory:
    """Resolve a category without making route order depend on widgets."""
    return next((item for item in SETTINGS_CATEGORIES if item.key == key), SETTINGS_CATEGORIES[0])


def category_key_for(value: str) -> str:
    """Accept a stable key or a visible category title from search metadata."""
    return next(
        (item.key for item in SETTINGS_CATEGORIES if value in {item.key, item.title}),
        SETTINGS_CATEGORIES[0].key,
    )
