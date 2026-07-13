from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse


MAX_SOURCE_BYTES = 2 * 1024 * 1024
BLOCKED_MODULES = {
    "fs",
    "node:fs",
    "child_process",
    "node:child_process",
    "worker_threads",
    "node:worker_threads",
}
SAFE_BUILTINS = {
    "buffer",
    "node:buffer",
    "crypto",
    "node:crypto",
    "events",
    "node:events",
    "path",
    "node:path",
    "querystring",
    "node:querystring",
    "stream",
    "node:stream",
    "url",
    "node:url",
    "util",
    "node:util",
}
ALLOWED_CONTENT_POLICIES = {"open", "user_owned"}


class SourceRegistryError(RuntimeError):
    pass


class SourceRegistryManager:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.runtime_dir = self.project_root / "source_runtime"
        self.registry_path = self.runtime_dir / "source_registry.json"
        self.sources_dir = self.runtime_dir / "sources"
        self.staging_dir = self.sources_dir / "staging"
        self.active_dir = self.sources_dir / "active"
        self.backups_dir = self.sources_dir / "backups"
        self.user_sources_dir = self.project_root / "user_sources"

    def ensure_runtime_dirs(self) -> None:
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def load_registry_document(self) -> dict:
        if not self.registry_path.exists():
            return {"version": 1, "sources": []}

        try:
            document = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception as error:
            raise SourceRegistryError(f"读取音源注册表失败：{error}") from error

        if isinstance(document, list):
            document = {"version": 1, "sources": document}

        if not isinstance(document, dict) or not isinstance(document.get("sources"), list):
            raise SourceRegistryError("音源注册表必须包含 sources 数组")

        return document

    def list_sources(self) -> list[dict]:
        return [dict(source) for source in self.load_registry_document()["sources"] if isinstance(source, dict)]

    def _save_registry_document(self, document: dict) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.registry_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.registry_path)

    def set_enabled(self, source_id: str, enabled: bool) -> dict:
        document = self.load_registry_document()

        for source in document["sources"]:
            if source.get("id") == source_id:
                source["enabled"] = bool(enabled)
                self._save_registry_document(document)
                return dict(source)

        raise SourceRegistryError(f"没有找到音源：{source_id}")

    def remove_source(self, source_id: str) -> dict:
        """Remove a registry entry and preserve runtime-managed files as backups."""
        document = self.load_registry_document()
        source_index = next(
            (
                index
                for index, source in enumerate(document["sources"])
                if isinstance(source, dict) and source.get("id") == source_id
            ),
            -1,
        )
        if source_index < 0:
            raise SourceRegistryError(f"没有找到音源：{source_id}")

        source = document["sources"][source_index]
        filename = str(source.get("filename") or "").strip()
        source_path = (self.runtime_dir / filename).resolve() if filename else None
        sources_root = self.sources_dir.resolve()
        backups_root = self.backups_dir.resolve()
        managed_file = bool(
            source_path
            and self._is_inside(source_path, sources_root)
            and not self._is_inside(source_path, backups_root)
        )
        backup_path: Path | None = None

        if managed_file and source_path is not None and source_path.exists():
            if not source_path.is_file():
                raise SourceRegistryError("音源路径不是普通文件，已停止删除")
            self.ensure_runtime_dirs()
            stamp = time.strftime("%Y%m%d_%H%M%S")
            safe_id = self._slug(str(source.get("id") or "source"))
            backup_path = self.backups_dir / f"{safe_id}_{stamp}{source_path.suffix or '.js'}"
            suffix = 2
            while backup_path.exists():
                backup_path = self.backups_dir / (
                    f"{safe_id}_{stamp}_{suffix}{source_path.suffix or '.js'}"
                )
                suffix += 1
            try:
                shutil.move(str(source_path), str(backup_path))
            except OSError as error:
                raise SourceRegistryError(f"备份音源文件失败，未删除注册记录：{error}") from error

        document["sources"].pop(source_index)
        try:
            self._save_registry_document(document)
        except Exception as error:
            if backup_path is not None and source_path is not None and backup_path.exists():
                try:
                    shutil.move(str(backup_path), str(source_path))
                except OSError as rollback_error:
                    raise SourceRegistryError(
                        f"保存注册表失败，且文件回滚失败：{rollback_error}"
                    ) from error
            raise SourceRegistryError(f"保存注册表失败，删除已回滚：{error}") from error

        return {
            "source": dict(source),
            "backupPath": str(backup_path) if backup_path is not None else "",
            "externalFilePreserved": bool(source_path and not managed_file),
        }

    def record_test_result(self, source_id: str, status: str) -> None:
        document = self.load_registry_document()

        for source in document["sources"]:
            if source.get("id") == source_id:
                source["lastTestStatus"] = str(status or "unknown")
                source["lastTestedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                self._save_registry_document(document)
                return

    def stage_local_file(self, source_path: Path) -> dict:
        path = Path(source_path)

        if not path.exists() or not path.is_file():
            raise SourceRegistryError("所选音源文件不存在")

        return self.stage_bytes(path.read_bytes(), path.name, source_url="")

    def stage_bytes(self, content: bytes, suggested_name: str, source_url: str = "") -> dict:
        self.ensure_runtime_dirs()

        if not content:
            raise SourceRegistryError("音源内容为空")

        if len(content) > MAX_SOURCE_BYTES:
            raise SourceRegistryError("音源文件超过 2 MB，已拒绝导入")

        extension = Path(urlparse(source_url).path or suggested_name).suffix.lower()

        if extension not in {".js", ".json"}:
            stripped = content.lstrip()
            extension = ".json" if stripped.startswith((b"{", b"[")) else ".js"

        sha256 = hashlib.sha256(content).hexdigest()
        safe_stem = self._slug(Path(suggested_name).stem or "source")
        staging_name = f"{int(time.time())}_{safe_stem}_{sha256[:8]}{extension}"
        staging_path = self.staging_dir / staging_name
        staging_path.write_bytes(content)

        if extension == ".json":
            return self._analyze_json_manifest(staging_path, source_url, sha256)

        return self._analyze_javascript(staging_path, source_url, sha256)

    def _decode_source(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise SourceRegistryError("音源文件不是有效 UTF-8") from error

        beginning = text[:1200].lower()

        if "<html" in beginning or "<!doctype html" in beginning:
            raise SourceRegistryError("下载结果是 HTML 页面，不是音源文件")

        return text

    def _analyze_javascript(self, staging_path: Path, source_url: str, sha256: str) -> dict:
        code = self._decode_source(staging_path)
        required_modules = sorted(
            set(re.findall(r"require\s*\(\s*[\"']([^\"']+)[\"']\s*\)", code))
        )
        blocked = [name for name in required_modules if name in BLOCKED_MODULES]
        suspicious_patterns = {
            "process.mainModule": r"process\s*\.\s*mainModule",
            "process.binding": r"process\s*\.\s*binding\s*\(",
            "process.kill": r"process\s*\.\s*kill\s*\(",
        }
        suspicious = [name for name, pattern in suspicious_patterns.items() if re.search(pattern, code, re.I)]

        if blocked or suspicious:
            details = ", ".join(blocked + suspicious)
            raise SourceRegistryError(f"安全扫描拒绝该音源：{details}")

        missing_modules = [
            name
            for name in required_modules
            if not name.startswith((".", "/"))
            and name not in SAFE_BUILTINS
            and not self._node_module_exists(name)
        ]
        platform = self._extract_js_string(code, "platform")
        author = self._extract_js_string(code, "author")
        version = self._extract_js_string(code, "version")
        embedded_url = self._extract_js_string(code, "srcUrl")
        name = platform or staging_path.stem
        source_id = f"{self._slug(name)}_{sha256[:8]}"
        capabilities = {
            "search": bool(re.search(r"\bsearch\b", code)),
            "metadata": bool(re.search(r"\bgetMusic(?:Info|Detail)\b", code)),
            "lyrics": bool(re.search(r"\bgetLyric\b", code)),
            "playback": False,
            "download": False,
        }
        return {
            "kind": "javascript",
            "stagingPath": str(staging_path),
            "id": source_id,
            "name": name,
            "platform": platform or name,
            "author": author,
            "version": version,
            "sourceUrl": source_url or embedded_url,
            "sha256": sha256,
            "requiredModules": required_modules,
            "missingModules": missing_modules,
            "securityStatus": "passed",
            "capabilities": capabilities,
            "experimental": True,
            "trusted": False,
            "contentPolicy": "unknown",
        }

    def _analyze_json_manifest(self, staging_path: Path, source_url: str, sha256: str) -> dict:
        text = self._decode_source(staging_path)

        try:
            manifest = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceRegistryError(f"JSON 音源描述文件无效：{error}") from error

        if not isinstance(manifest, dict):
            raise SourceRegistryError("第一阶段仅支持单个 JSON 音源描述对象")

        filename = str(manifest.get("filename") or "").strip()

        if not filename:
            raise SourceRegistryError("JSON 音源描述必须提供 filename")

        source_file = self._resolve_registered_source_file(filename)
        analyzed = self._analyze_javascript(source_file, source_url or str(manifest.get("sourceUrl") or ""), sha256)
        declared_capabilities = manifest.get("capabilities") or {}

        if not isinstance(declared_capabilities, dict):
            raise SourceRegistryError("JSON 音源描述的 capabilities 必须是对象")

        content_policy = str(manifest.get("contentPolicy") or "unknown").strip().lower()
        policy_allowed = content_policy in ALLOWED_CONTENT_POLICIES
        code = self._decode_source(source_file)
        playback_method = bool(re.search(r"\b(?:resolvePlayback|getMediaSource)\b", code))
        download_method = bool(re.search(r"\b(?:resolveDownload|getDownloadSource)\b", code))
        analyzed["capabilities"]["playback"] = (
            policy_allowed and declared_capabilities.get("playback") is True and playback_method
        )
        analyzed["capabilities"]["download"] = (
            policy_allowed and declared_capabilities.get("download") is True and download_method
        )
        analyzed.update(
            {
                "kind": "manifest",
                "stagingPath": str(staging_path),
                "id": str(manifest.get("id") or analyzed["id"]),
                "name": str(manifest.get("name") or analyzed["name"]),
                "platform": str(manifest.get("platform") or analyzed["platform"]),
                "author": str(manifest.get("author") or analyzed["author"]),
                "version": str(manifest.get("version") or analyzed["version"]),
                "filename": filename.replace("\\", "/"),
                "sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
                "contentPolicy": content_policy,
            }
        )
        return analyzed

    def install_candidate(self, candidate: dict) -> dict:
        if candidate.get("securityStatus") != "passed":
            raise SourceRegistryError("音源尚未通过安全扫描")

        if candidate.get("missingModules"):
            modules = ", ".join(candidate["missingModules"])
            raise SourceRegistryError(f"该音源需要依赖 {modules}，目前未安装")

        document = self.load_registry_document()
        source_url = str(candidate.get("sourceUrl") or "").strip()
        sha256 = str(candidate.get("sha256") or "").lower()

        for source in document["sources"]:
            if sha256 and str(source.get("sha256") or "").lower() == sha256:
                raise SourceRegistryError("相同 SHA-256 的音源已经安装")

            if source_url and str(source.get("sourceUrl") or "").strip() == source_url:
                raise SourceRegistryError("相同 URL 的音源已经安装")

        self.ensure_runtime_dirs()
        source_id = self._unique_source_id(str(candidate.get("id") or "source"), document["sources"])

        if candidate.get("kind") == "manifest":
            filename = str(candidate.get("filename") or "")
        else:
            staging_path = Path(str(candidate.get("stagingPath") or ""))

            if not staging_path.exists() or staging_path.parent.resolve() != self.staging_dir.resolve():
                raise SourceRegistryError("暂存音源文件不存在或路径无效")

            target_path = self.active_dir / f"{source_id}.js"
            suffix = 2

            while target_path.exists():
                target_path = self.active_dir / f"{source_id}_{suffix}.js"
                suffix += 1

            shutil.move(str(staging_path), str(target_path))
            filename = target_path.relative_to(self.runtime_dir).as_posix()

        entry = {
            "id": source_id,
            "name": str(candidate.get("name") or source_id),
            "platform": str(candidate.get("platform") or candidate.get("name") or source_id),
            "author": str(candidate.get("author") or ""),
            "version": str(candidate.get("version") or ""),
            "filename": filename,
            "sourceUrl": source_url,
            "enabled": False,
            "experimental": True,
            "trusted": False,
            "userInstalled": True,
            "contentPolicy": str(candidate.get("contentPolicy") or "unknown"),
            "sha256": sha256,
            "capabilities": {
                **dict(candidate.get("capabilities") or {}),
            },
            "lastTestStatus": "not_tested",
            "lastTestedAt": "",
        }
        document["sources"].append(entry)
        self._save_registry_document(document)
        return dict(entry)

    def describe_candidate(self, candidate: dict) -> str:
        capabilities = candidate.get("capabilities") or {}
        feature_names = [
            label
            for key, label in (
                ("search", "搜索"),
                ("metadata", "元数据"),
                ("lyrics", "歌词"),
                ("playback", "播放"),
                ("download", "下载"),
            )
            if capabilities.get(key)
        ]
        dependencies = candidate.get("requiredModules") or []
        missing = candidate.get("missingModules") or []
        return (
            f"名称：{candidate.get('name') or '未知'}\n"
            f"平台：{candidate.get('platform') or '未知'}\n"
            f"作者：{candidate.get('author') or '未知'}\n"
            f"版本：{candidate.get('version') or '未知'}\n"
            f"能力：{'、'.join(feature_names) or '未识别'}\n"
            f"依赖：{', '.join(dependencies) or '无'}\n"
            f"缺少依赖：{', '.join(missing) or '无'}\n"
            f"SHA-256：{candidate.get('sha256') or ''}\n"
            f"内容策略：{candidate.get('contentPolicy') or 'unknown'}\n"
            "播放/下载仅对明确声明为开放内容或用户自有内容的 JSON 音源启用。\n"
            "安全提示：静态扫描不能替代完整沙箱，请只启用你信任的音源。"
        )

    def _resolve_registered_source_file(self, filename: str) -> Path:
        candidate = (self.runtime_dir / filename).resolve()
        allowed_roots = [self.sources_dir.resolve(), self.user_sources_dir.resolve()]

        if not any(self._is_inside(candidate, root) for root in allowed_roots):
            raise SourceRegistryError("JSON 描述引用的音源超出允许目录")

        if not candidate.exists() or not candidate.is_file():
            raise SourceRegistryError(f"JSON 描述引用的音源不存在：{filename}")

        return candidate

    def _node_module_exists(self, module_name: str) -> bool:
        package_name = "/".join(module_name.split("/")[:2]) if module_name.startswith("@") else module_name.split("/")[0]
        return (self.runtime_dir / "node_modules" / package_name).exists()

    @staticmethod
    def _extract_js_string(code: str, field: str) -> str:
        match = re.search(rf"\b{re.escape(field)}\s*:\s*[\"']([^\"']{{1,160}})[\"']", code)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        return slug or "source"

    @staticmethod
    def _unique_source_id(base_id: str, sources: list[dict]) -> str:
        existing = {str(source.get("id") or "") for source in sources}
        candidate = SourceRegistryManager._slug(base_id)
        suffix = 2

        while candidate in existing:
            candidate = f"{SourceRegistryManager._slug(base_id)}_{suffix}"
            suffix += 1

        return candidate

    @staticmethod
    def _is_inside(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False
