# -*- mode: python ; coding: utf-8 -*-

import json
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parent
ICON_FILE = PROJECT_ROOT / "assets" / "icons" / "HushPlayer.ico"
NODE_EXE = Path(os.environ["HUSHPLAYER_NODE_EXE"]).resolve()
if not ICON_FILE.is_file():
    raise SystemExit(f"Application icon not found: {ICON_FILE}")
if not NODE_EXE.is_file():
    raise SystemExit(f"Bundled Node executable not found: {NODE_EXE}")


def directory_if_present(relative_path, destination):
    source = PROJECT_ROOT / relative_path
    if not source.is_dir():
        return []
    return [(str(source), destination)]


datas = []
datas += directory_if_present("assets", "assets")
datas += directory_if_present("app/resources", "app/resources")

for runtime_name in (
    "runner.js",
    "plugin_host.js",
    "source_test_worker.js",
    "package.json",
    "package-lock.json",
    "README.md",
):
    runtime_file = PROJECT_ROOT / "source_runtime" / runtime_name
    if runtime_file.is_file():
        datas.append((str(runtime_file), "source_runtime"))

package_lock_path = PROJECT_ROOT / "source_runtime" / "package-lock.json"
package_lock = json.loads(package_lock_path.read_text(encoding="utf-8"))
package_entries = package_lock.get("packages") or {}
selected_package_paths = []
for relative_path, metadata in sorted(package_entries.items()):
    normalized = relative_path.replace("\\", "/")
    if not normalized.startswith("node_modules/") or metadata.get("dev") is True:
        continue
    source_path = PROJECT_ROOT / "source_runtime" / Path(normalized)
    if not source_path.is_dir():
        continue
    if any(
        normalized.startswith(parent + "/node_modules/")
        for parent in selected_package_paths
    ):
        continue
    selected_package_paths.append(normalized)
    datas.append(
        (str(source_path), f"source_runtime/{normalized}")
    )

hiddenimports = collect_submodules("mutagen")

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[(str(NODE_EXE), "runtime/node")],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tests"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HushPlayer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
    version=str(PROJECT_ROOT / "packaging" / "version_info.txt"),
    icon=str(ICON_FILE),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HushPlayer",
)
