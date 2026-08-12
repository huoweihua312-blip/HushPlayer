# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path


PROJECT_ROOT = Path(SPECPATH).resolve().parent
ICON_FILE = PROJECT_ROOT / "assets" / "icons" / "HushPlayer.ico"
VERSION_INFO_FILE = Path(os.environ["HUSHPLAYER_VERSION_INFO"]).resolve()


a = Analysis(
    [str(PROJECT_ROOT / "packaging" / "hushplayer_updater.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HushPlayerUpdater",
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
    version=str(VERSION_INFO_FILE),
    icon=str(ICON_FILE),
)
