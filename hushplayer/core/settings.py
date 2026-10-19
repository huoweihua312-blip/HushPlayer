"""分层设置存储。

所有可配置项集中在这里：一份默认值、一个 JSON 文件、一条 ``changed`` 信号。
界面只通过点号路径读写，避免各处硬编码文件名与默认值。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from . import paths
from .logging_setup import get_logger

log = get_logger("settings")
_MISSING = object()

DEFAULTS: dict[str, Any] = {
    "schema": 1,
    "general": {
        "language": "zh_CN",
        "start_page": "home",
        "restore_last_page": True,
        "remember_queue": True,
        "close_action": "quit",  # quit | tray
        "minimize_to_tray": False,
        "launch_at_startup": False,
        "check_updates_on_start": True,
        "system_media_controls": True,
        "taskbar_progress": True,
        "global_hotkeys": True,
        "last_page": "home",
        "first_run_done": False,
        "window": {"x": None, "y": None, "w": 1280, "h": 820, "maximized": False},
    },
    "appearance": {
        "theme": "system",  # system | light | dark
        "accent": "#C95770",
        "reduce_motion": False,
        "font_scale": 1.0,
        "ui_scale": "auto",  # auto | 1.0 | 1.15 | 1.25 | 1.5（需重启）
        "sidebar_visible": True,
        "density": "comfortable",  # comfortable | compact
        "show_source_badge": True,
    },
    "playback": {
            "sleep_timer_minutes": 0,
        "volume": 0.72,
        "muted": False,
        "repeat": "off",  # off | all | one
        "shuffle": False,
        "quality": "higher",  # standard | higher | exhigh | lossless
        "resume_on_start": True,
        "audio_device": "",
        "fade_ms": 180,
        "skip_unavailable": True,
    },
    "lyrics": {
        "font_scale": 1.0,
        "translate": True,
        "offset_ms": 0,
        "alignment": "center",  # center | left
        "online_enabled": True,
        "prefer_word_timing": True,
        "show_metadata": True,
    },
    "desktop_lyrics": {
        "enabled": False,
        "locked": False,
        "click_through": False,
        "always_on_top": True,
        "font_family": "",
        "font_size": 32,
        "color": "#FFFFFF",
        "highlight_color": "#C95770",
        "opacity": 0.94,
        "lines": 2,
        "show_translation": True,
        "geometry": None,
        "screen": "",
    },
    "library": {
        "folders": [],
        "auto_scan_on_start": True,
        "watch": True,
        "last_scan": 0,
        "cover_from_folder": True,
    },
    "online": {
            "dedupe_results": True,
        "sources_expanded": False,
        "enabled_sources": {},
        "preferred_source": "",
        "search_all": True,
        "timeout_s": 22,
        "show_explicit": True,
        "default_quality": "higher",
    },
    "cache": {
        "enabled": True,
        "max_mb": 2048,
        "dir": "",
    },
    "downloads": {
        "dir": "",
        "quality": "higher",
        "naming": "{artist} - {title}",
        "embed_metadata": True,
    },
    "immersive": {
        "mode": "cover",  # cover | lyrics
        "last_mode": "cover",
        "ambient": True,
        "motion": True,
    },
    "update": {
        "manifest_url": "",  # 留空表示未配置更新源；见 docs/UPDATES.md
        "last_check": 0,
        "skipped_version": "",
    },
}


class Settings(QObject):
    changed = Signal(str, object)
    reset_signal = Signal()

    def __init__(self, path: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = Path(path) if path else paths.settings_file()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(350)
        self._save_timer.timeout.connect(self.flush)
        self._dirty = False

    # ------------------------------------------------------------------ 读写
    def load(self) -> None:
        data: dict[str, Any] = {}
        try:
            if self._path.is_file():
                data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("设置文件损坏，使用默认值: %s", exc)
            try:
                shutil.copy2(self._path, self._path.with_suffix(".corrupt.json"))
            except OSError:
                pass
        if not isinstance(data, dict):
            data = {}
        self._data = _deep_merge(copy.deepcopy(DEFAULTS), data)
        self._dirty = False

    def flush(self) -> None:
        if not self._dirty:
            return
        self._write()
        self._dirty = False

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            if self._path.is_file():
                try:
                    shutil.copy2(self._path, self._path.with_suffix(".bak"))
                except OSError:
                    pass
            os.replace(tmp, self._path)
        except OSError as exc:
            log.error("写入设置失败: %s", exc)

    # ------------------------------------------------------------------ 访问
    def get(self, key: str, default: Any = _MISSING) -> Any:
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is not _MISSING:
                    return default
                fallback: Any = DEFAULTS
                for fallback_part in key.split("."):
                    if not isinstance(fallback, dict) or fallback_part not in fallback:
                        return None
                    fallback = fallback[fallback_part]
                return fallback
            node = node[part]
        return node

    def set(self, key: str, value: Any, *, save: bool = True) -> bool:
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        if node.get(parts[-1]) == value:
            return False
        node[parts[-1]] = value
        self._dirty = True
        if save:
            self._save_timer.start()
        self.changed.emit(key, value)
        return True

    def update(self, mapping: dict[str, Any], *, save: bool = True) -> None:
        for key, value in mapping.items():
            self.set(key, value, save=False)
        self._dirty = True
        if save:
            self._save_timer.start()

    def toggle(self, key: str) -> bool:
        value = not bool(self.get(key))
        self.set(key, value)
        return value

    def reset(self, prefix: str | None = None) -> None:
        if not prefix:
            self._data = copy.deepcopy(DEFAULTS)
        else:
            parts = prefix.split(".")
            default_node: Any = DEFAULTS
            for part in parts:
                default_node = default_node.get(part, {}) if isinstance(default_node, dict) else {}
            if isinstance(default_node, dict):
                self._set_subtree(parts, copy.deepcopy(default_node))
        self._dirty = True
        self.flush()
        self.reset_signal.emit()

    def _set_subtree(self, parts: list[str], value: Any) -> None:
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    @property
    def path(self) -> Path:
        return self._path


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.load()
    return _settings


def set_settings(instance: Settings) -> None:
    global _settings
    _settings = instance
