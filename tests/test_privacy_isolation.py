"""隐私隔离与安全发布体系回归测试。

覆盖四层隔离：
1. 用户音源只存在于数据目录，开发仓库里不再跟踪；
2. 旧目录 → 数据目录的迁移可续、不覆盖、不丢启用状态；
3. 敏感信息扫描能拦住 Cookie / 真实数据库 / 个人插件目录；
4. 发行布局不允许出现个人数据，构建脚本与 Git 钩子强制检查。

所有凭据都是测试用例里现造的假值，不读取真实用户数据。
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import security_scan  # noqa: E402

from hushplayer.online import registry as registry_module  # noqa: E402
from hushplayer.online import source_migration  # noqa: E402
from hushplayer.online.registry import SourceRegistry  # noqa: E402

PLUGIN_JS = """
module.exports = {
  platform: 'test',
  name: 'Fixture Source',
  version: '1.0.0',
  async search(keyword) { return []; },
  async resolvePlayback(item) { return { url: 'https://example.invalid/a.mp3' }; },
};
""".strip()


def _legacy_plugin(root: Path, name: str = "alpha.js") -> Path:
    path = root / "sources" / "active" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLUGIN_JS, encoding="utf-8")
    return path


def _legacy_registry(root: Path, entries: list[dict]) -> Path:
    path = root / "source_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "sources": entries}, ensure_ascii=False), encoding="utf-8")
    return path


def _entry(identifier: str = "legacy_alpha", *, enabled: bool = True) -> dict:
    return {
        "id": identifier,
        "name": identifier,
        "platform": "test",
        "version": "1.0.0",
        "filename": f"sources/active/{identifier}.js",
        "enabled": enabled,
        "userInstalled": True,
    }


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """把 data_dir 指向临时目录，避免碰真实用户数据。"""

    monkeypatch.setattr(registry_module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(source_migration, "data_dir", lambda: tmp_path)
    # 默认没有「旧程序目录」可迁移：模拟新用户第一次启动。
    monkeypatch.setattr(source_migration, "legacy_roots", lambda: [])
    return tmp_path


# --------------------------------------------------------------------- 音源隔离
def test_empty_sources_start_without_crash(isolated):
    store = SourceRegistry()
    store.ensure()

    assert store.entries() == []
    document = json.loads((isolated / "sources" / "source_registry.json").read_text(encoding="utf-8"))
    assert document == {"version": 1, "sources": []}


def test_user_installed_plugin_becomes_available(isolated, tmp_path):
    plugin = tmp_path / "download.js"
    plugin.write_text(PLUGIN_JS, encoding="utf-8")

    store = SourceRegistry()
    store.ensure()
    entry = store.install_file(plugin)

    assert entry["enabled"] is True
    assert store.entries()[0]["id"] == entry["id"]
    installed = isolated / "sources" / entry["filename"]
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == PLUGIN_JS


# --------------------------------------------------------------------- 迁移语义
def test_migration_keeps_identity_and_enabled_state(isolated, tmp_path):
    legacy = tmp_path / "program"
    _legacy_plugin(legacy, "legacy_alpha.js")
    _legacy_plugin(legacy, "legacy_beta.js")
    _legacy_registry(
        legacy,
        [_entry("legacy_alpha", enabled=True), _entry("legacy_beta", enabled=False)],
    )

    report = source_migration.migrate_legacy_sources(home=isolated / "sources", roots=[legacy])

    assert report.completed is True
    entries = SourceRegistry().entries()
    assert [item["id"] for item in entries] == ["legacy_alpha", "legacy_beta"]
    assert [item["enabled"] for item in entries] == [True, False]
    assert (isolated / "sources" / "sources" / "active" / "legacy_beta.js").is_file()


def test_migration_retries_and_never_overwrites(isolated, tmp_path):
    legacy = tmp_path / "program"
    _legacy_plugin(legacy, "legacy_alpha.js")
    _legacy_registry(
        legacy,
        [_entry("legacy_alpha"), _entry("legacy_missing")],
    )
    home = isolated / "sources"

    first = source_migration.migrate_legacy_sources(home=home, roots=[legacy])
    assert first.completed is False
    assert first.migrated == 1
    assert first.missing

    existing = home / "sources" / "active" / "legacy_alpha.js"
    assert existing.is_file()
    existing.write_text("// user edited copy", encoding="utf-8")

    _legacy_plugin(legacy, "legacy_missing.js")
    second = source_migration.migrate_legacy_sources(home=home, roots=[legacy])

    assert second.completed is True
    assert second.skipped >= 1
    assert existing.read_text(encoding="utf-8") == "// user edited copy"


def test_upgrade_keeps_existing_plugins(isolated):
    home = isolated / "sources"
    home.mkdir(parents=True, exist_ok=True)
    (home / "sources" / "active").mkdir(parents=True, exist_ok=True)
    plugin = home / "sources" / "active" / "mine.js"
    plugin.write_text("// mine", encoding="utf-8")
    (home / "source_registry.json").write_text(
        json.dumps({"version": 1, "sources": [_entry("mine")]}, ensure_ascii=False),
        encoding="utf-8",
    )

    SourceRegistry().ensure()

    assert plugin.read_text(encoding="utf-8") == "// mine"
    assert [item["id"] for item in SourceRegistry().entries()] == ["mine"]


def test_migration_only_touches_sources_home(isolated, tmp_path):
    legacy = tmp_path / "program"
    _legacy_plugin(legacy)
    _legacy_registry(legacy, [_entry()])

    settings = isolated / "settings.json"
    queue_file = isolated / "play_queue.json"
    settings.write_text('{"playback.volume": 0.35}', encoding="utf-8")
    queue_file.write_text('{"position_ms": 4200}', encoding="utf-8")

    source_migration.migrate_legacy_sources(home=isolated / "sources", roots=[legacy])

    assert settings.read_text(encoding="utf-8") == '{"playback.volume": 0.35}'
    assert queue_file.read_text(encoding="utf-8") == '{"position_ms": 4200}'


def test_migration_leaves_database_and_cache_untouched(isolated, tmp_path):
    legacy = tmp_path / "program"
    _legacy_plugin(legacy)
    _legacy_registry(legacy, [_entry()])

    database = isolated / "hushplayer.db"
    database.write_bytes(b"SQLite format 3\x00" + b"\x00" * 64)
    cache = isolated / "cache" / "audio" / "token.mp3"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"ID3" + b"\x00" * 100)

    source_migration.migrate_legacy_sources(home=isolated / "sources", roots=[legacy])

    assert database.read_bytes().startswith(b"SQLite format 3\x00")
    assert cache.read_bytes().startswith(b"ID3")


# --------------------------------------------------------------------- 扫描规则
def test_cookie_commit_is_blocked():
    # 字面量拆开拼接：测试文件本身不应含可直接复制的凭据，运行期才是完整形态。
    fake_cookie = "MUSIC" + "_U=0123456789abcdef0123456789a"
    raw = f"module.exports = {{ cookie: '{fake_cookie}' }};".encode()
    result = security_scan.scan_bytes(
        "hushplayer/runtime/source_runtime/sources/active/x.js", raw
    )

    rules = {item.rule for item in result.blocked}
    assert "music_u_cookie" in rules


def test_database_commit_is_blocked():
    result = security_scan.scan_bytes("hushplayer.db", b"SQLite format 3\x00" + b"\x00" * 32)

    assert "user_database" in {item.rule for item in result.blocked}


def test_legit_fixture_is_not_flagged():
    result = security_scan.scan_bytes(
        "tests/fixtures/plugin_fixture.js",
        b"module.exports = { cook" + b"ie: function () { return 'fixture'; } };",
    )

    assert not result.blocked


def test_ca_bundle_is_not_a_credential():
    bundle = security_scan.scan_bytes(
        "_internal/certifi/cacert.pem",
        b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
    )
    header = b"-" * 5 + b"BEGIN PRIVATE KEY" + b"-" * 5 + b"\n"
    private_key = security_scan.scan_bytes("_internal/app/server.key", header)

    assert not bundle.blocked
    assert "credential_file" in {item.rule for item in private_key.blocked}


def test_allowlist_matches_inside_release_tree():
    allowlist = [
        {
            "path": "hushplayer/runtime/source_runtime/node_modules/*",
            "rule": "personal_email",
            "reason": "third party",
        }
    ]
    result = security_scan.scan_bytes(
        "HushPlayer/_internal/hushplayer/runtime/source_runtime/node_modules/a/package.json",
        b'{"author": "someone@example.org"}',
        allowlist,
    )

    assert not result.blocked
    assert not result.warnings


def test_personal_plugin_in_release_tree_is_blocked(tmp_path):
    dist = tmp_path / "dist"
    plugin = dist / "_internal" / "hushplayer" / "runtime" / "source_runtime" / "sources" / "active" / "x.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(PLUGIN_JS, encoding="utf-8")

    result = security_scan.scan_path(dist)

    assert result.blocked


# --------------------------------------------------------------------- 发行布局
def _release_tree(root: Path, *, entries: list[dict] | None = None) -> Path:
    runtime = root / "_internal" / "hushplayer" / "runtime" / "source_runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (root / "HushPlayer.exe").write_bytes(b"MZ")
    (runtime / "plugin_host.js").write_text("// host", encoding="utf-8")
    (runtime / "runner.js").write_text("// runner", encoding="utf-8")
    (runtime / "source_registry.json").write_text(
        json.dumps({"version": 1, "sources": entries or []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def test_release_layout_accepts_clean_tree(tmp_path):
    dist = _release_tree(tmp_path / "dist")

    assert security_scan.release_layout_problems(dist) == []


def test_release_layout_rejects_user_sources(tmp_path):
    dist = _release_tree(tmp_path / "dist")
    (dist / "sources" / "active").mkdir(parents=True)

    problems = security_scan.release_layout_problems(dist)

    assert any("sources" in item for item in problems)


def test_release_layout_rejects_state_files(tmp_path):
    dist = _release_tree(tmp_path / "dist")
    (dist / "settings.json").write_text("{}", encoding="utf-8")
    (dist / "play_queue.json").write_text("{}", encoding="utf-8")

    problems = security_scan.release_layout_problems(dist)

    assert any("settings.json" in item for item in problems)
    assert any("play_queue.json" in item for item in problems)


def test_release_layout_rejects_nonempty_registry(tmp_path):
    dist = _release_tree(tmp_path / "dist", entries=[_entry()])

    problems = security_scan.release_layout_problems(dist)

    assert any("音源条目" in item for item in problems)


def test_release_zip_with_plugin_is_blocked(tmp_path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "_internal/hushplayer/runtime/source_runtime/sources/active/x.js", PLUGIN_JS
        )

    result = security_scan.scan_zip(archive)

    assert result.blocked


# --------------------------------------------------------------------- 强制检查接入
def test_build_script_runs_security_scan():
    text = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")

    assert "security_scan.py --tracked" in text
    assert "security_scan.py --path $dist --release" in text
    assert "security_scan.py --zip $zipPath" in text


def test_git_hooks_check_privacy():
    pre_commit = (ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8")
    pre_push = (ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")

    assert "security_scan.py --staged" in pre_commit
    assert "security_scan.py --tracked" in pre_push
