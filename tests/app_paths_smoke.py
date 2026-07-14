from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.app_paths import AppPaths


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hushplayer_paths_") as temp_dir:
        root = Path(temp_dir)
        bundle = root / "bundle"
        app_data = root / "用户 数据"
        cache = root / "缓存 目录"
        logs = root / "日志"
        legacy_data = bundle / "data"
        legacy_data.mkdir(parents=True)
        (legacy_data / "library.json").write_text(
            json.dumps([{"title": "迁移测试"}], ensure_ascii=False),
            encoding="utf-8",
        )
        (legacy_data / "metadata_cache.json").write_text(
            json.dumps({"fixture": True}),
            encoding="utf-8",
        )
        legacy_runtime = bundle / "source_runtime"
        legacy_active = legacy_runtime / "sources" / "active"
        legacy_active.mkdir(parents=True)
        (legacy_runtime / "source_registry.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "id": "fixture_source",
                            "filename": "sources/active/fixture.js",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (legacy_active / "fixture.js").write_text(
            "module.exports = {};\n",
            encoding="utf-8",
        )
        legacy_user_sources = bundle / "user_sources"
        legacy_user_sources.mkdir()
        (legacy_user_sources / "user.js").write_text(
            "module.exports = {};\n",
            encoding="utf-8",
        )
        previous = {
            name: os.environ.get(name)
            for name in (
                "HUSHPLAYER_BUNDLED_RESOURCE_DIR",
                "HUSHPLAYER_APP_DATA_DIR",
                "HUSHPLAYER_CACHE_DIR",
                "HUSHPLAYER_LOG_DIR",
            )
        }
        missing = object()
        previous_frozen = getattr(sys, "frozen", missing)
        previous_meipass = getattr(sys, "_MEIPASS", missing)
        try:
            os.environ["HUSHPLAYER_BUNDLED_RESOURCE_DIR"] = str(bundle)
            os.environ["HUSHPLAYER_APP_DATA_DIR"] = str(app_data)
            os.environ["HUSHPLAYER_CACHE_DIR"] = str(cache)
            os.environ["HUSHPLAYER_LOG_DIR"] = str(logs)
            paths = AppPaths.resolve()
            object.__setattr__(paths, "legacy_project_dir", bundle)
            paths.initialize_user_storage()
            assert paths.bundled_resource_dir == bundle.resolve()
            assert paths.application_data_dir == app_data.resolve()
            assert paths.cache_dir == cache.resolve()
            assert paths.log_dir == logs.resolve()
            assert json.loads((paths.data_dir / "library.json").read_text(encoding="utf-8"))[0]["title"] == "迁移测试"
            assert json.loads(paths.metadata_cache_file.read_text(encoding="utf-8"))["fixture"] is True
            assert json.loads(paths.source_registry_file.read_text(encoding="utf-8"))["sources"][0]["id"] == "fixture_source"
            assert (paths.source_runtime_data_dir / "sources" / "active" / "fixture.js").is_file()
            assert (paths.user_sources_dir / "user.js").is_file()
            (paths.data_dir / "library.json").write_text("[]", encoding="utf-8")
            paths.source_registry_file.write_text(
                '{"version": 1, "sources": [{"id": "preserved"}]}',
                encoding="utf-8",
            )
            paths.initialize_user_storage()
            assert (paths.data_dir / "library.json").read_text(encoding="utf-8") == "[]"
            assert json.loads(paths.source_registry_file.read_text(encoding="utf-8"))["sources"][0]["id"] == "preserved"
            assert paths.data_dir.is_dir()
            assert (paths.cache_dir / "covers").is_dir()
            assert (paths.cache_dir / "lyrics").is_dir()
            assert paths.log_dir.is_dir()

            frozen_bundle = root / "portable 中文" / "HushPlayer" / "_internal"
            frozen_bundle.mkdir(parents=True)
            sys.frozen = True
            sys._MEIPASS = str(frozen_bundle)
            frozen_paths = AppPaths.resolve()
            assert frozen_paths.frozen is True
            assert frozen_paths.bundled_resource_dir == frozen_bundle.resolve()
            assert frozen_paths.bundled_node_executable == (
                frozen_bundle / "runtime" / "node" / "node.exe"
            ).resolve()
            assert frozen_paths.bundled_source_runtime_dir == (
                frozen_bundle / "source_runtime"
            ).resolve()

            del sys._MEIPASS
            try:
                AppPaths.resolve()
            except RuntimeError as error:
                assert "sys._MEIPASS" in str(error)
            else:
                raise AssertionError(
                    "Frozen path resolution accepted a missing sys._MEIPASS"
                )
        finally:
            if previous_frozen is missing:
                if hasattr(sys, "frozen"):
                    del sys.frozen
            else:
                sys.frozen = previous_frozen
            if previous_meipass is missing:
                if hasattr(sys, "_MEIPASS"):
                    del sys._MEIPASS
            else:
                sys._MEIPASS = previous_meipass
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    print("application paths smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
