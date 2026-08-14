from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import subprocess
import tempfile
import zipfile
from unittest.mock import patch
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.app_update_service import (
    UpdateValidationError,
    parse_update_manifest,
    verify_update_package,
)

def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(package: Path) -> object:
    setup = b"MZ" + b"s" * 2046
    package_name = "HushPlayer-0.5.0-beta.8-win-x64-update.zip"
    document = {
        "schema_version": 1,
        "channel": "beta",
        "version": "0.5.0-beta.8",
        "numeric_version": "0.5.0.8",
        "architecture": "win-x64",
        "mandatory": False,
        "setup_url": "https://example.invalid/HushPlayer-0.5.0-beta.8-win-x64-setup.exe",
        "setup_size": len(setup),
        "sha256": hashlib.sha256(setup).hexdigest(),
        "package_url": f"https://example.invalid/{package_name}",
        "package_size": package.stat().st_size,
        "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "package_filename": package_name,
        "release_notes": ["应用内更新测试"],
    }
    return parse_update_manifest(json.dumps(document).encode("utf-8"))


def _create_package(path: Path, *, include_helper: bool = True, unsafe: bool = False) -> None:
    payload = bytes(index % 251 for index in range(8192))
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("HushPlayer.exe", payload)
        if include_helper:
            archive.writestr("HushPlayerUpdater.exe", payload)
        archive.writestr("_internal/app.bin", payload)
        if unsafe:
            archive.writestr("../outside.txt", b"must be rejected")


def package_manifest_checks(root: Path) -> None:
    package = root / "HushPlayer-0.5.0-beta.8-win-x64-update.zip"
    _create_package(package)
    manifest = _manifest(package)
    assert manifest.has_in_app_package
    assert manifest.download_url == manifest.package_url
    assert manifest.download_size == package.stat().st_size
    verify_update_package(package, manifest)

    legacy_document = {
        "schema_version": 1,
        "channel": "beta",
        "version": "0.5.0-beta.8",
        "numeric_version": "0.5.0.8",
        "architecture": "win-x64",
        "mandatory": False,
        "setup_url": "https://example.invalid/HushPlayer-0.5.0-beta.8-win-x64-setup.exe",
        "setup_size": 2048,
        "sha256": hashlib.sha256(b"MZ" + b"s" * 2046).hexdigest(),
        "release_notes": [],
    }
    legacy = parse_update_manifest(json.dumps(legacy_document).encode("utf-8"))
    assert not legacy.has_in_app_package
    assert legacy.download_url == legacy.setup_url

    unsafe = root / "HushPlayer-0.5.0-beta.8-win-x64-update-unsafe.zip"
    _create_package(unsafe, unsafe=True)
    unsafe_manifest = _manifest(unsafe)
    try:
        verify_update_package(unsafe, unsafe_manifest)
    except UpdateValidationError as error:
        assert "不安全" in str(error)
    else:
        raise AssertionError("unsafe update package was accepted")

    missing = root / "HushPlayer-0.5.0-beta.8-win-x64-update-missing.zip"
    _create_package(missing, include_helper=False)
    missing_manifest = _manifest(missing)
    try:
        verify_update_package(missing, missing_manifest)
    except UpdateValidationError as error:
        assert "HushPlayerUpdater.exe" in str(error)
    else:
        raise AssertionError("package without updater was accepted")


def updater_swap_checks(root: Path) -> None:
    updater = _load_module(
        "hushplayer_packaged_updater_smoke",
        PROJECT_ROOT / "packaging" / "hushplayer_updater.py",
    )
    install_dir = root / "HushPlayer"
    install_dir.mkdir()
    (install_dir / "HushPlayer.exe").write_bytes(b"old executable")
    (install_dir / "HushPlayerUpdater.exe").write_bytes(b"old updater")
    package = root / "swap.zip"
    _create_package(package)
    updater._wait_for_parent = lambda _pid: None
    updater._start_application = lambda _executable, _working_dir: None
    updater.apply_update(
        parent_pid=12345,
        install_dir=install_dir,
        package=package,
        restart_exe=install_dir / "HushPlayer.exe",
    )
    payload = bytes(index % 251 for index in range(8192))
    assert (install_dir / "HushPlayer.exe").read_bytes() == payload
    assert (install_dir / "HushPlayerUpdater.exe").read_bytes() == payload
    assert not list(root.glob(".HushPlayer-backup-*"))


