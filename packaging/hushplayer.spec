# -*- mode: python ; coding: utf-8 -*-
"""HushPlayer 的 PyInstaller 打包配置（onedir，便于快速启动与增量更新）。

构建：
    python tools/make_versioninfo.py
    python -m PyInstaller packaging/hushplayer.spec --noconfirm

产物：
    packaging/out/HushPlayer/HushPlayer.exe
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - PyInstaller 注入

APP_NAME = "HushPlayer"

datas = [
    (str(ROOT / "hushplayer" / "runtime" / "source_runtime"), "hushplayer/runtime/source_runtime"),
    (str(ROOT / "hushplayer" / "runtime" / "node"), "hushplayer/runtime/node"),
    (str(ROOT / "assets"), "assets"),
]

hiddenimports = [
    "mutagen",
    "mutagen.mp3",
    "mutagen.id3",
    "mutagen.flac",
    "mutagen.mp4",
    "mutagen.oggvorbis",
    "mutagen.wave",
    "mutagen.aiff",
    "mutagen.asf",
    "PySide6.QtMultimedia",
    "PySide6.QtSvg",
]

excludes = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "pytest",
    "_pytest",
    "numpy",
    "pandas",
    "matplotlib",
    "scipy",
    "soundfile",
    "PIL",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtQmlWorkerScript",
    "PySide6.QtQuickWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
]

analysis = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "brand" / "HushPlayer.ico")
    if (ROOT / "assets" / "brand" / "HushPlayer.ico").is_file()
    else str(ROOT / "assets" / "hushplayer.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    manifest=str(ROOT / "packaging" / "app.manifest"),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
