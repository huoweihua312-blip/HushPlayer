from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.version import (
    APP_NUMERIC_VERSION,
    APP_NUMERIC_VERSION_TEXT,
    APP_VERSION,
    UPDATE_CHANNEL,
    numeric_version_text,
)


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


def manifest_version(sequence: int) -> tuple[str, str]:
    major, minor, patch, _ = APP_NUMERIC_VERSION
    numeric_version = (major, minor, patch, sequence)
    return (
        f"{major}.{minor}.{patch}-{UPDATE_CHANNEL}.{sequence}",
        numeric_version_text(numeric_version),
    )


def assert_validation_rejected(callback, expected: str) -> None:
    try:
        callback()
    except ValueError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError("invalid manifest unexpectedly validated")


def run_helper_cli(helper, arguments: list[str]) -> None:
    previous_argv = sys.argv
    try:
        sys.argv = ["prepare_update_manifest.py", *arguments]
        helper.main()
    finally:
        sys.argv = previous_argv


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
    helper.validate_prebuild_manifest(current_document, current_releases)

    _, _, _, current_sequence = APP_NUMERIC_VERSION
    current_version, current_numeric_version = manifest_version(current_sequence)
    current_release_document = dict(current_document)
    current_release_document["version"] = current_version
    current_release_document["numeric_version"] = current_numeric_version
    current_release_document = helper.synchronize_manifest_document(
        current_release_document,
        current_releases,
    )
    helper.validate_prebuild_manifest(current_release_document, current_releases)
    helper.validate_manifest_matches_application(current_release_document)

    previous_version, previous_numeric_version = manifest_version(
        current_sequence - 1
    )
    previous_document = dict(current_document)
    previous_document["version"] = previous_version
    previous_document["numeric_version"] = previous_numeric_version
    previous_document = helper.synchronize_manifest_document(
        previous_document,
        current_releases,
    )
    helper.validate_prebuild_manifest(previous_document, current_releases)
    assert_validation_rejected(
        lambda: helper.validate_manifest_matches_application(previous_document),
        "version 与 app/core/version.py 不一致",
    )

    stale_version, stale_numeric_version = manifest_version(current_sequence - 2)
    stale_document = dict(current_document)
    stale_document["version"] = stale_version
    stale_document["numeric_version"] = stale_numeric_version
    stale_document = helper.synchronize_manifest_document(
        stale_document,
        current_releases,
    )
    assert_validation_rejected(
        lambda: helper.validate_prebuild_manifest(stale_document, current_releases),
        "最多只能落后",
    )

    future_version, future_numeric_version = manifest_version(current_sequence + 1)
    with tempfile.TemporaryDirectory(prefix="hushplayer_future_manifest_") as temp_dir:
        future_changelog = Path(temp_dir) / "CHANGELOG.md"
        future_changelog.write_text(
            current_changelog.read_text(encoding="utf-8")
            + "\n"
            + f"## {future_version} - 2026-07-22\n\n"
            + "### 在线更新摘要\n\n"
            + "- 未来版本日志\n",
            encoding="utf-8",
        )
        future_releases = helper.parse_changelog_releases(future_changelog)
        future_document = dict(current_document)
        future_document["version"] = future_version
        future_document["numeric_version"] = future_numeric_version
        future_document = helper.synchronize_manifest_document(
            future_document,
            future_releases,
        )
        assert_validation_rejected(
            lambda: helper.validate_prebuild_manifest(
                future_document,
                future_releases,
            ),
            "不得高于",
        )

    wrong_channel = dict(current_document)
    wrong_channel["channel"] = "stable"
    assert_validation_rejected(
        lambda: helper.validate_prebuild_manifest(wrong_channel, current_releases),
        "channel",
    )

    wrong_architecture = dict(current_document)
    wrong_architecture["architecture"] = "win-arm64"
    assert_validation_rejected(
        lambda: helper.validate_prebuild_manifest(
            wrong_architecture,
            current_releases,
        ),
        "architecture",
    )

    wrong_platform_version = dict(current_document)
    wrong_platform_version["version"] = (
        f"{APP_NUMERIC_VERSION[0] + 1}.{APP_NUMERIC_VERSION[1]}."
        f"{APP_NUMERIC_VERSION[2]}-{UPDATE_CHANNEL}.{current_sequence - 1}"
    )
    wrong_platform_version["numeric_version"] = (
        f"{APP_NUMERIC_VERSION[0] + 1}.{APP_NUMERIC_VERSION[1]}."
        f"{APP_NUMERIC_VERSION[2]}.{current_sequence - 1}"
    )
    assert_validation_rejected(
        lambda: helper.validate_published_manifest_for_source(
            wrong_platform_version
        ),
        "major/minor/patch",
    )

    with tempfile.TemporaryDirectory(prefix="hushplayer_staged_manifest_") as temp_dir:
        root = Path(temp_dir)
        installer = root / helper.expected_installer_filename()
        installer.write_bytes(
            b"MZ"
            + f"staged {APP_VERSION} installer fixture".encode("utf-8") * 64
        )
        source_manifest = root / "published-manifest.json"
        source_manifest.write_text(
            json.dumps(current_document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        staged_manifest = root / "build" / "release-manifest" / "win-x64.json"
        run_helper_cli(
            helper,
            [
                "--manifest",
                str(source_manifest),
                "--stage-installer",
                str(installer),
                "--output",
                str(staged_manifest),
            ],
        )
        assert staged_manifest.is_file()
        assert staged_manifest.parent == root / "build" / "release-manifest"
        staged_document = json.loads(staged_manifest.read_text(encoding="utf-8"))
        assert staged_document["version"] == APP_VERSION
        assert staged_document["numeric_version"] == APP_NUMERIC_VERSION_TEXT
        assert staged_document["setup_size"] == installer.stat().st_size
        assert staged_document["sha256"] == hashlib.sha256(
            installer.read_bytes()
        ).hexdigest()
        assert staged_document["setup_url"].startswith("https://")
        helper.validate_final_manifest(
            staged_document,
            current_releases,
            installer,
        )
        run_helper_cli(
            helper,
            [
                "--manifest",
                str(staged_manifest),
                "--final-installer",
                str(installer),
            ],
        )
        assert_validation_rejected(
            lambda: helper.validate_final_manifest(
                previous_document,
                current_releases,
                installer,
            ),
            "version 与 app/core/version.py 不一致",
        )
        wrong_size = dict(staged_document, setup_size=installer.stat().st_size + 1)
        assert_validation_rejected(
            lambda: helper.validate_final_manifest(
                wrong_size,
                current_releases,
                installer,
            ),
            "setup_size",
        )
        wrong_sha256 = dict(staged_document, sha256="0" * 64)
        assert_validation_rejected(
            lambda: helper.validate_final_manifest(
                wrong_sha256,
                current_releases,
                installer,
            ),
            "sha256",
        )
        insecure_url = dict(
            staged_document,
            setup_url=(
                "http://example.com/" + helper.expected_installer_filename()
            ),
        )
        assert_validation_rejected(
            lambda: helper.validate_final_manifest(
                insecure_url,
                current_releases,
                installer,
            ),
            "HTTPS",
        )

    print("update manifest changelog smoke: OK")


if __name__ == "__main__":
    main()
