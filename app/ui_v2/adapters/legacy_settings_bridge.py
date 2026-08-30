"""Settings bridge shared by the V2 Overlay and the existing settings file.

The bridge owns persistence boundaries. Widgets receive snapshots and action
callbacks; they never open or write ``settings.json`` themselves.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.core.app_paths import AppPaths
from app.models.appearance_settings import (
    APPEARANCE_SETTING_KEYS,
    ImmersiveAppearanceConfig,
    normalize_appearance_mode,
)
from app.services.lyrics_timing import normalize_lyrics_timing_offsets
from app.ui_v2.models.settings_snapshot import SettingsSnapshot
from app.ui_v2.theme.tokens import OPEN_FONT_FAMILIES


IMMERSIVE_BACKGROUND_VISUAL_MODES = frozenset(
    {"artwork", "gradient", "solid", "transparent", "custom"}
)
_LEGACY_BACKGROUND_TO_VISUAL_MODE = {
    "cover": "artwork",
    "default": "solid",
    "translucent": "transparent",
    "custom": "custom",
}


def normalize_immersive_background_visual_mode(
    value: Any,
    legacy_mode: Any = "cover",
) -> str:
    """Resolve the V2 visual mode while preserving the legacy setting key."""

    visual_mode = str(value or "").strip().casefold()
    if visual_mode in IMMERSIVE_BACKGROUND_VISUAL_MODES:
        return visual_mode
    return _LEGACY_BACKGROUND_TO_VISUAL_MODE.get(
        str(legacy_mode or "cover").strip().casefold(),
        "artwork",
    )


DEFAULT_SETTINGS: dict[str, Any] = {
    "volume": 65,
    "play_mode": "list_loop",
    "appearance_mode": "dark",
    "auto_scan_music_folders_on_startup": True,
    "floating_lyrics_auto_open": False,
    "restore_last_playback": True,
    "immersive_auto_hide_ui": True,
    "floating_lyrics_color": "white",
    "floating_lyrics_opacity": 100,
    "floating_lyrics_font_size": 42,
    "floating_lyrics_width": 980,
    "floating_lyrics_height": 135,
    "floating_lyrics_font_family": OPEN_FONT_FAMILIES[0],
    "floating_lyrics_x": -1,
    "floating_lyrics_y": -1,
    "floating_lyrics_passthrough": True,
    "music_scan_folders": [],
    "music_scan_import_mode": "pending",
    "auto_check_updates_on_startup": False,
    "update_check_delay_seconds": 15,
    "cache_directory": "",
    "remember_close_choice": False,
    "close_behavior": "ask",
    "immersive_background_mode": "cover",
    "immersive_background_visual_mode": "artwork",
    "immersive_background_custom_path": "",
    "immersive_background_blur": 40,
    "immersive_background_darkness": 68,
    "immersive_background_image_opacity": 100,
    "immersive_background_transparency": 38,
    "immersive_background_fill_mode": "cover",
    "immersive_lyrics_font_scale": 100,
}


def load_settings_document(path: Path) -> dict[str, Any]:
    """Load the existing settings document with legacy normalization rules."""

    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_SETTINGS)
    if not isinstance(document, dict):
        return dict(DEFAULT_SETTINGS)

    result = deepcopy(document)
    try:
        volume = int(result.get("volume", DEFAULT_SETTINGS["volume"]))
    except (TypeError, ValueError):
        volume = int(DEFAULT_SETTINGS["volume"])
    result["volume"] = max(0, min(100, volume))

    play_mode = result.get("play_mode", DEFAULT_SETTINGS["play_mode"])
    if not isinstance(play_mode, str) or play_mode not in {
        "sequence",
        "list_loop",
        "single_loop",
        "shuffle",
    }:
        play_mode = DEFAULT_SETTINGS["play_mode"]
    result["play_mode"] = play_mode

    if "appearance_mode" in result:
        result["appearance_mode"] = normalize_appearance_mode(result["appearance_mode"])

    integer_defaults = {
        "floating_lyrics_opacity": 100,
        "floating_lyrics_font_size": 42,
        "floating_lyrics_width": 980,
        "floating_lyrics_height": 135,
        "floating_lyrics_x": -1,
        "floating_lyrics_y": -1,
        "update_check_delay_seconds": 15,
    }
    for key, default in integer_defaults.items():
        if key not in result:
            continue
        try:
            result[key] = int(result[key])
        except (TypeError, ValueError):
            result[key] = default

    if APPEARANCE_SETTING_KEYS.intersection(result):
        result.update(ImmersiveAppearanceConfig.from_settings(result).to_settings())
    result["immersive_background_visual_mode"] = normalize_immersive_background_visual_mode(
        result.get("immersive_background_visual_mode"),
        result.get("immersive_background_mode", DEFAULT_SETTINGS["immersive_background_mode"]),
    )
    if "lyrics_timing_offsets_ms" in result:
        result["lyrics_timing_offsets_ms"] = normalize_lyrics_timing_offsets(
            result["lyrics_timing_offsets_ms"]
        )
    if "auto_check_updates_on_startup" in result and not isinstance(
        result["auto_check_updates_on_startup"], bool
    ):
        result["auto_check_updates_on_startup"] = False
    font_family = str(
        result.get("floating_lyrics_font_family", DEFAULT_SETTINGS["floating_lyrics_font_family"])
    ).strip()
    result["floating_lyrics_font_family"] = (
        font_family if font_family in OPEN_FONT_FAMILIES else DEFAULT_SETTINGS["floating_lyrics_font_family"]
    )
    if "floating_lyrics_passthrough" in result and not isinstance(
        result["floating_lyrics_passthrough"], bool
    ):
        result["floating_lyrics_passthrough"] = True
    result["floating_lyrics_passthrough"] = bool(
        result.get("floating_lyrics_passthrough", DEFAULT_SETTINGS["floating_lyrics_passthrough"])
    )
    if "remember_close_choice" in result and not isinstance(
        result["remember_close_choice"], bool
    ):
        result["remember_close_choice"] = False
    result["remember_close_choice"] = bool(
        result.get("remember_close_choice", DEFAULT_SETTINGS["remember_close_choice"])
    )
    close_behavior = str(
        result.get("close_behavior", DEFAULT_SETTINGS["close_behavior"])
    ).strip().casefold()
    if close_behavior not in {"ask", "exit", "tray"}:
        close_behavior = DEFAULT_SETTINGS["close_behavior"]
    if not bool(result.get("remember_close_choice", False)):
        close_behavior = "ask"
    result["close_behavior"] = close_behavior
    if "music_scan_folders" in result and not isinstance(result["music_scan_folders"], list):
        result["music_scan_folders"] = []
    return result


def write_settings_document(path: Path, document: dict[str, Any]) -> None:
    """Atomically write the existing settings document path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


