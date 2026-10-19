"""Writable source home for community playback plugins.

The bundled ``source_runtime`` lives inside the installation directory, which
may be read-only (Program Files). The plugin host accepts
``HUSHPLAYER_SOURCE_REGISTRY`` / ``HUSHPLAYER_SOURCE_HOME`` /
``HUSHPLAYER_USER_SOURCES`` so we materialise a writable copy of the registry
under the user data directory on first run. Install / remove operations only
ever touch that copy, never the bundled files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.logging_setup import get_logger, log_exception
from ..core.paths import data_dir, resource_path

__all__ = [
    "SourceRegistry",
    "registry",
    "MAX_SOURCE_BYTES",
    "RegistryError",
    "InstallReport",
    "collect_plugin_files",
]

log = get_logger(__name__)

MAX_SOURCE_BYTES = 2 * 1024 * 1024
_ACTIVE_DIR = "sources"
_USER_DIR = "user_sources"


class RegistryError(RuntimeError):
    """Raised when a source file cannot be installed or removed."""


@dataclass
class InstallReport:
    """Outcome of a batch install (multi-select or folder import)."""

    installed: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.installed) + len(self.duplicates) + len(self.failed)

    def summary(self) -> str:
        parts = [f"已安装 {len(self.installed)} 个音源"]
        if self.duplicates:
            parts.append(f"跳过 {len(self.duplicates)} 个重复")
        if self.failed:
            parts.append(f"失败 {len(self.failed)} 个")
        return "，".join(parts)

    def failure_text(self, limit: int = 8) -> str:
        lines = [f"{Path(name).name}：{reason}" for name, reason in self.failed[:limit]]
        if len(self.failed) > limit:
            lines.append(f"…另有 {len(self.failed) - limit} 个失败")
        return "\n".join(lines)


_PLUGIN_SUFFIXES = {".js", ".json"}


def collect_plugin_files(folder: str | Path, *, recursive: bool = False) -> list[Path]:
    """List installable MusicFree plugins in ``folder`` (newest first)."""
    root = Path(folder)
    if not root.is_dir():
        return []
    iterator = root.rglob("*") if recursive else root.glob("*")
    files = [
        path
        for path in iterator
        if path.is_file()
        and path.suffix.lower() in _PLUGIN_SUFFIXES
        and "node_modules" not in path.parts
    ]
    files.sort(key=lambda path: path.name.lower())
    return files


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError(f"音源注册表不可读：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise RegistryError("音源注册表格式不受支持")
    return data



_PLATFORM_RE = re.compile(r"""platform\s*:\s*["'`]([^"'`\r\n]{1,60})["'`]""")
_VERSION_RE = re.compile(r"""version\s*:\s*["'`]([^"'`\r\n]{1,30})["'`]""")
_AUTHOR_RE = re.compile(r"""author\s*:\s*["'`]([^"'`\r\n]{1,60})["'`]""")


def peek_plugin_metadata(raw: bytes) -> dict[str, str]:
    """Best-effort metadata for MusicFree plugins without executing them.

    Plugins declare ``platform``/``version``/``author`` as plain string
    literals in ``module.exports``; reading those keeps ``install_file``
    offline and side-effect free (loading is the plugin host's job).
    """
    try:
        head = raw[: 8192].decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001 - never fail an install over metadata
        return {}
    found: dict[str, str] = {}
    for key, pattern in (("platform", _PLATFORM_RE), ("version", _VERSION_RE), ("author", _AUTHOR_RE)):
        match = pattern.search(head)
        if match:
            found[key] = match.group(1).strip()
    return found

class SourceRegistry:
    """Manage the writable registry copy plus the user-installed plugins."""

    def __init__(self) -> None:
        self._home: Path | None = None

    # ------------------------------------------------------------------ 路径
    @property
    def home(self) -> Path:
        if self._home is None:
            self._home = data_dir() / "sources"
            self.ensure()
        return self._home

    @property
    def registry_path(self) -> Path:
        return self.home / "source_registry.json"

    @property
    def user_sources_dir(self) -> Path:
        path = self.home / _USER_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure(self) -> None:
        """Create the writable copy of the bundled runtime on first use."""
        home = data_dir() / "sources"
        home.mkdir(parents=True, exist_ok=True)
        (home / _USER_DIR).mkdir(exist_ok=True)
        (home / _ACTIVE_DIR).mkdir(exist_ok=True)
        target = home / "source_registry.json"
        if target.is_file():
            return
        bundled = resource_path("hushplayer", "runtime", "source_runtime")
        source = bundled / "source_registry.json"
        if not source.is_file():
            target.write_text('{"version": 1, "sources": []}', encoding="utf-8")
            return
        data = _read_json(source)
        for entry in data.get("sources", []):
            relative = str(entry.get("filename") or "").strip()
            if not relative:
                continue
            origin = bundled / relative
            if not origin.is_file():
                continue
            destination = home / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(origin, destination)
            except OSError as exc:
                log_exception(f"复制内置音源失败：{relative}", exc)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("已创建可写音源目录：%s（%d 个音源）", home, len(data.get("sources", [])))

    # ------------------------------------------------------------------ 读写
    def entries(self) -> list[dict[str, Any]]:
        return list(_read_json(self.registry_path).get("sources", []))

    def _save(self, data: dict[str, Any]) -> None:
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.registry_path)

    # ------------------------------------------------------------------ 安装
    def install_file(self, path: str | Path, *, content_policy: str = "user_owned") -> dict[str, Any]:
        source = Path(path)
        if not source.is_file():
            raise RegistryError("文件不存在")
        if source.suffix.lower() not in {".js", ".json"}:
            raise RegistryError("只支持 .js / .json 音源文件")
        size = source.stat().st_size
        if size <= 0 or size > MAX_SOURCE_BYTES:
            raise RegistryError("音源文件大小必须在 2 MB 以内")
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        data = _read_json(self.registry_path)
        entries = data.get("sources", [])
        for entry in entries:
            if str(entry.get("sha256") or "") == digest:
                raise RegistryError("该音源已经安装")
        identifier = f"user_source_{digest[:12]}"
        filename = f"{_USER_DIR}/{identifier}{source.suffix.lower()}"
        destination = self.home / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        meta = peek_plugin_metadata(raw)
        entry = {
            "id": identifier,
            "name": meta.get("platform") or source.stem,
            "platform": "custom",
            "author": meta.get("author", ""),
            "version": meta.get("version") or time.strftime("%Y.%m.%d"),
            "filename": filename,
            "sourceUrl": "",
            "enabled": True,
            "experimental": True,
            "trusted": False,
            "userInstalled": True,
            "contentPolicy": content_policy if content_policy in {"open", "user_owned"} else "user_owned",
            "sha256": digest,
            "capabilities": {
                "search": True,
                "metadata": True,
                "lyrics": True,
                "playback": True,
                "download": True,
                "downloadViaPlayback": True,
            },
            "lastTestStatus": "not_tested",
            "lastTestedAt": "",
        }
        entries.append(entry)
        data["sources"] = entries
        self._save(data)
        log.info("已安装音源：%s（%s）", entry["name"], identifier)
        return entry

    def remove(self, identifier: str, *, allow_bundled: bool = True) -> bool:
        """Remove a source from the writable registry.

        Bundled sources may be removed too (the original HushPlayer lets the
        user curate its source list); ``restore_bundled()`` brings them back.
        """
        data = _read_json(self.registry_path)
        entries = data.get("sources", [])
        kept: list[dict[str, Any]] = []
        removed: dict[str, Any] | None = None
        for entry in entries:
            if str(entry.get("id")) == identifier and (allow_bundled or entry.get("userInstalled")):
                removed = entry
            else:
                kept.append(entry)
        if removed is None:
            raise RegistryError("没有找到该音源")
        filename = str(removed.get("filename") or "")
        if filename.startswith(f"{_USER_DIR}/"):
            path = self.home / filename
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("删除音源文件失败：%s", exc)
        data["sources"] = kept
        self._save(data)
        log.info("已删除音源：%s", identifier)
        return True

    def restore_bundled(self) -> int:
        """Re-add every bundled source that is missing from the writable copy."""
        bundled = resource_path("hushplayer", "runtime", "source_runtime")
        bundled_registry = bundled / "source_registry.json"
        if not bundled_registry.is_file():
            return 0
        builtin = _read_json(bundled_registry).get("sources", [])
        data = _read_json(self.registry_path)
        entries = data.get("sources", [])
        known = {str(entry.get("id")) for entry in entries}
        added = 0
        for entry in builtin:
            identifier = str(entry.get("id") or "")
            if not identifier or identifier in known:
                continue
            relative = str(entry.get("filename") or "").strip()
            if relative:
                origin = bundled / relative
                destination = self.home / relative
                if origin.is_file() and not destination.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(origin, destination)
                    except OSError as exc:
                        log_exception(f"恢复内置音源文件失败：{relative}", exc)
                        continue
            entries.append(entry)
            known.add(identifier)
            added += 1
        if added:
            data["sources"] = entries
            self._save(data)
            log.info("已恢复 %d 个内置音源", added)
        return added

    def install_url(self, url: str, *, content_policy: str = "user_owned") -> dict[str, Any]:
        """Install a plugin from an https URL (MusicFree style share link)."""
        url = (url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise RegistryError("请输入 http(s) 音源地址")
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - requests is a hard dep
            raise RegistryError("缺少 requests 依赖") from exc
        try:
            response = requests.get(
                url,
                timeout=(8, 20),
                headers={"User-Agent": "HushPlayer/1.0 (source installer)"},
                stream=True,
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise RegistryError(f"下载音源失败：{exc}") from exc
        suffix = Path(url.split("?")[0]).suffix.lower()
        if suffix not in {".js", ".json"}:
            suffix = ".js"
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise RegistryError("音源文件超过 2 MB 限制")
                chunks.append(chunk)
        finally:
            response.close()
        if not chunks:
            raise RegistryError("音源文件为空")
        import tempfile

        handle, temp_path = tempfile.mkstemp(suffix=suffix, prefix="hush-source-")
        os.close(handle)
        try:
            Path(temp_path).write_bytes(b"".join(chunks))
            return self.install_file(temp_path, content_policy=content_policy)
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass

    def install_many(self, paths: list[str | Path]) -> InstallReport:
        """Install several plugins, collecting per-file errors instead of aborting."""
        report = InstallReport()
        seen: set[str] = set()
        for raw in paths:
            path = Path(raw)
            key = str(path.resolve()).lower()
            if key in seen:
                report.duplicates.append(path.name)
                continue
            seen.add(key)
            try:
                entry = self.install_file(path)
            except RegistryError as exc:
                message = str(exc)
                if "已经安装" in message:
                    report.duplicates.append(path.name)
                else:
                    report.failed.append((path.name, message))
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                log_exception(f"安装音源失败：{path}", exc)
                report.failed.append((path.name, str(exc)))
            else:
                report.installed.append(entry)
        log.info(
            "批量安装音源：%s / 重复 %s / 失败 %s",
            len(report.installed),
            len(report.duplicates),
            len(report.failed),
        )
        return report

    def set_enabled(self, identifier: str, enabled: bool) -> bool:
        data = _read_json(self.registry_path)
        changed = False
        for entry in data.get("sources", []):
            if str(entry.get("id")) == identifier:
                entry["enabled"] = bool(enabled)
                changed = True
        if changed:
            self._save(data)
        return changed


_registry: SourceRegistry | None = None


def registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry
