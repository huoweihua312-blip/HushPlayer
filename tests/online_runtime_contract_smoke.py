from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication

from app.core.app_paths import AppPaths
from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import SourceRegistryManager


def test_worktree_independent_paths() -> None:
    application = QCoreApplication.instance() or QCoreApplication([])
    del application
    original_cwd = Path.cwd()
    try:
        paths_before = AppPaths.resolve()
        os.chdir(Path(os.environ.get("SystemDrive") or "C:") / "\\")
        paths_after = AppPaths.resolve()
    finally:
        os.chdir(original_cwd)

    assert paths_before.bundled_resource_dir == paths_after.bundled_resource_dir
    assert paths_before.source_runtime_data_dir == paths_after.source_runtime_data_dir
    assert paths_before.source_registry_file == paths_after.source_registry_file
    assert paths_before.user_sources_dir == paths_after.user_sources_dir
    assert paths_before.cache_dir == paths_after.cache_dir


def test_runtime_dependency_provider_is_outside_active_worktree() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_runtime_contract_") as temp_dir:
        root = Path(temp_dir)
        active_bundle = root / "active-worktree"
        active_runtime = active_bundle / "source_runtime"
        active_runtime.mkdir(parents=True)
        (active_runtime / "runner.js").write_text("", encoding="utf-8")
        (active_runtime / "package.json").write_text(
            '{"dependencies":{"axios":"^1.0.0"}}',
            encoding="utf-8",
        )
        provider_runtime = root / "stable-provider" / "source_runtime"
        (provider_runtime / "node_modules" / "axios").mkdir(parents=True)
        (provider_runtime / "runner.js").write_text("", encoding="utf-8")
        (provider_runtime / "package.json").write_text(
            '{"dependencies":{"axios":"^1.0.0"}}',
            encoding="utf-8",
        )
        paths = AppPaths(
            bundled_resource_dir=active_bundle,
            application_data_dir=root / "appdata",
            cache_dir=root / "cache",
            log_dir=root / "logs",
            frozen=False,
            legacy_project_dir=active_bundle,
        )
        assert paths.source_runtime_dependencies_dir == (
            provider_runtime / "node_modules"
        ).resolve()


def test_formal_runtime_paths_and_source_resolution() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_runtime_paths_") as temp_dir:
        root = Path(temp_dir)
        writable_runtime = root / "appdata" / "source_runtime"
        source_file = writable_runtime / "sources" / "active" / "fixture.js"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("module.exports = { search: async () => [] };\n", encoding="utf-8")
        registry_path = writable_runtime / "source_registry.json"
        registry_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "id": "fixture_source",
                            "filename": "sources/active/fixture.js",
                            "enabled": True,
                            "userInstalled": True,
                            "capabilities": {"search": True},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        user_sources_dir = root / "appdata" / "user_sources"
        user_sources_dir.mkdir()
        runtime_dir = root / "bundle" / "source_runtime"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "runner.js").write_text("", encoding="utf-8")
        dependency_dir = root / "stable" / "node_modules"
        dependency_dir.mkdir(parents=True)

        manager = SourceRegistryManager(
            root / "bundle",
            runtime_dir=writable_runtime,
            user_sources_dir=user_sources_dir,
            bundled_runtime_dir=runtime_dir,
        )
        assert manager._resolve_registered_source_file(
            "sources/active/fixture.js"
        ) == source_file.resolve()
        client = OnlineSourceClient(
            root / "bundle",
            runtime_dir=runtime_dir,
            registry_path=registry_path,
            user_sources_dir=user_sources_dir,
            runtime_dependencies_dir=dependency_dir,
            bundled_node_executable=root / "node.exe",
            frozen=True,
        )
        environment = client.process.processEnvironment()
        assert Path(environment.value("HUSHPLAYER_SOURCE_REGISTRY")) == registry_path.resolve()
        assert Path(environment.value("HUSHPLAYER_SOURCE_HOME")) == writable_runtime.resolve()
        assert Path(environment.value("HUSHPLAYER_USER_SOURCES")) == user_sources_dir.resolve()
        assert str(dependency_dir.resolve()) in environment.value("NODE_PATH").split(os.pathsep)
        assert client.runner_path == (runtime_dir / "runner.js").resolve()


def main() -> int:
    test_worktree_independent_paths()
    test_runtime_dependency_provider_is_outside_active_worktree()
    test_formal_runtime_paths_and_source_resolution()
    print("online runtime contract smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
