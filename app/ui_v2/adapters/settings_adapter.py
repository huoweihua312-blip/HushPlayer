"""In-memory draft, preview, and mock-operation adapter for UI V2 settings."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Any

from PySide6.QtCore import QObject, Signal

from app.ui_v2.adapters.lyrics_adapter import LyricsAdapter
from app.ui_v2.models.immersive_lyrics_options import ImmersiveLyricsOptions
from app.ui_v2.models.settings_search_result import SettingsSearchResult
from app.ui_v2.models.settings_state import ImmersiveSettings, SettingsState


SEARCH_ENTRIES: tuple[SettingsSearchResult, ...] = (
    SettingsSearchResult("general.restore_last_session", "常规", "恢复上次会话", "启动时恢复上次浏览状态", ("session", "startup")),
    SettingsSearchResult("general.auto_open_floating_lyrics", "常规", "自动打开桌面歌词", "播放时打开桌面歌词预览", ("floating", "desktop lyrics")),
    SettingsSearchResult("general.minimize_to_tray", "常规", "最小化到托盘", "最小化后保留在通知区域", ("tray",)),
    SettingsSearchResult("general.close_behavior", "常规", "关闭窗口行为", "选择直接退出、最小化或询问", ("close", "exit")),
    SettingsSearchResult("general.remember_close_choice", "常规", "记住关闭窗口时的选择", "关闭后保留上次选择，关闭此项可恢复每次询问", ("close", "remember", "tray")),
    SettingsSearchResult("general.language", "常规", "界面语言", "选择界面语言偏好", ("language", "english")),
    SettingsSearchResult("appearance.theme_mode", "外观", "主题", "跟随系统、浅色或深色主题", ("theme", "light", "dark")),
    SettingsSearchResult("appearance.accent_mode", "外观", "强调色", "控制界面的强调颜色模式", ("accent", "color")),
    SettingsSearchResult("appearance.ui_scale", "外观", "UI 整体缩放", "预览设置页面的界面比例", ("scale", "zoom")),
    SettingsSearchResult("appearance.compact_density", "外观", "紧凑密度", "减小设置行之间的间距", ("compact", "density")),
    SettingsSearchResult("appearance.reduce_motion", "外观", "减少动态效果", "减少设置与沉浸歌词预览动画", ("motion", "animation")),
    SettingsSearchResult("playback.autoplay_on_start", "播放", "启动自动播放", "启动时继续播放上次的队列", ("autoplay",)),
    SettingsSearchResult("playback.default_volume", "播放", "默认音量", "新会话的备用默认音量", ("volume",)),
    SettingsSearchResult("playback.remember_volume", "播放", "记住上次音量", "优先使用上次的音量", ("remember volume",)),
    SettingsSearchResult("playback.gapless_enabled", "播放", "无缝播放", "连续曲目之间保持平滑衔接", ("gapless",)),
    SettingsSearchResult("playback.crossfade_enabled", "播放", "交叉淡化", "切歌时启用交叉淡化", ("crossfade",)),
    SettingsSearchResult("playback.crossfade_seconds", "播放", "交叉淡化秒数", "设置交叉淡化的持续时间", ("crossfade seconds",)),
    SettingsSearchResult("playback.replay_gain_mode", "播放", "ReplayGain", "选择音量标准化策略", ("gain",)),
    SettingsSearchResult("playback.output_device_mock", "播放", "输出设备", "选择音频输出设备", ("device", "output")),
    SettingsSearchResult("lyrics.show_translation", "歌词", "显示翻译", "普通歌词与沉浸歌词同步显示翻译", ("translation",)),
    SettingsSearchResult("lyrics.lyrics_font_scale", "歌词", "整体歌词大小", "调整普通歌词的文字比例", ("lyrics size", "font")),
    SettingsSearchResult("lyrics.lyrics_alignment", "歌词", "歌词对齐", "设置普通歌词的阅读对齐偏好", ("alignment",)),
    SettingsSearchResult("lyrics.auto_follow", "歌词", "自动跟随", "播放时跟随当前歌词行", ("follow",)),
    SettingsSearchResult("lyrics.manual_browse_timeout", "歌词", "手动浏览超时", "浏览歌词后返回当前行的等待时间", ("browse", "timeout")),
    SettingsSearchResult("lyrics.lyrics_offset_ms", "歌词", "歌词偏移", "提前或延后同步时间", ("offset", "sync")),
    SettingsSearchResult("immersive.background_mode", "沉浸歌词", "背景模式", "封面、渐变、纯色或透明背景", ("background", "transparent", "opacity")),
    SettingsSearchResult("immersive.global_font_scale", "沉浸歌词", "整体歌词大小", "按比例调整当前、普通和翻译歌词字号", ("lyrics", "font", "scale")),
    SettingsSearchResult("immersive.controls_auto_hide", "沉浸歌词", "控制层自动隐藏", "播放时静止后收起控制层", ("controls", "auto hide")),
    SettingsSearchResult("library.mock_music_folders", "音乐库", "音乐文件夹", "管理需要扫描的音乐位置", ("folder", "path")),
    SettingsSearchResult("library.scan_on_start", "音乐库", "启动扫描", "启动时扫描音乐文件夹", ("scan",)),
    SettingsSearchResult("cache.cache_limit_mb", "缓存", "缓存上限", "设置可使用的缓存容量", ("cache", "storage")),
    SettingsSearchResult("cache.artwork_cache_enabled", "缓存", "封面缓存", "启用封面缓存", ("artwork",)),
    SettingsSearchResult("updates.auto_check_updates", "更新", "自动检查更新", "启动后检查可用更新", ("update", "check")),
    SettingsSearchResult("updates.update_channel", "更新", "更新通道", "选择稳定版或测试版更新通道", ("beta", "channel")),
)


class SettingsAdapter(QObject):
    """Owns draft state and all non-persistent UI V2 setting previews."""

    draft_changed = Signal(object)
    dirty_changed = Signal(bool)
    validation_changed = Signal(bool, object)
    saved = Signal(object)
    cancelled = Signal(object)
    defaults_restored = Signal()
    category_defaults_restored = Signal(str)
    theme_preview_changed = Signal(str)
    immersive_preview_changed = Signal(object)
    lyrics_preview_changed = Signal(object)
    motion_preview_changed = Signal(bool)
    cache_stats_changed = Signal(object)
    mock_feedback_changed = Signal(str, str)
    update_status_changed = Signal(object)

    def __init__(
        self,
        lyrics: LyricsAdapter,
        immersive_options: ImmersiveLyricsOptions,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._lyrics = lyrics
        self._immersive_options = immersive_options
        self._default_state = SettingsState()
        self._copy_immersive_options_into(self._default_state.immersive)
        self._persisted_state = self._default_state.copy()
        self._draft_state = self._persisted_state.copy()
        self._cache_stats = {
            "artwork": 186,
            "lyrics": 42,
            "audio": 0,
            "incomplete": 24,
            "total": 252,
        }
        self._update_cursor = 0
        self._applying_lyrics_preview = False
        self._applying_immersive_preview = False
        lyrics.display_options_changed.connect(self._sync_from_lyrics_adapter)
        lyrics.offset_changed.connect(self._sync_offset_from_lyrics_adapter)
        self._emit_state_changes()

    def state(self) -> SettingsState:
        return self._persisted_state.copy()

    def draft(self) -> SettingsState:
        return self._draft_state.copy()

    def default_state(self) -> SettingsState:
        return self._default_state.copy()

    def set_value(self, path: str, value: Any) -> None:
        if self._draft_state.get_value(path) == value:
            return
        self._draft_state.set_value(path, value)
        self._apply_preview_for_path(path)
        self._emit_state_changes()

    def get_value(self, path: str) -> Any:
        return deepcopy(self._draft_state.get_value(path))

    def is_dirty(self) -> bool:
        return bool(self.dirty_fields())

    def dirty_fields(self) -> frozenset[str]:
        return self._draft_state.dirty_fields_against(self._persisted_state)

    def validate(self) -> tuple[bool, dict[str, str]]:
        draft = self._draft_state
        errors: dict[str, str] = {}
        if draft.playback.crossfade_enabled and not 1 <= draft.playback.crossfade_seconds <= 12:
            errors["playback.crossfade_seconds"] = "交叉淡化时间需在 1 到 12 秒之间。"
        if not 0 <= draft.playback.default_volume <= 100:
            errors["playback.default_volume"] = "默认音量需在 0 到 100 之间。"
        if not 80 <= round(draft.lyrics.lyrics_font_scale * 100) <= 145:
            errors["lyrics.lyrics_font_scale"] = "歌词缩放需在 80% 到 145% 之间。"
        if not -10_000 <= draft.lyrics.lyrics_offset_ms <= 10_000:
            errors["lyrics.lyrics_offset_ms"] = "歌词偏移需在 -10000 到 10000 ms 之间。"
        if not 128 <= draft.cache.cache_limit_mb <= 8192:
            errors["cache.cache_limit_mb"] = "缓存上限需在 128 到 8192 MB 之间。"
        return not errors, errors

    def save(self) -> bool:
        valid, _errors = self.validate()
        if not valid:
            self._emit_state_changes()
            return False
        self._persisted_state = self._draft_state.copy()
        self._apply_all_previews()
        self._emit_state_changes()
        self.saved.emit(self.state())
        self.mock_feedback_changed.emit("已保存", "设置已保存。")
        return True

    def cancel(self) -> None:
        self._draft_state = self._persisted_state.copy()
        self._apply_all_previews()
        self._emit_state_changes()
        self.cancelled.emit(self.draft())
        self.mock_feedback_changed.emit("已取消", "已恢复进入设置前的状态。")

    def restore_defaults(self) -> None:
        self._draft_state = self._default_state.copy()
        self._apply_all_previews()
        self._emit_state_changes()
        self.defaults_restored.emit()
        self.mock_feedback_changed.emit("已恢复默认", "默认值尚未保存。")

    def restore_category_defaults(self, category: str) -> None:
        if not hasattr(self._draft_state, category):
            self.mock_feedback_changed.emit("无需恢复默认", "当前分类没有可编辑的设置项。")
            return
        setattr(self._draft_state, category, deepcopy(getattr(self._default_state, category)))
        self._apply_preview_for_category(category)
        self._emit_state_changes()
        self.category_defaults_restored.emit(category)
        self.mock_feedback_changed.emit("已恢复分类默认", "默认值尚未保存。")

    def reset_draft_from_persisted(self) -> None:
        self.cancel()

    def apply_theme_preview(self) -> None:
        mode = self._draft_state.appearance.theme_mode
        self.theme_preview_changed.emit("dark" if mode == "system" else mode)

    def apply_immersive_preview(self) -> None:
        self._applying_immersive_preview = True
        try:
            source = self._draft_state.immersive
            for value_field in fields(source):
                setattr(self._immersive_options, value_field.name, deepcopy(getattr(source, value_field.name)))
            self.immersive_preview_changed.emit(self._immersive_options)
        finally:
            self._applying_immersive_preview = False

    def search(self, query: str) -> tuple[SettingsSearchResult, ...]:
        value = str(query).strip()
        if not value:
            return ()
        return tuple(item for item in SEARCH_ENTRIES if item.matches(value))

    def add_mock_folder(self, path: str) -> bool:
        normalized = str(path).strip()
        folders = self._draft_state.library.mock_music_folders
        if not normalized or normalized in folders:
            return False
        folders.append(normalized)
        self._emit_state_changes()
        self.mock_feedback_changed.emit("已添加音乐文件夹", normalized)
        return True

    def remove_mock_folder(self, path: str) -> bool:
        folders = self._draft_state.library.mock_music_folders
        if path not in folders:
            return False
        folders.remove(path)
        self._emit_state_changes()
        self.mock_feedback_changed.emit("已移除音乐文件夹", path)
        return True

    def cache_stats(self) -> dict[str, int]:
        return dict(self._cache_stats)

    def refresh_mock_cache_stats(self) -> None:
        self._cache_stats["artwork"] = 186
        self._cache_stats["lyrics"] = 42
        self._cache_stats["audio"] = 0 if not self._draft_state.cache.online_audio_cache_enabled else 118
        self._cache_stats["total"] = sum(self._cache_stats[key] for key in ("artwork", "lyrics", "audio", "incomplete"))
        self.cache_stats_changed.emit(self.cache_stats())
        self.mock_feedback_changed.emit("缓存统计已刷新", "已更新当前缓存用量。")

    def clear_mock_incomplete_cache(self) -> None:
        self._cache_stats["incomplete"] = 0
        self._cache_stats["total"] = sum(self._cache_stats[key] for key in ("artwork", "lyrics", "audio"))
        self.cache_stats_changed.emit(self.cache_stats())
        self.mock_feedback_changed.emit("已清理未完成缓存", "未完成缓存已移除。")

    def clear_all_mock_cache(self) -> None:
        for key in ("artwork", "lyrics", "audio", "incomplete", "total"):
            self._cache_stats[key] = 0
        self.cache_stats_changed.emit(self.cache_stats())
        self.mock_feedback_changed.emit("已清理全部缓存", "缓存已清理。")

    def check_mock_updates(self) -> dict[str, str]:
        scenarios = (
            {"phase": "latest", "title": "已是最新版本", "detail": "HushPlayer 已是最新版本。"},
            {"phase": "available", "title": "发现新版本", "detail": "有可用的新版本。"},
            {"phase": "failed", "title": "检查失败", "detail": "暂时无法检查更新，请稍后重试。"},
        )
        result = scenarios[self._update_cursor % len(scenarios)]
        self._update_cursor += 1
        self.update_status_changed.emit(dict(result))
        return dict(result)

    def sync_immersive_options(self, _options: ImmersiveLyricsOptions | None = None) -> None:
        """Accept direct edits made in the immersive floating settings panel."""
        if self._applying_immersive_preview:
            return
        target = ImmersiveSettings()
        self._copy_immersive_options_into(target)
        self._persisted_state.immersive = deepcopy(target)
        self._draft_state.immersive = deepcopy(target)
        self._emit_state_changes()

    def _copy_immersive_options_into(self, target: ImmersiveSettings) -> None:
        for value_field in fields(target):
            setattr(target, value_field.name, deepcopy(getattr(self._immersive_options, value_field.name)))

    def _sync_from_lyrics_adapter(self, options: dict[str, object]) -> None:
        if self._applying_lyrics_preview:
            return
        values = {
            "lyrics.show_translation": bool(options.get("translation")),
            "lyrics.lyrics_font_scale": float(options.get("font_scale", 1.0)),
        }
        self._sync_external_values(values)

    def _sync_offset_from_lyrics_adapter(self, offset_ms: int) -> None:
        if not self._applying_lyrics_preview:
            self._sync_external_values({"lyrics.lyrics_offset_ms": int(offset_ms)})

    def _sync_external_values(self, values: dict[str, object]) -> None:
        changed = False
        for path, value in values.items():
            if self._persisted_state.get_value(path) != value:
                self._persisted_state.set_value(path, value)
                changed = True
            if self._draft_state.get_value(path) != value:
                self._draft_state.set_value(path, value)
                changed = True
        if changed:
            self._emit_state_changes()

    def _apply_all_previews(self) -> None:
        self.apply_theme_preview()
        self.apply_immersive_preview()
        self._apply_lyrics_preview()
        self.motion_preview_changed.emit(self._draft_state.appearance.reduce_motion)

    def _apply_preview_for_path(self, path: str) -> None:
        self._apply_preview_for_category(path.partition(".")[0])

    def _apply_preview_for_category(self, category: str) -> None:
        if category == "appearance":
            self.apply_theme_preview()
            self.motion_preview_changed.emit(self._draft_state.appearance.reduce_motion)
        elif category == "immersive":
            self.apply_immersive_preview()
        elif category == "lyrics":
            self._apply_lyrics_preview()

    def _apply_lyrics_preview(self) -> None:
        self._applying_lyrics_preview = True
        try:
            draft = self._draft_state.lyrics
            display = self._lyrics.display_options
            if bool(display["translation"]) != draft.show_translation:
                self._lyrics.toggle_translation()
            self._lyrics.set_font_scale(draft.lyrics_font_scale)
            self._lyrics.set_offset(draft.lyrics_offset_ms)
            self.lyrics_preview_changed.emit({
                "alignment": draft.lyrics_alignment,
                "auto_follow": draft.auto_follow,
                "manual_browse_timeout": draft.manual_browse_timeout,
            })
        finally:
            self._applying_lyrics_preview = False

    def _emit_state_changes(self) -> None:
        valid, errors = self.validate()
        self.draft_changed.emit(self.draft())
        self.dirty_changed.emit(self.is_dirty())
        self.validation_changed.emit(valid, errors)