def updater_replace_retry_checks(root: Path) -> None:
    updater = _load_module(
        "hushplayer_packaged_updater_retry_smoke",
        PROJECT_ROOT / "packaging" / "hushplayer_updater.py",
    )
    install_dir = root / "HushPlayer-retry"
    install_dir.mkdir()
    (install_dir / "HushPlayer.exe").write_bytes(b"old executable")
    (install_dir / "HushPlayerUpdater.exe").write_bytes(b"old updater")
    package = root / "retry-swap.zip"
    _create_package(package)

    real_replace = updater.os.replace
    calls = 0

    def fail_once(source, destination):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("directory is temporarily locked")
        return real_replace(source, destination)

    updater._wait_for_parent = lambda _pid: None
    updater._start_application = lambda _executable, _working_dir: None
    with patch.object(updater.os, "replace", fail_once):
        updater.apply_update(
            parent_pid=12345,
            install_dir=install_dir,
            package=package,
            restart_exe=install_dir / "HushPlayer.exe",
        )
    assert calls >= 3
    assert (install_dir / "HushPlayer.exe").read_bytes() == bytes(
        index % 251 for index in range(8192)
    )

    locked_dir = root / "HushPlayer-permanent-lock"
    locked_dir.mkdir()
    (locked_dir / "HushPlayer.exe").write_bytes(b"must remain")
    (locked_dir / "HushPlayerUpdater.exe").write_bytes(b"old updater")
    updater._REPLACE_RETRY_TIMEOUT_MS = 10

    def always_locked(_source, _destination):
        raise PermissionError("directory remains locked")

    with patch.object(updater.os, "replace", always_locked), patch.object(
        updater.time, "sleep", return_value=None
    ):
        try:
            updater.apply_update(
                parent_pid=12345,
                install_dir=locked_dir,
                package=package,
                restart_exe=locked_dir / "HushPlayer.exe",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("permanently locked install unexpectedly replaced")
    assert (locked_dir / "HushPlayer.exe").read_bytes() == b"must remain"
    assert not list(root.glob(".HushPlayer-backup-*"))

    if updater.os.name == "nt":
        live_install = root / "HushPlayer-live-lock"
        live_backup = root / "HushPlayer-live-backup"
        live_install.mkdir()
        (live_install / "HushPlayer.exe").write_bytes(b"live install")
        holder = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.4)"],
            cwd=str(live_install),
        )
        try:
            updater._REPLACE_RETRY_TIMEOUT_MS = 5_000
            updater._replace_with_retry(live_install, live_backup)
        finally:
            holder.wait(timeout=5)
        assert live_backup.is_dir()
        assert not live_install.exists()


def payload_builder_checks(root: Path) -> None:
    builder = _load_module(
        "hushplayer_payload_builder_smoke",
        PROJECT_ROOT / "packaging" / "build_update_payload.py",
    )
    source = root / "dist" / "HushPlayer"
    source.mkdir(parents=True)
    (source / "HushPlayer.exe").write_bytes(b"exe")
    (source / "HushPlayerUpdater.exe").write_bytes(b"updater")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
    output = root / "payload.zip"
    metadata = builder.build_payload(source, output)
    assert metadata["files"] == 2
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"HushPlayer.exe", "HushPlayerUpdater.exe"}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_in_app_update_") as temporary:
        root = Path(temporary)
        package_manifest_checks(root)
        updater_swap_checks(root)
        updater_replace_retry_checks(root)
        payload_builder_checks(root)
    print("in-app update smoke: OK")


if __name__ == "__main__":
    main()
