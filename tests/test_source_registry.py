"""R7 回归：MusicFree 兼容插件可以安装、识别元数据、删除与恢复。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hushplayer.online.registry import SourceRegistry, peek_plugin_metadata

PLUGIN = """module.exports = {
    platform: "测试音乐",
    version: "0.1.2",
    author: "qa",
    capabilities: [],

    async search(query) {
        return [{ id: "1", title: query, artist: "QA" }];
    },

    async getMediaSource(song) {
        return { url: "https://example.com/a.mp3" };
    },
};
"""


def test_peek_metadata_without_executing() -> None:
    meta = peek_plugin_metadata(PLUGIN.encode("utf-8"))
    assert meta["platform"] == "测试音乐"
    assert meta["version"] == "0.1.2"
    assert meta["author"] == "qa"


@pytest.fixture()
def registry(tmp_path, monkeypatch) -> SourceRegistry:
    from hushplayer.online import registry as registry_module

    monkeypatch.setattr(registry_module, "data_dir", lambda: tmp_path)
    store = SourceRegistry()
    store.ensure()
    return store


def test_install_uses_declared_platform_name(registry: SourceRegistry, tmp_path: Path) -> None:
    plugin = tmp_path / "some-plugin.js"
    plugin.write_text(PLUGIN, encoding="utf-8")

    entry = registry.install_file(plugin)
    assert entry["name"] == "测试音乐"
    assert entry["version"] == "0.1.2"
    assert entry["userInstalled"] is True
    assert (registry.home / entry["filename"]).is_file()

    stored = json.loads(registry.registry_path.read_text(encoding="utf-8"))
    assert any(item["id"] == entry["id"] for item in stored["sources"])

    # the same bytes cannot be installed twice
    with pytest.raises(Exception):
        registry.install_file(plugin)

    assert registry.remove(entry["id"]) is True
    stored = json.loads(registry.registry_path.read_text(encoding="utf-8"))
    assert not any(item["id"] == entry["id"] for item in stored["sources"])


def test_rejects_oversized_or_wrong_type(registry: SourceRegistry, tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    text.write_text("hello", encoding="utf-8")
    with pytest.raises(Exception):
        registry.install_file(text)

    big = tmp_path / "big.js"
    big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(Exception):
        registry.install_file(big)


def test_collect_plugin_files_skips_other_types(tmp_path: Path) -> None:
    from hushplayer.online.registry import collect_plugin_files

    (tmp_path / "a.js").write_text("module.exports = {}", encoding="utf-8")
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    modules = tmp_path / "node_modules"
    modules.mkdir()
    (modules / "dep.js").write_text("module.exports = {}", encoding="utf-8")

    names = [path.name for path in collect_plugin_files(tmp_path)]
    assert names == ["a.js", "b.json"]


def test_install_many_reports_and_continues(registry: SourceRegistry, tmp_path: Path) -> None:
    first = tmp_path / "one.js"
    first.write_text(PLUGIN.replace("测试音乐", "源一"), encoding="utf-8")
    second = tmp_path / "two.js"
    second.write_text(PLUGIN.replace("测试音乐", "源二").replace("0.1.2", "0.2.0"), encoding="utf-8")
    broken = tmp_path / "broken.txt"
    broken.write_text("not a plugin", encoding="utf-8")

    report = registry.install_many([first, second, first, broken])

    assert [entry["name"] for entry in report.installed] == ["源一", "源二"]
    assert report.duplicates == ["one.js"]
    assert report.failed and report.failed[0][0] == "broken.txt"
    assert report.total == 4
    assert "已安装 2 个音源" in report.summary()

    stored = json.loads(registry.registry_path.read_text(encoding="utf-8"))
    user_ids = [item["id"] for item in stored["sources"] if str(item["id"]).startswith("user_source_")]
    assert len(user_ids) == 2
