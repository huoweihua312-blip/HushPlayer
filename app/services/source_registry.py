from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit


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

    def get_source(self, source_id: str) -> dict | None:
        target = str(source_id or "").strip()
        for source in self.list_sources():
            if str(source.get("id") or "").strip() == target:
                return source
        return None

    def find_by_source_url(self, source_url: str) -> dict | None:
        normalized = self.normalize_source_url(source_url)
        if not normalized:
            return None
        for source in self.list_sources():
            try:
                current = self.normalize_source_url(str(source.get("sourceUrl") or ""))
            except SourceRegistryError:
                current = ""
            if current == normalized:
                return source
        return None

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

    def set_name(self, source_id: str, name: str) -> dict:
        display_name = " ".join(str(name or "").strip().split())
        if not display_name:
            raise SourceRegistryError("来源名称不能为空")
        if len(display_name) > 80:
            raise SourceRegistryError("来源名称不能超过 80 个字符")
        document = self.load_registry_document()
        for source in document["sources"]:
            if isinstance(source, dict) and source.get("id") == source_id:
                source["name"] = display_name
                source["nameCustomized"] = True
                self._save_registry_document(document)
                return dict(source)
        raise SourceRegistryError(f"没有找到音源：{source_id}")

    def authorize_user_source(self, source_id: str, content_policy: str) -> dict:
        policy = str(content_policy or "").strip().lower()
        if policy not in ALLOWED_CONTENT_POLICIES:
            raise SourceRegistryError("自定义来源必须明确标记为开放内容或用户自有内容")
        document = self.load_registry_document()
        for source in document["sources"]:
            if not isinstance(source, dict) or source.get("id") != source_id:
                continue
            filename = str(source.get("filename") or "").strip()
            source_file = self._resolve_registered_source_file(filename)
            text = self._decode_source(source_file)
            if source_file.suffix.lower() == ".json":
                try:
                    descriptor = json.loads(text)
                except json.JSONDecodeError as error:
                    raise SourceRegistryError(f"JSON 音源描述文件无效：{error}") from error
                playback_method = bool(isinstance(descriptor, dict) and descriptor.get("url"))
                download_method = playback_method
            else:
                playback_method = bool(re.search(r"\b(?:resolvePlayback|getMediaSource)\b", text))
                download_method = bool(re.search(r"\b(?:resolveDownload|getDownloadSource)\b", text))
            capabilities = dict(source.get("capabilities") or {})
            capabilities.update(
                {
                    "playback": playback_method,
                    "download": bool(download_method or playback_method),
                    "downloadViaPlayback": bool(playback_method and not download_method),
                }
            )
            source["contentPolicy"] = policy
            source["userInstalled"] = True
            source["enabled"] = True
            source["capabilities"] = capabilities
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

    def stage_bytes(
        self,
        content: bytes,
        suggested_name: str,
        source_url: str = "",
        content_policy: str = "unknown",
        user_installed: bool = False,
    ) -> dict:
        self.ensure_runtime_dirs()

        if not content:
            raise SourceRegistryError("音源内容为空")

        if len(content) > MAX_SOURCE_BYTES:
            raise SourceRegistryError("音源文件超过 2 MB，已拒绝导入")

        normalized_source_url = self.normalize_source_url(source_url) if source_url else ""
        normalized_policy = str(content_policy or "unknown").strip().lower()
        if normalized_policy not in ALLOWED_CONTENT_POLICIES:
            normalized_policy = "unknown"
        extension = Path(urlparse(normalized_source_url).path or suggested_name).suffix.lower()

        if extension not in {".js", ".json"}:
            stripped = content.lstrip()
            extension = ".json" if stripped.startswith((b"{", b"[")) else ".js"

        sha256 = hashlib.sha256(content).hexdigest()
        safe_stem = self._slug(Path(suggested_name).stem or "source")
        staging_name = f"{int(time.time())}_{safe_stem}_{sha256[:8]}{extension}"
        staging_path = self.staging_dir / staging_name
        staging_path.write_bytes(content)

        if extension == ".json":
            return self._analyze_json_manifest(
                staging_path,
                normalized_source_url,
                sha256,
                normalized_policy,
                bool(user_installed),
            )

        return self._analyze_javascript(
            staging_path,
            normalized_source_url,
            sha256,
            normalized_policy,
            bool(user_installed),
        )

    def _decode_source(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise SourceRegistryError("音源文件不是有效 UTF-8") from error

        beginning = text[:1200].lower()

        if "<html" in beginning or "<!doctype html" in beginning:
            raise SourceRegistryError("下载结果是 HTML 页面，不是音源文件")

        return text

    def _analyze_javascript(
        self,
        staging_path: Path,
        source_url: str,
        sha256: str,
        content_policy: str = "unknown",
        user_installed: bool = False,
    ) -> dict:
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
        staged_name = re.sub(r"^\d+_", "", staging_path.stem)
        staged_name = re.sub(r"_[0-9a-f]{8}$", "", staged_name, flags=re.I)
        name = platform or staged_name or "source"
        normalized_url = source_url
        if not normalized_url and embedded_url:
            try:
                normalized_url = self.normalize_source_url(embedded_url)
            except SourceRegistryError:
                normalized_url = ""
        stable_hash = (
            hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
            if normalized_url
            else sha256
        )
        source_id = f"custom_source_{stable_hash[:12]}" if normalized_url else f"{self._slug(name)}_{sha256[:8]}"
        policy_allowed = content_policy in ALLOWED_CONTENT_POLICIES
        playback_method = bool(re.search(r"\b(?:resolvePlayback|getMediaSource)\b", code))
        download_method = bool(re.search(r"\b(?:resolveDownload|getDownloadSource)\b", code))
        download_via_playback = bool(
            user_installed and policy_allowed and playback_method and not download_method
        )
        capabilities = {
            "search": bool(re.search(r"\bsearch\b", code)),
            "metadata": bool(re.search(r"\bgetMusic(?:Info|Detail)\b", code)),
            "lyrics": bool(re.search(r"\bgetLyric\b", code)),
            "playback": bool(user_installed and policy_allowed and playback_method),
            "download": bool(
                user_installed and policy_allowed and (download_method or playback_method)
            ),
            "downloadViaPlayback": download_via_playback,
        }
        return {
            "kind": "javascript",
            "stagingPath": str(staging_path),
            "id": source_id,
            "name": name,
            "platform": platform or name,
            "author": author,
            "version": version,
            "sourceUrl": normalized_url,
            "sha256": sha256,
            "requiredModules": required_modules,
            "missingModules": missing_modules,
            "securityStatus": "passed",
            "capabilities": capabilities,
            "experimental": True,
            "trusted": False,
            "userInstalled": bool(user_installed),
            "contentPolicy": content_policy,
        }

    def _analyze_json_manifest(
        self,
        staging_path: Path,
        source_url: str,
        sha256: str,
        content_policy: str = "unknown",
        user_installed: bool = False,
    ) -> dict:
        text = self._decode_source(staging_path)

        try:
            manifest = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceRegistryError(f"JSON 音源描述文件无效：{error}") from error

        if not isinstance(manifest, dict):
            raise SourceRegistryError("第一阶段仅支持单个 JSON 音源描述对象")

        manifest_policy = str(manifest.get("contentPolicy") or content_policy or "unknown").strip().lower()
        if manifest_policy not in ALLOWED_CONTENT_POLICIES:
            manifest_policy = "unknown"
        filename = str(manifest.get("filename") or "").strip()

        if not filename:
            media_url = str(manifest.get("url") or "").strip()
            if not media_url:
                raise SourceRegistryError("JSON 音源描述必须提供 filename 或直接媒体 url")
            parsed_media = urlparse(media_url)
            if parsed_media.scheme not in {"http", "https"} or not parsed_media.netloc:
                raise SourceRegistryError("JSON 音源的媒体 url 仅支持 HTTP 或 HTTPS")
            if parsed_media.username or parsed_media.password:
                raise SourceRegistryError("JSON 音源的媒体 url 不允许包含登录凭据")
            policy_allowed = manifest_policy in ALLOWED_CONTENT_POLICIES
            name = str(
                manifest.get("name")
                or manifest.get("title")
                or Path(urlparse(source_url).path).stem
                or "JSON 音源"
            )
            stable_hash = hashlib.sha256((source_url or sha256).encode("utf-8")).hexdigest()
            return {
                "kind": "json_track",
                "stagingPath": str(staging_path),
                "id": f"custom_source_{stable_hash[:12]}",
                "name": name,
                "platform": str(manifest.get("platform") or name),
                "author": str(manifest.get("author") or ""),
                "version": str(manifest.get("version") or ""),
                "sourceUrl": source_url,
                "sha256": sha256,
                "requiredModules": [],
                "missingModules": [],
                "securityStatus": "passed",
                "capabilities": {
                    "search": True,
                    "metadata": True,
                    "lyrics": False,
                    "playback": bool(user_installed and policy_allowed),
                    "download": bool(user_installed and policy_allowed),
                    "downloadViaPlayback": False,
                },
                "experimental": True,
                "trusted": False,
                "userInstalled": bool(user_installed),
                "contentPolicy": manifest_policy,
            }

        source_file = self._resolve_registered_source_file(filename)
        manifest_source_url = source_url or str(manifest.get("sourceUrl") or "")
        analyzed = self._analyze_javascript(
            source_file,
            manifest_source_url,
            sha256,
            manifest_policy,
            user_installed,
        )
        declared_capabilities = manifest.get("capabilities") or {}

        if not isinstance(declared_capabilities, dict):
            raise SourceRegistryError("JSON 音源描述的 capabilities 必须是对象")

        policy_allowed = manifest_policy in ALLOWED_CONTENT_POLICIES
        code = self._decode_source(source_file)
        playback_method = bool(re.search(r"\b(?:resolvePlayback|getMediaSource)\b", code))
        download_method = bool(re.search(r"\b(?:resolveDownload|getDownloadSource)\b", code))
        if user_installed:
            analyzed["capabilities"]["playback"] = policy_allowed and playback_method
            analyzed["capabilities"]["download"] = policy_allowed and (
                download_method or playback_method
            )
            analyzed["capabilities"]["downloadViaPlayback"] = (
                policy_allowed and playback_method and not download_method
            )
        else:
            analyzed["capabilities"]["playback"] = (
                policy_allowed and declared_capabilities.get("playback") is True and playback_method
            )
            analyzed["capabilities"]["download"] = (
                policy_allowed and declared_capabilities.get("download") is True and download_method
            )
            analyzed["capabilities"]["downloadViaPlayback"] = False
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
                "userInstalled": bool(user_installed),
                "contentPolicy": manifest_policy,
            }
        )
        return analyzed

    def install_candidate(self, candidate: dict, enabled: bool = False) -> dict:
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

            if source_url:
                try:
                    registered_url = self.normalize_source_url(str(source.get("sourceUrl") or ""))
                except SourceRegistryError:
                    registered_url = ""
                if registered_url == source_url:
                    raise SourceRegistryError("相同 URL 的音源已经安装")

        self.ensure_runtime_dirs()
        source_id = self._unique_source_id(str(candidate.get("id") or "source"), document["sources"])

        if candidate.get("kind") == "manifest":
            filename = str(candidate.get("filename") or "")
        else:
            staging_path = Path(str(candidate.get("stagingPath") or ""))

            if not staging_path.exists() or staging_path.parent.resolve() != self.staging_dir.resolve():
                raise SourceRegistryError("暂存音源文件不存在或路径无效")

            staging_suffix = staging_path.suffix.lower()
            target_suffix = ".json" if candidate.get("kind") == "json_track" else ".js"
            if staging_suffix in {".js", ".json"}:
                target_suffix = staging_suffix
            target_path = self.active_dir / f"{source_id}{target_suffix}"
            suffix = 2

            while target_path.exists():
                target_path = self.active_dir / f"{source_id}_{suffix}{target_suffix}"
                suffix += 1

            shutil.move(str(staging_path), str(target_path))
            filename = target_path.relative_to(self.runtime_dir).as_posix()

        entry = {
            "id": source_id,
            "name": str(candidate.get("name") or source_id),
            "nameCustomized": False,
            "platform": str(candidate.get("platform") or candidate.get("name") or source_id),
            "author": str(candidate.get("author") or ""),
            "version": str(candidate.get("version") or ""),
            "filename": filename,
            "sourceUrl": source_url,
            "enabled": bool(enabled),
            "experimental": True,
            "trusted": False,
            "userInstalled": bool(candidate.get("userInstalled", True)),
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

    def update_candidate(self, source_id: str, candidate: dict) -> dict:
        if candidate.get("securityStatus") != "passed":
            raise SourceRegistryError("更新内容尚未通过安全扫描")
        if candidate.get("missingModules"):
            modules = ", ".join(candidate["missingModules"])
            raise SourceRegistryError(f"更新内容需要未安装依赖：{modules}")
        document = self.load_registry_document()
        source = next(
            (
                item
                for item in document["sources"]
                if isinstance(item, dict) and item.get("id") == source_id
            ),
            None,
        )
        if source is None:
            raise SourceRegistryError(f"没有找到音源：{source_id}")
        candidate_url = self.normalize_source_url(str(candidate.get("sourceUrl") or ""))
        registered_url = self.normalize_source_url(str(source.get("sourceUrl") or ""))
        if not candidate_url or candidate_url != registered_url:
            raise SourceRegistryError("更新内容与已注册 URL 不一致")
        candidate_sha = str(candidate.get("sha256") or "").casefold()
        if candidate_sha and candidate_sha == str(source.get("sha256") or "").casefold():
            return {**dict(source), "unchanged": True}
        if candidate.get("kind") == "manifest":
            raise SourceRegistryError("引用外部文件的 JSON manifest 暂不支持自动更新")

        staging_path = Path(str(candidate.get("stagingPath") or ""))
        if not staging_path.exists() or staging_path.parent.resolve() != self.staging_dir.resolve():
            raise SourceRegistryError("暂存更新文件不存在或路径无效")
        self.ensure_runtime_dirs()
        current_filename = str(source.get("filename") or "").strip()
        current_path = (self.runtime_dir / current_filename).resolve() if current_filename else None
        managed_current = bool(
            current_path
            and self._is_inside(current_path, self.active_dir.resolve())
            and current_path.is_file()
        )
        target_suffix = ".json" if candidate.get("kind") == "json_track" else ".js"
        target_path = self.active_dir / f"{source_id}{target_suffix}"
        if target_path.exists() and (current_path is None or target_path.resolve() != current_path):
            target_path = self.active_dir / f"{source_id}_{candidate_sha[:8]}{target_suffix}"
        backup_path: Path | None = None
        try:
            if managed_current and current_path is not None:
                stamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = self.backups_dir / f"{self._slug(source_id)}_{stamp}{current_path.suffix}"
                suffix = 2
                while backup_path.exists():
                    backup_path = self.backups_dir / (
                        f"{self._slug(source_id)}_{stamp}_{suffix}{current_path.suffix}"
                    )
                    suffix += 1
                shutil.move(str(current_path), str(backup_path))
            shutil.move(str(staging_path), str(target_path))
            source.update(
                {
                    "name": str(
                        source.get("name")
                        if source.get("nameCustomized")
                        else candidate.get("name") or source.get("name") or source_id
                    ),
                    "platform": str(candidate.get("platform") or source.get("platform") or source_id),
                    "author": str(candidate.get("author") or ""),
                    "version": str(candidate.get("version") or ""),
                    "filename": target_path.relative_to(self.runtime_dir).as_posix(),
                    "sourceUrl": candidate_url,
                    "enabled": True,
                    "userInstalled": True,
                    "contentPolicy": str(candidate.get("contentPolicy") or "unknown"),
                    "sha256": candidate_sha,
                    "capabilities": dict(candidate.get("capabilities") or {}),
                    "lastTestStatus": "not_tested",
                    "lastTestedAt": "",
                }
            )
            self._save_registry_document(document)
        except Exception as error:
            if target_path.exists():
                try:
                    shutil.move(str(target_path), str(staging_path))
                except OSError:
                    pass
            if backup_path is not None and current_path is not None and backup_path.exists():
                try:
                    shutil.move(str(backup_path), str(current_path))
                except OSError:
                    pass
            if isinstance(error, SourceRegistryError):
                raise
            raise SourceRegistryError(f"更新音源失败，已尝试回滚：{error}") from error
        return {**dict(source), "backupPath": str(backup_path or ""), "unchanged": False}

    @staticmethod
    def normalize_source_url(source_url: str) -> str:
        text = str(source_url or "").strip()
        if not text:
            return ""
        try:
            parsed = urlsplit(text)
        except ValueError as error:
            raise SourceRegistryError(f"音源 URL 无效：{error}") from error
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise SourceRegistryError("音源 URL 仅支持 HTTP 或 HTTPS")
        if parsed.username or parsed.password:
            raise SourceRegistryError("音源 URL 不允许包含用户名或密码")
        hostname = parsed.hostname.casefold()
        host_token = f"[{hostname}]" if ":" in hostname else hostname
        try:
            port = parsed.port
        except ValueError as error:
            raise SourceRegistryError(f"音源 URL 端口无效：{error}") from error
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{host_token}:{port}"
        else:
            netloc = host_token
        path = parsed.path or "/"
        return urlunsplit((scheme, netloc, path, parsed.query, ""))

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
            "播放/下载仅对用户明确确认的开放内容或用户自有内容来源启用。\n"
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
