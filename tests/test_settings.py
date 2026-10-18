"""设置：默认值、持久化、原子写、损坏恢复与前缀重置。"""

from __future__ import annotations

import json
from pathlib import Path

from hushplayer.core.settings import DEFAULTS, Settings


def make_settings(tmp_path: Path, name: str = "settings.json") -> Settings:
    return Settings(tmp_path / name)


def test_defaults_are_complete(tmp_path) -> None:
    settings = make_settings(tmp_path)
    assert settings.get("appearance.theme") == "system"
    assert settings.get("appearance.accent").lower() == "#c95770"
    assert settings.get("playback.volume") == DEFAULTS["playback"]["volume"]
    assert settings.get("lyrics.translate") == DEFAULTS["lyrics"]["translate"]
    assert settings.get("missing.key", "fallback") == "fallback"
    assert settings.get("appearance.not_a_key", 7) == 7


def test_set_and_persist(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.set("appearance.theme", "dark")
    settings.set("playback.volume", 0.33)
    settings.set("library.folders", ["C:/Music"])
    settings.flush()

    reloaded = make_settings(tmp_path)
    reloaded.load()
    assert reloaded.get("appearance.theme") == "dark"
    assert abs(reloaded.get("playback.volume") - 0.33) < 1e-6
    assert reloaded.get("library.folders") == ["C:/Music"]


def test_nested_update_and_toggle(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.update({"appearance.reduce_motion": True, "playback.shuffle": True})
    assert settings.get("appearance.reduce_motion") is True
    assert settings.toggle("playback.shuffle") is False
    assert settings.get("playback.shuffle") is False


def test_reset_prefix(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.set("lyrics.translate", True)
    settings.set("lyrics.font_scale", 1.4)
    settings.set("appearance.theme", "light")
    settings.reset("lyrics")
    assert settings.get("lyrics.translate") == DEFAULTS["lyrics"]["translate"]
    assert settings.get("lyrics.font_scale") == DEFAULTS["lyrics"]["font_scale"]
    assert settings.get("appearance.theme") == "light"


def test_change_signal(tmp_path, qapp) -> None:
    settings = make_settings(tmp_path)
    seen: list[tuple[str, object]] = []
    settings.changed.connect(lambda key, value: seen.append((key, value)))
    settings.set("appearance.theme", "dark")
    settings.set("appearance.theme", "dark")  # 相同值不应重复发信号
    assert seen == [("appearance.theme", "dark")]


def test_corrupt_file_is_quarantined(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ this is not json", encoding="utf-8")
    settings = make_settings(tmp_path)
    settings.load()
    assert settings.get("appearance.theme") == "system"
    backups = list(tmp_path.glob("*.corrupt*"))
    assert backups, "损坏的设置文件应被另存备份，而不是直接丢弃"


def test_unknown_keys_are_preserved(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"future": {"flag": True}, "appearance": {"theme": "dark"}}), encoding="utf-8")
    settings = make_settings(tmp_path)
    settings.load()
    assert settings.get("appearance.theme") == "dark"
    settings.set("playback.volume", 0.5)
    settings.flush()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["future"]["flag"] is True, "未知字段必须保留，便于降级/回滚"


def test_atomic_write_leaves_no_temp_file(tmp_path) -> None:
    settings = make_settings(tmp_path)
    settings.set("appearance.theme", "light")
    settings.flush()
    leftovers = [item.name for item in tmp_path.iterdir() if item.name.endswith(".tmp")]
    assert leftovers == []
