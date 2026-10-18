"""把旧版 HushPlayer 的用户数据迁移到 HushPlayer Reimagined（可预览、可备份、可回退）。

安全约定
--------
- 默认 **只预览**，不加 ``--apply`` 不会写入任何东西；
- 写入前自动把目标目录打包成 ``backups/legacy-import-<时间>.zip``；
- 只复制白名单文件，绝不删除源目录、绝不修改旧项目；
- 遇到同名文件先备份再覆盖，并打印完整清单；
- 数据库只做整文件复制（不做不可逆的 schema 变更）——新版启动时会自行补表。

用法::

    # 预览（默认）
    .venv\\Scripts\\python.exe tools\\migrate_legacy.py --source "%APPDATA%\\HushPlayer"

    # 真正导入
    .venv\\Scripts\\python.exe tools\\migrate_legacy.py --source "..." --apply

    # 回退
    .venv\\Scripts\\python.exe tools\\migrate_legacy.py --rollback backups\\legacy-import-XXXX.zip
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WHITELIST = [
    "hushplayer.db",
    "hushplayer.db-wal",
    "hushplayer.db-shm",
    "library.json",
    "playlists.json",
    "favorites.json",
    "settings.json",
    "play_queue.json",
    "playback_session.json",
    "stats.json",
    "remote_tracks.json",
    "lyrics_bindings.json",
    "ignored_imports.json",
    "pending_imports.json",
]
SKIP_DIRS = {"cache", "logs", "backups", "artwork", "downloads"}


def candidate_files(source: Path) -> list[Path]:
    found: list[Path] = []
    for name in WHITELIST:
        path = source / name
        if path.is_file():
            found.append(path)
    for path in sorted(source.glob("*.db")):
        if path not in found:
            found.append(path)
    return found


def describe(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "无法读取"
    if path.suffix == ".db":
        return f"{size / 1024 / 1024:.2f} MB（SQLite 数据库）"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"{size} 字节（JSON 解析失败：{exc}）"
    if isinstance(data, list):
        return f"{size} 字节（{len(data)} 条记录）"
    if isinstance(data, dict):
        keys = ", ".join(list(data)[:6])
        return f"{size} 字节（字段：{keys}）"
    return f"{size} 字节"


def preview(source: Path) -> list[Path]:
    files = candidate_files(source)
    print(f"源目录：{source}")
    if not files:
        print("未发现可导入的数据文件。请确认路径是旧版 HushPlayer 的数据目录。")
        return []
    print(f"发现 {len(files)} 个可导入文件：")
    for path in files:
        print(f"  - {path.name:<26} {describe(path)}")
    return files


def make_backup(target: Path) -> Path:
    backup_dir = target / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = backup_dir / f"legacy-import-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in target.iterdir():
            if path.is_file() and path.name not in {"hushplayer.db-shm", "hushplayer.db-wal"}:
                bundle.write(path, arcname=path.name)
    return archive


def apply_import(source: Path, files: list[Path], target: Path, *, keep: bool) -> int:
    target.mkdir(parents=True, exist_ok=True)
    archive = make_backup(target)
    print(f"已备份现有数据：{archive}")
    copied = 0
    for path in files:
        destination = target / path.name
        if destination.exists():
            shutil.copy2(destination, destination.with_suffix(destination.suffix + ".before-import"))
        shutil.copy2(path, destination)
        print(f"  复制 {path.name} → {destination}")
        copied += 1
    print(f"完成：导入 {copied} 个文件。旧目录未做任何修改。")
    print("如需回退，请使用 --rollback 指向上面生成的 zip。")
    return 0


def rollback(archive: Path, target: Path) -> int:
    if not archive.is_file():
        print(f"备份不存在：{archive}")
        return 2
    print(f"将把 {archive.name} 解压回 {target}（现有文件会先另存为 *.before-rollback）")
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        print(f"包含 {len(names)} 个文件：{', '.join(names[:8])}{' …' if len(names) > 8 else ''}")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            destination = target / name
            if destination.exists():
                shutil.copy2(destination, destination.with_suffix(destination.suffix + ".before-rollback"))
            bundle.extract(name, target)
    print("回退完成。请重新启动 HushPlayer。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="旧版 HushPlayer 数据迁移工具（默认只预览）")
    parser.add_argument("--source", default="", help="旧版数据目录，例如 %%APPDATA%%\\HushPlayer")
    parser.add_argument("--target", default="", help="目标数据目录，默认使用新版数据目录")
    parser.add_argument("--apply", action="store_true", help="真正写入（默认只预览）")
    parser.add_argument("--rollback", default="", help="从备份 zip 回退")
    parser.add_argument("--no-keep", action="store_true", help="保留参数占位：旧目录永远不被修改")
    args = parser.parse_args(argv)

    from hushplayer.core import paths

    target = Path(args.target) if args.target else paths.data_dir()

    if args.rollback:
        return rollback(Path(args.rollback), target)

    if not args.source:
        parser.print_help()
        print("\n提示：先在设置 → 关于 → 打开数据目录 里确认新版位置。")
        return 2
    source = Path(os.path.expandvars(args.source)).expanduser()
    if not source.is_dir():
        print(f"源目录不存在：{source}")
        return 2

    print("=" * 62)
    print("HushPlayer 数据迁移 —— 预览模式" if not args.apply else "HushPlayer 数据迁移 —— 写入模式")
    print(f"目标目录：{target}")
    print("=" * 62)
    files = preview(source)
    if not files:
        return 2
    if not args.apply:
        print("\n这是预览，没有写入任何数据。确认无误后加 --apply 执行导入。")
        return 0

    print("\n将执行：备份目标目录 → 复制上述文件 → 保留 *.before-import")
    answer = input("继续？输入 YES 确认：").strip()
    if answer != "YES":
        print("已取消，未做任何修改。")
        return 1
    return apply_import(source, files, target, keep=not args.no_keep)


if __name__ == "__main__":
    raise SystemExit(main())