class SettingsBridgeError(RuntimeError):
    """Raised when a settings snapshot cannot be validated or saved."""


class LegacySettingsBridge(QObject):
    """Facade over the one existing settings persistence source."""

    snapshot_changed = Signal(object)
    save_succeeded = Signal(object)
    save_failed = Signal(str)

    def __init__(
        self,
        settings_path: Path | str | None = None,
        *,
        apply_callback: Callable[[dict[str, Any]], None] | None = None,
        action_callbacks: dict[str, Callable[..., Any]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if settings_path is None:
            settings_path = AppPaths.resolve().data_dir / "settings.json"
        self.settings_path = Path(settings_path)
        self._apply_callback = apply_callback
        self._actions = dict(action_callbacks or {})

    def read_snapshot(self) -> SettingsSnapshot:
        snapshot = SettingsSnapshot.from_mapping(load_settings_document(self.settings_path))
        self.snapshot_changed.emit(snapshot)
        return snapshot

    def defaults(self) -> dict[str, Any]:
        return deepcopy(DEFAULT_SETTINGS)

    @staticmethod
    def value(snapshot: SettingsSnapshot, key: str) -> Any:
        return snapshot.get(key, deepcopy(DEFAULT_SETTINGS.get(key)))

    @staticmethod
    def validate(document: dict[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        mode = document.get("appearance_mode", DEFAULT_SETTINGS["appearance_mode"])
        if mode not in {"system", "light", "dark"}:
            errors["appearance_mode"] = "主题值无效。"
        visual_mode = document.get("immersive_background_visual_mode")
        if visual_mode is not None and str(visual_mode).strip().casefold() not in IMMERSIVE_BACKGROUND_VISUAL_MODES:
            errors["immersive_background_visual_mode"] = "沉浸背景显示模式无效。"
        close_behavior = str(document.get("close_behavior", "ask")).strip().casefold()
        if close_behavior not in {"ask", "exit", "tray"}:
            errors["close_behavior"] = "关闭窗口行为无效。"
        if not isinstance(document.get("remember_close_choice", False), bool):
            errors["remember_close_choice"] = "关闭行为记忆选项无效。"
        try:
            opacity = int(document.get("floating_lyrics_opacity", 100))
        except (TypeError, ValueError):
            opacity = -1
        if not 20 <= opacity <= 100:
            errors["floating_lyrics_opacity"] = "桌面歌词不透明度需在 20% 到 100% 之间。"
        try:
            font_size = int(document.get("floating_lyrics_font_size", 42))
        except (TypeError, ValueError):
            font_size = -1
        if not 22 <= font_size <= 84:
            errors["floating_lyrics_font_size"] = "桌面歌词字号需在 22 到 84 px 之间。"
        try:
            width = int(document.get("floating_lyrics_width", 980))
        except (TypeError, ValueError):
            width = -1
        if not 420 <= width <= 1600:
            errors["floating_lyrics_width"] = "桌面歌词宽度需在 420 到 1600 px 之间。"
        try:
            height = int(document.get("floating_lyrics_height", 135))
        except (TypeError, ValueError):
            height = -1
        if not 90 <= height <= 320:
            errors["floating_lyrics_height"] = "桌面歌词高度需在 90 到 320 px 之间。"
        for key, title in (("floating_lyrics_x", "横坐标"), ("floating_lyrics_y", "纵坐标")):
            try:
                coordinate = int(document.get(key, -1))
            except (TypeError, ValueError):
                coordinate = -2
            if not -100_000 <= coordinate <= 100_000:
                errors[key] = f"桌面歌词{title}无效。"
        if document.get("floating_lyrics_font_family", DEFAULT_SETTINGS["floating_lyrics_font_family"]) not in OPEN_FONT_FAMILIES:
            errors["floating_lyrics_font_family"] = "桌面歌词只能使用随应用分发的开放字体。"
        if not isinstance(document.get("floating_lyrics_passthrough", True), bool):
            errors["floating_lyrics_passthrough"] = "桌面歌词鼠标穿透设置无效。"
        try:
            delay = int(document.get("update_check_delay_seconds", 15))
        except (TypeError, ValueError):
            delay = -1
        if not 5 <= delay <= 300:
            errors["update_check_delay_seconds"] = "更新检查延迟需在 5 到 300 秒之间。"
        try:
            font_scale = int(document.get("immersive_lyrics_font_scale", 100))
        except (TypeError, ValueError):
            font_scale = -1
        if not 70 <= font_scale <= 160:
            errors["immersive_lyrics_font_scale"] = "沉浸歌词字号比例需在 70% 到 160% 之间。"
        folders = document.get("music_scan_folders", [])
        if not isinstance(folders, list) or any(not isinstance(item, str) for item in folders):
            errors["music_scan_folders"] = "音乐文件夹列表无效。"
        cache_directory = str(document.get("cache_directory", "") or "").strip()
        if cache_directory:
            candidate = Path(cache_directory).expanduser()
            if not candidate.is_absolute():
                errors["cache_directory"] = "缓存目录必须是绝对路径。"
            elif not candidate.is_dir():
                errors["cache_directory"] = "缓存目录不存在，请先选择现有文件夹。"
            elif not os.access(candidate, os.W_OK):
                errors["cache_directory"] = "缓存目录不可写，请选择其他文件夹。"
        return errors

    def save_snapshot(self, snapshot: SettingsSnapshot) -> SettingsSnapshot:
        document = snapshot.to_dict()
        document["remember_close_choice"] = bool(
            document.get("remember_close_choice", False)
        )
        if not document["remember_close_choice"]:
            document["close_behavior"] = "ask"
        errors = self.validate(document)
        if errors:
            message = next(iter(errors.values()))
            self.save_failed.emit(message)
            raise SettingsBridgeError(message)
        try:
            write_settings_document(self.settings_path, document)
            if self._apply_callback is not None:
                self._apply_callback(deepcopy(document))
        except Exception as error:
            message = f"保存设置失败：{error}"
            self.save_failed.emit(message)
            raise SettingsBridgeError(message) from error
        saved = SettingsSnapshot.from_mapping(document)
        self.save_succeeded.emit(saved)
        return saved

    def run_action(self, name: str, *args, **kwargs):
        callback = self._actions.get(str(name))
        if callback is None:
            raise SettingsBridgeError(f"设置操作不可用：{name}")
        return callback(*args, **kwargs)

    def has_action(self, name: str) -> bool:
        """Expose availability without leaking the callback registry."""

        return callable(self._actions.get(str(name)))
