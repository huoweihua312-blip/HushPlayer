from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import SourceRegistryManager


def main() -> int:
    application = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix="hushplayer_runtime_") as temp_dir:
        root = Path(temp_dir)
        writable_runtime = root / "用户 数据" / "source_runtime"
        active_dir = writable_runtime / "sources" / "active"
        user_sources_dir = root / "用户 数据" / "user_sources"
        active_dir.mkdir(parents=True)
        user_sources_dir.mkdir(parents=True)
        source_file = active_dir / "fixture.js"
        source_file.write_text(
            "module.exports = { platform: 'Fixture', search: async () => [] };\n",
            encoding="utf-8",
        )
        registry_path = writable_runtime / "source_registry.json"
        registry_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "id": "fixture_source",
                            "name": "Fixture",
                            "filename": "sources/active/fixture.js",
                            "enabled": True,
                            "userInstalled": True,
                            "contentPolicy": "user_owned",
                            "capabilities": {"search": True},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        manager = SourceRegistryManager(
            PROJECT_ROOT,
            runtime_dir=writable_runtime,
            user_sources_dir=user_sources_dir,
            bundled_runtime_dir=PROJECT_ROOT / "source_runtime",
        )
        assert manager.registry_path == registry_path.resolve()
        assert manager._resolve_registered_source_file(
            "sources/active/fixture.js"
        ) == source_file.resolve()
        assert manager.get_source("fixture_source") is not None

        client = OnlineSourceClient(
            PROJECT_ROOT,
            runtime_dir=PROJECT_ROOT / "source_runtime",
            registry_path=registry_path,
            user_sources_dir=user_sources_dir,
            frozen=False,
        )
        environment = client.process.processEnvironment()
        assert Path(environment.value("HUSHPLAYER_SOURCE_REGISTRY")) == registry_path.resolve()
        assert Path(environment.value("HUSHPLAYER_SOURCE_HOME")) == writable_runtime.resolve()
        assert Path(environment.value("HUSHPLAYER_USER_SOURCES")) == user_sources_dir.resolve()

        result: list[dict] = []
        errors: list[str] = []
        diagnostics: list[str] = []
        loop = QEventLoop()
        client.sourceListReceived.connect(lambda sources: (result.extend(sources), loop.quit()))
        client.processError.connect(lambda message: (errors.append(message), loop.quit()))
        client.nodeLog.connect(diagnostics.append)
        client.requestFailed.connect(
            lambda _request_id, _action, message: (errors.append(message), loop.quit())
        )
        client.list_sources(timeout_ms=8000)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        client.stop()
        assert not errors, errors
        assert any(source.get("id") == "fixture_source" for source in result), result
        assert Path(client.process.program()).is_absolute()
        assert client.process.arguments() == [str(client.runner_path)]
        assert client.process.workingDirectory() == str(client.runner_path.parent)
        assert any("node_path.exists=True" in item for item in diagnostics)
        assert any("runner_path.exists=True" in item for item in diagnostics)

        missing_node = OnlineSourceClient(
            PROJECT_ROOT,
            bundled_node_executable=root / "missing" / "node.exe",
            frozen=True,
        )
        assert not missing_node.node_program
        missing_diagnostics: list[str] = []
        missing_node.nodeLog.connect(missing_diagnostics.append)
        assert not missing_node.start()
        assert any("node_path.exists=False" in item for item in missing_diagnostics)

    application.processEvents()
    print("bundled runtime paths smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
