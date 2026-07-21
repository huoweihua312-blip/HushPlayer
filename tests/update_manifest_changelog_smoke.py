from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_manifest_helper():
    helper_path = PROJECT_ROOT / "packaging" / "prepare_update_manifest.py"
    specification = importlib.util.spec_from_file_location(
        "hushplayer_prepare_update_manifest",
        helper_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def changelog_text() -> str:
    return """# HushPlayer 更新日志

## 未发布

暂无已确认、待发布的用户可见变更。

## 0.5.0-beta.8 — 2026-07-08

### 在线更新摘要

- beta.8 日志

## 0.5.0-beta.6 — 2026-07-06

### 在线更新摘要

- beta.6 日志

## 0.5.0-beta.7 — 2026-07-07

### 在线更新摘要

- beta.7 日志
"""


def manifest_document() -> dict:
    return {
        "schema_version": 1,
        "channel": "beta",
        "version": "0.5.0-beta.8",
        "numeric_version": "0.5.0.8",
        "architecture": "win-x64",
        "mandatory": False,
        "setup_url": "https://example.com/HushPlayer-0.5.0-beta.8-win-x64-setup.exe",
        "setup_size": 4096,
        "sha256": "0" * 64,
        "release_notes": ["过期说明"],
    }


def main() -> None:
    helper = load_manifest_helper()
    with tempfile.TemporaryDirectory(prefix="hushplayer_manifest_changelog_") as temp_dir:
        root = Path(temp_dir)
        changelog_path = root / "CHANGELOG.md"
        manifest_path = root / "win-x64.json"
        changelog_path.write_text(changelog_text(), encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest_document(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        releases = helper.parse_changelog_releases(changelog_path)
        assert [release.version for release in releases] == [
            "0.5.0-beta.6",
            "0.5.0-beta.7",
            "0.5.0-beta.8",
        ]
        synchronized = helper.synchronize_manifest_document(
            manifest_document(),
            releases,
        )
        assert synchronized["release_notes"] == ["beta.8 日志"]
        assert [entry["version"] for entry in synchronized["release_history"]] == [
            "0.5.0-beta.6",
            "0.5.0-beta.7",
            "0.5.0-beta.8",
        ]
        helper.validate_manifest_document(synchronized, releases)

        stale = dict(synchronized)
        stale["release_history"] = stale["release_history"][1:]
        try:
            helper.validate_manifest_document(stale, releases)
        except helper.ChangelogValidationError as error:
            assert "release_history" in str(error)
        else:
            raise AssertionError("stale release_history unexpectedly validated")

    current_changelog = PROJECT_ROOT / "CHANGELOG.md"
    current_manifest = PROJECT_ROOT / "updates" / "beta" / "win-x64.json"
    current_releases = helper.parse_changelog_releases(current_changelog)
    current_document = json.loads(current_manifest.read_text(encoding="utf-8"))
    helper.validate_manifest_document(current_document, current_releases)
    helper.validate_manifest_matches_application(current_document)

    print("update manifest changelog smoke: OK")


if __name__ == "__main__":
    main()
