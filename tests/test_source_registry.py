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
