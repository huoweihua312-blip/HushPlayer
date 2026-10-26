"""把用户自己安装的音源插件收进用户数据目录。

HushPlayer 1.3.22 之前，音源插件和注册表会随程序目录（开发时是仓库里的
``hushplayer/runtime/source_runtime/sources``，安装后是 ``_internal`` 下同样的
路径）一起分发，导致「个人插件」和「运行框架」混在一起。1.3.23 起：

* 程序目录只保留运行框架（``plugin_host.js`` / ``runner.js`` / ``node_modules``）；
* 插件、备份、暂存目录和注册表都放在 ``data_dir()/sources``；
* 首次启动时如果发现旧位置还有插件，会在**不删除旧文件**的前提下复制过来。

这个模块只做「复制 + 校验 + 记录」三件事，可以重复执行：

* 目标文件已存在时绝不再覆盖；
* 迁移前先把旧注册表和插件复制到 ``sources/migration_backup/``；
* 迁移中断（例如进程被杀）后再次执行，会补齐缺失文件；
* 迁移完成后写 ``migration.json``，并记录旧注册表的指纹，
  旧内容没有变化时下次启动直接跳过，避免把用户主动删掉的插件又「复活」。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.logging_setup import get_logger, log_exception
from ..core.paths import data_dir, resource_path

__all__ = [
    "MigrationReport",
    "backup_legacy_sources",
    "home_dir",
    "legacy_roots",
    "migrate_legacy_sources",
    "verify_sources",
]

log = get_logger(__name__)

MIGRATION_VERSION = 1
REGISTRY_NAME = "source_registry.json"
MARKER_NAME = "migration.json"
BACKUP_DIR = "migration_backup"


@dataclass
class MigrationReport:
    """Result of one migration / repair pass."""

    migrated: int = 0
    skipped: int = 0
    missing: list[str] = field(default_factory=list)
    backup: str = ""
    completed: bool = False
    verified: int = 0
    reason: str = ""

    @property
    def total(self) -> int:
        return self.migrated + self.skipped + len(self.missing)

    def summary(self) -> str:
        if not self.completed:
            return f"音源迁移未完成：{self.reason or '未知原因'}"
        if not self.migrated and not self.missing:
            return f"音源已就绪（{self.verified} 个）"
        parts = [f"迁移 {self.migrated} 个音源"]
        if self.missing:
            parts.append(f"{len(self.missing)} 个文件缺失")
        parts.append(f"当前可用 {self.verified} 个")
        return "，".join(parts)


# --------------------------------------------------------------------------- 路径
def home_dir() -> Path:
    """用户数据目录下的音源根目录（与 registry.SourceRegistry.home 一致）。"""

    return data_dir() / "sources"


def legacy_roots() -> list[Path]:
    """旧版本可能存放私人插件的位置，按优先级排序。"""

    roots: list[Path] = []
    for candidate in (
        resource_path("hushplayer", "runtime", "source_runtime"),
        resource_path("source_runtime"),
    ):
        path = Path(candidate)
        if path not in roots:
            roots.append(path)
    return roots


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        document = json.loads(raw)
    except ValueError:
        return {}
    return document if isinstance(document, dict) else {}


def _entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    items = document.get("sources")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _fingerprint(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _relative_target(home: Path, relative: str) -> Path | None:
    """把注册表里的相对路径翻译成 home 内的路径，越界一律拒绝。"""

    text = str(relative or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or ":" in text:
        return None
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return home.joinpath(*parts)


def _copy_file(source: Path, destination: Path) -> bool:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return True
    except OSError as exc:
        log_exception(f"复制音源文件失败：{source.name}", exc)
        return False


# --------------------------------------------------------------------------- 备份
def backup_legacy_sources(root: Path, *, home: Path | None = None) -> Path | None:
    """迁移前把旧注册表和它引用的插件复制到用户数据目录，保留现场。"""

    registry = root / REGISTRY_NAME
    if not registry.is_file():
        return None
    target_home = home or home_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = target_home / BACKUP_DIR / f"legacy-{stamp}"
    try:
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(registry, destination / REGISTRY_NAME)
        copied = 0
        for entry in _entries(_read_json(registry)):
            source = root / str(entry.get("filename") or "")
            if not source.is_file():
                continue
            try:
                relative = Path(str(entry.get("filename"))).as_posix()
            except (TypeError, ValueError):
                continue
            _copy_file(source, destination / relative)
            copied += 1
    except OSError as exc:
        log_exception("备份旧音源失败（迁移仍会继续，旧文件不会被删除）", exc)
        return None
    log.info("已备份旧音源到 %s（%d 个插件）", destination, copied)
    return destination


# --------------------------------------------------------------------------- 迁移
def _load_marker(home: Path) -> dict[str, Any]:
    document = _read_json(home / MARKER_NAME)
    return document if document.get("version") == MIGRATION_VERSION else {}


def _write_marker(home: Path, payload: dict[str, Any], report: MigrationReport) -> None:
    try:
        home.mkdir(parents=True, exist_ok=True)
        tmp = home / (MARKER_NAME + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(home / MARKER_NAME)
    except OSError as exc:
        log_exception("写入音源迁移记录失败", exc)
        report.reason = "写入迁移记录失败"


def _write_registry(home: Path, document: dict[str, Any]) -> bool:
    try:
        home.mkdir(parents=True, exist_ok=True)
        tmp = home / (REGISTRY_NAME + ".tmp")
        tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(home / REGISTRY_NAME)
        return True
    except OSError as exc:
        log_exception("写入音源注册表失败（旧注册表保持原样）", exc)
        return False


def verify_sources(home: Path | None = None) -> tuple[int, list[str]]:
    """统计注册表里真正可用的插件数量，返回 (可用数, 缺失文件名)。"""

    target_home = home or home_dir()
    registry = target_home / REGISTRY_NAME
    if not registry.is_file():
        return 0, []
    available = 0
    missing: list[str] = []
    for entry in _entries(_read_json(registry)):
        relative = str(entry.get("filename") or "")
        path = _relative_target(target_home, relative)
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            missing.append(relative or str(entry.get("id") or ""))
            continue
        expected = str(entry.get("sha256") or "")
        if expected and _fingerprint(path) != expected:
            # 插件在注册表快照之后被更新/手改过：文件仍然可用，不能当成缺失，
            # 否则每次启动都会重试迁移并把它记为失败。
            log.warning("音源文件内容与注册表指纹不一致（按可用处理）：%s", relative)
        available += 1
    return available, missing


def _copy_missing(
    root: Path,
    entries: list[dict[str, Any]],
    home: Path,
    report: MigrationReport,
) -> None:
    for entry in entries:
        relative = str(entry.get("filename") or "")
        destination = _relative_target(home, relative)
        if destination is None:
            report.missing.append(relative or str(entry.get("id") or ""))
            continue
        if destination.is_file() and destination.stat().st_size > 0:
            report.skipped += 1
            continue
        source = root / relative
        if not source.is_file() or source.stat().st_size <= 0:
            report.missing.append(relative)
            continue
        if _copy_file(source, destination):
            report.migrated += 1
        else:
            report.missing.append(relative)


def migrate_legacy_sources(*, home: Path | None = None, roots: list[Path] | None = None) -> MigrationReport:
    """把旧音源搬进用户数据目录；可重复调用，失败时保持可重试状态。"""

    target_home = home or home_dir()
    report = MigrationReport()
    try:
        target_home.mkdir(parents=True, exist_ok=True)
        (target_home / "user_sources").mkdir(exist_ok=True)
        (target_home / "sources" / "active").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log_exception("创建音源目录失败", exc)
        report.reason = "无法创建音源目录"
        return report

    registry = target_home / REGISTRY_NAME
    candidates = [Path(root) for root in (roots if roots is not None else legacy_roots())]
    marker = _load_marker(target_home)

    # 已经有注册表：只补齐「注册表里还引用、但文件丢了」的插件。
    if registry.is_file():
        current = _read_json(registry)
        entries = _entries(current)
        pending = [
            root
            for root in candidates
            if root != target_home
            and (root / REGISTRY_NAME).is_file()
            and (marker.get("legacy") != str(root) or marker.get("sig") != _fingerprint(root / REGISTRY_NAME))
        ]
        if not pending:
            available, missing = verify_sources(target_home)
            report.verified = available
            report.missing = missing
            report.completed = True
            report.reason = "已迁移"
            return report
        for root in pending:
            report.backup = report.backup or str(backup_legacy_sources(root, home=target_home) or "")
            _copy_missing(root, entries, target_home, report)
        available, missing = verify_sources(target_home)
        report.verified = available
        report.missing = missing
        if missing:
            # 保留可重试状态：不写完成标记，下次启动继续尝试。
            log.warning("音源迁移尚有 %d 个文件缺失：%s", len(missing), ", ".join(missing[:5]))
        report.completed = not missing
        if report.completed:
            _write_marker(
                target_home,
                {
                    "version": MIGRATION_VERSION,
                    "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "legacy": str(pending[-1]),
                    "sig": _fingerprint(pending[-1] / REGISTRY_NAME),
                    "available": available,
                },
                report,
            )
            report.reason = "已迁移"
        else:
            report.reason = "部分插件文件缺失，将在下次启动重试"
        return report

    # 没有注册表：找一个真正带插件的旧目录，整份复制过来。
    source_root = None
    for root in candidates:
        path = root / REGISTRY_NAME
        if root == target_home or not path.is_file():
            continue
        entries = _entries(_read_json(path))
        if entries and any((root / str(entry.get("filename") or "")).is_file() for entry in entries):
            source_root = root
            break
    if source_root is None:
        _write_registry(target_home, {"version": MIGRATION_VERSION, "sources": []})
        _write_marker(
            target_home,
            {
                "version": MIGRATION_VERSION,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "legacy": "",
                "sig": "",
                "available": 0,
            },
            report,
        )
        report.completed = True
        report.reason = "没有需要迁移的旧音源"
        return report

    document = _read_json(source_root / REGISTRY_NAME)
    entries = _entries(document)
    report.backup = str(backup_legacy_sources(source_root, home=target_home) or "")
    _copy_missing(source_root, entries, target_home, report)
    available, missing = verify_sources_hypothetical(target_home, document)
    if missing:
        report.missing = missing
        report.verified = available
        report.completed = False
        report.reason = "部分插件文件缺失，旧文件已保留，下次启动重试"
        log.warning("首次迁移未完成：%s", ", ".join(missing[:5]))
        return report
    if not _write_registry(target_home, document):
        report.completed = False
        report.reason = "写入注册表失败"
        return report
    report.verified = available
    report.completed = True
    report.reason = "已迁移"
    _write_marker(
        target_home,
        {
            "version": MIGRATION_VERSION,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "legacy": str(source_root),
            "sig": _fingerprint(source_root / REGISTRY_NAME),
            "available": available,
        },
        report,
    )
    log.info("已把 %d 个音源迁移到 %s", available, target_home)
    return report


def verify_sources_hypothetical(home: Path, document: dict[str, Any]) -> tuple[int, list[str]]:
    """在写入注册表之前，按文档内容检查文件是否已经就位。"""

    available = 0
    missing: list[str] = []
    for entry in _entries(document):
        relative = str(entry.get("filename") or "")
        path = _relative_target(home, relative)
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            missing.append(relative or str(entry.get("id") or ""))
            continue
        expected = str(entry.get("sha256") or "")
        if expected and _fingerprint(path) != expected:
            log.warning("迁移后的音源指纹与注册表不一致（按可用处理）：%s", relative)
        available += 1
    return available, missing
