"""R7 回归：MusicFree 兼容插件可以安装、识别元数据、删除与恢复。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hushplayer.online.registry import (
    SourceRegistry,
    peek_plugin_metadata,
    subscription_entries,
)

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


def test_subscription_entries_accepts_common_shapes() -> None:
    assert subscription_entries({"plugins": [{"url": "a"}]}) == [{"url": "a"}]
    assert subscription_entries({"sources": [{"url": "b"}]}) == [{"url": "b"}]
    assert subscription_entries({"data": [{"url": "c"}]}) == [{"url": "c"}]
    assert subscription_entries([{"url": "d"}]) == [{"url": "d"}]
    assert subscription_entries({"foo": 1}) == []
    assert subscription_entries("nope") == []


def _serve(directory: Path):
    import functools
    import http.server
    import threading

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_install_subscription_downloads_and_keeps_going(registry) -> None:
    import json

    folder = registry.home / "_test_subscription"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "a.js").write_text(PLUGIN, encoding="utf-8")
    (folder / "b.js").write_text(PLUGIN.replace("a.mp3", "b.mp3"), encoding="utf-8")
    (folder / "mf.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "订阅源 A", "url": "__BASE__/a.js", "version": "9.9"},
                    {"name": "订阅源 B", "url": "__BASE__/b.js"},
                    {"name": "坏源", "url": "__BASE__/missing.js"},
                ]
            }
        ),
        encoding="utf-8",
    )
    server, base = _serve(folder)
    (folder / "mf.json").write_text(
        (folder / "mf.json").read_text(encoding="utf-8").replace("__BASE__", base),
        encoding="utf-8",
    )
    try:
        report = registry.install_subscription(f"{base}/mf.json")
    finally:
        server.shutdown()
        server.server_close()

    assert [entry["name"] for entry in report.installed] == ["订阅源 A", "订阅源 B"]
    assert report.duplicates == []
    assert len(report.failed) == 1 and report.failed[0][0] == "坏源"
    assert report.installed[0]["version"] == "9.9"
    saved = registry.entries()
    assert sum(1 for entry in saved if entry.get("userInstalled")) >= 2


def test_preview_subscription_counts_new_plugins(tmp_path, monkeypatch):
    import http.server
    import json
    import threading

    monkeypatch.setenv("HUSHPLAYER_DATA_DIR", str(tmp_path / "data"))
    from hushplayer.core import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "data")

    plugin = "module.exports = { platform: '预览源', search() { return [] } }".encode("utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):  # noqa: N802
            if self.path.endswith(".js"):
                body = plugin
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
            else:
                body = json.dumps({"plugins": [{"name": "预览源", "url": f"http://127.0.0.1:{self.server.server_address[1]}/p.js"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        from hushplayer.online.registry import SourceRegistry

        reg = SourceRegistry()
        url = f"http://127.0.0.1:{httpd.server_address[1]}/mf.json"
        first = reg.preview_subscription(url)
        assert first["new"] == 1
        reg.install_subscription(url)
        second = reg.preview_subscription(url)
        assert second["new"] == 0
    finally:
        httpd.shutdown()
        thread.join(timeout=3)
