"""设置：默认值、持久化、原子写、损坏恢复与前缀重置。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hushplayer.core import settings as settings_module
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


# --------------------------------------------------------------- 写入失败语义


def test_failed_write_keeps_dirty_and_original_file(tmp_path, monkeypatch) -> None:
    """写盘失败时：内存值保留、dirty 不清、旧文件不被破坏。"""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"appearance": {"theme": "dark"}}), encoding="utf-8")
    settings = make_settings(tmp_path)
    settings.load()
    settings.set("playback.volume", 0.41)

    def boom(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(settings_module.os, "replace", boom)
    assert settings.flush() is False
    assert settings.get("playback.volume") == 0.41, "内存中的最新设置不能丢"
    assert settings._dirty is True, "写盘失败后必须保持待保存状态"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["appearance"]["theme"] == "dark", "旧文件必须保持可读且不被覆盖"
    assert raw.get("playback", {}).get("volume") != 0.41


def test_failed_write_recovers_on_retry(tmp_path, monkeypatch) -> None:
    """恢复写权限后，之前未落盘的数据必须能再次写入。"""
    settings = make_settings(tmp_path)
    settings.set("playback.volume", 0.27)

    original_replace = os.replace
    monkeypatch.setattr(
        settings_module.os,
        "replace",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError(5, "denied")),
    )
    assert settings.flush() is False
    settings.set("appearance.theme", "light")

    monkeypatch.setattr(settings_module.os, "replace", original_replace)
    assert settings.flush() is True
    assert settings._dirty is False
    reloaded = make_settings(tmp_path)
    reloaded.load()
    assert abs(reloaded.get("playback.volume") - 0.27) < 1e-6
    assert reloaded.get("appearance.theme") == "light"


def test_unwritable_directory_does_not_raise(tmp_path) -> None:
    """目录本身不可创建时（父路径是文件），flush 必须返回 False 而不是抛异常。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    settings = Settings(blocker / "settings.json")
    settings.set("playback.volume", 0.5)
    assert settings.flush() is False
    assert settings.get("playback.volume") == 0.5
    assert settings._dirty is True


def test_failed_write_does_not_clobber_backup(tmp_path, monkeypatch) -> None:
    """失败写入不能删除上一次成功写入留下的 .bak 备份。"""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"appearance": {"theme": "system"}}), encoding="utf-8")
    settings = make_settings(tmp_path)
    settings.load()
    settings.set("appearance.theme", "dark")
    assert settings.flush() is True
    backup = tmp_path / "settings.bak"
    assert backup.is_file(), "成功写入前应先把旧文件复制为 .bak"
    before = backup.read_bytes()

    settings.set("appearance.theme", "light")
    monkeypatch.setattr(
        settings_module.os,
        "replace",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError(5, "denied")),
    )
    assert settings.flush() is False
    assert backup.read_bytes() == before
