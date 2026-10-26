"""HushPlayer 的敏感信息与发行内容检查。

这个脚本是「个人数据不进 Git、不进发行包」这条红线的可执行版本：

* ``--staged``  检查即将提交的内容（pre-commit 钩子用）；
* ``--tracked`` 检查当前仓库跟踪的全部文本文件；
* ``--path``    检查任意目录（构建产物、临时目录）；
* ``--zip``     检查 zip 里的文件名与文本内容（PyInstaller 便携包）；
* ``--inno``    检查 Inno Setup 脚本里的 ``[Files]`` 来源是否越界，再扫 dist。

发现 ``high`` 级别问题时返回退出码 1，调用方（git 钩子、build.ps1）必须
以失败处理。允许的例外写在 ``tools/security_allowlist.json`` 里，并且必须
带 ``reason``；不允许用「忽略整个音源目录」的方式绕过检查。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

__all__ = [
    "Finding",
    "ScanResult",
    "HIGH",
    "MEDIUM",
    "LOW",
    "ALLOWLIST_NAME",
    "RULES",
    "scan_bytes",
    "scan_path",
    "scan_paths",
    "scan_zip",
    "scan_staged",
    "scan_tracked",
    "scan_inno",
    "load_allowlist",
    "release_layout_problems",
]

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

ALLOWLIST_NAME = "security_allowlist.json"
MAX_TEXT_BYTES = 2 * 1024 * 1024

FRAMEWORK_JS = {
    "plugin_host.js",
    "runner.js",
    "source_test_worker.js",
    "playback_protocol_self_test.js",
}

USER_STATE_FILES = {
    "settings.json",
    "play_queue.json",
    "playback_session.json",
    "library.json",
    "playlists.json",
    "stats.json",
    "pending_imports.json",
    "ignored_imports.json",
    "remote_tracks.json",
    "lyrics_bindings.json",
    "metadata_cache.json",
    "online_source_memory.json",
    "source_health.json",
}

DB_SUFFIXES = {".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".sqlite-wal", ".sqlite-shm"}
SECRET_SUFFIXES = {".key", ".p12", ".pfx"}
# .pem 既可能是私钥也可能是 CA 证书包（certifi）。只有名字带这些提示才按凭据处理。
PEM_HINTS = ("key", "secret", "private", "credential", "token", "id_rsa", "id_ed25519")
SECRET_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.json", "cookies.txt"}
LOG_SUFFIXES = {".log", ".stackdump"}

# 值本身是占位符时不算泄密：${MUSIC_U} / <token> / YOUR_KEY / xxxx / 空串 ...
_PLACEHOLDER = re.compile(
    r"^(?:\$\{.*\}|<.*>|\{\{.*\}\}|%[A-Za-z_]+%|YOUR[_-].*|xxx+|x{3,}|\*+|0+|none|null|nil|"
    r"(?:example|sample|dummy|fake|test|placeholder|redacted|changeme)[\w-]*|-+)$",
    re.IGNORECASE,
)
_GENERIC_USERS = {"public", "default", "defaultuser0", "administrator", "wdagutilityaccount", "user"}


def _is_placeholder(value: str) -> bool:
    text = (value or "").strip().strip("\"'")
    if not text:
        return True
    if "${" in text or "{{" in text or "%" in text:
        return True
    return bool(_PLACEHOLDER.match(text))


# 文本规则：(id, severity, 正则, 说明)
RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        HIGH,
        re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
        "私钥内容",
    ),
    (
        "github_token",
        HIGH,
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        "GitHub Token",
    ),
    ("aws_access_key", HIGH, re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS Access Key"),
    (
        "bearer_token",
        HIGH,
        re.compile(r"\bBearer\s+([A-Za-z0-9._~+/=-]{20,})"),
        "Bearer Token",
    ),
    (
        "music_u_cookie",
        HIGH,
        re.compile(r"\bMUSIC_U\b\s*[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}]{8,})"),
        "网易云 MUSIC_U 登录 Cookie",
    ),
    (
        "music_a_cookie",
        HIGH,
        re.compile(r"\bMUSIC_A\b\s*[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}]{8,})"),
        "网易云 MUSIC_A 登录 Cookie",
    ),
    (
        "csrf_cookie",
        MEDIUM,
        re.compile(r"\b__csrf\b\s*[\"']?\s*[:=]\s*[\"']?([^\"'\s,;}]{8,})"),
        "CSRF Cookie",
    ),
    (
        "cookie_header",
        MEDIUM,
        re.compile(r"(?i)\bCookie\s*[:=]\s*[\"']?([^\"'\n]{16,})"),
        "明文 Cookie 头",
    ),
    (
        "signed_url",
        MEDIUM,
        re.compile(
            r"https?://[^\s\"'<>]*[?&](?:auth|token|sign|signature|expire|expires|key|keyid|mkey)=([^&\s\"'<>]{12,})"
        ),
        "带签名的临时播放 URL",
    ),
    (
        "user_home_path",
        MEDIUM,
        re.compile(r"\b[A-Za-z]:\\{1,2}Users\\{1,2}([A-Za-z0-9._-]+)"),
        "个人绝对路径",
    ),
    (
        "personal_email",
        MEDIUM,
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@(?:qq|163|126|yeah|gmail|outlook|hotmail|foxmail|icloud|protonmail)\.(?:com|cn)\b",
            re.IGNORECASE,
        ),
        "个人邮箱",
    ),
)

NAME_RULES: tuple[tuple[str, str, str], ...] = (
    ("music_plugin", HIGH, "个人音源插件（active/backups/staging）"),
    ("source_registry", HIGH, "含音源条目的注册表"),
    ("user_database", HIGH, "用户数据库 / WAL"),
    ("user_state", HIGH, "用户歌单、设置或播放状态"),
    ("credential_file", HIGH, "凭据或私钥文件"),
    ("probe_output", MEDIUM, "带真实播放地址的探测结果"),
    ("log_or_dump", MEDIUM, "运行日志或崩溃转储"),
)


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    line: int = 0
    detail: str = ""
    snippet: str = ""
    allowed: str = ""

    def format(self) -> str:
        where = self.path if not self.line else f"{self.path}:{self.line}"
        tail = f"（已允许：{self.allowed}）" if self.allowed else ""
        return f"[{self.severity.upper():6}] {self.rule:16} {where}  {self.detail}{tail}"

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "detail": self.detail,
            "snippet": self.snippet,
            "allowed": self.allowed,
        }


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    scanned_files: int = 0
    scanned_bytes: int = 0

    @property
    def blocked(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == HIGH and not item.allowed]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == MEDIUM and not item.allowed]

    def extend(self, other: "ScanResult") -> None:
        self.findings.extend(other.findings)
        self.scanned_files += other.scanned_files
        self.scanned_bytes += other.scanned_bytes

    def summary(self) -> str:
        if not self.findings:
            return f"已检查 {self.scanned_files} 个文件，未发现敏感信息"
        blocked = len(self.blocked)
        warned = len(self.warnings)
        allowed = len(self.findings) - blocked - warned
        return (
            f"已检查 {self.scanned_files} 个文件：{blocked} 项高风险，"
            f"{warned} 项提醒，{allowed} 项按白名单放行"
        )


# --------------------------------------------------------------------------- 白名单
def load_allowlist(path: Path | None = None) -> list[dict[str, str]]:
    target = path or Path(__file__).resolve().parent / ALLOWLIST_NAME
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return []
    cleaned: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pattern = str(entry.get("path") or "").strip()
        rule = str(entry.get("rule") or "*").strip() or "*"
        reason = str(entry.get("reason") or "").strip()
        if not pattern or not reason:
            continue
        cleaned.append({"path": pattern.replace("\\", "/"), "rule": rule, "reason": reason})
    return cleaned


def _allowance(path: str, rule: str, allowlist: Sequence[dict[str, str]]) -> str:
    normalized = path.replace("\\", "/")
    # 发行目录扫描会带上产物根名（如 ``HushPlayer/_internal/...``），
    # 去掉第一段后再匹配一次，仓库相对路径的白名单才能继续生效。
    candidates = [normalized, Path(normalized).name]
    parts = normalized.split("/", 1)
    if len(parts) == 2:
        candidates.append(parts[1])
    # 发行包里的路径会带 ``_internal/`` 前缀；把仓库相对段提出来再匹配一次。
    for anchor in ("hushplayer/", "packaging/", "tools/", "docs/", "tests/", "assets/"):
        index = normalized.find(anchor)
        if index > 0:
            candidates.append(normalized[index:])
    for entry in allowlist:
        if entry["rule"] not in ("*", rule):
            continue
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, entry["path"]):
                return entry["reason"]
    return ""


# --------------------------------------------------------------------------- 名称规则
def _name_findings(path: str, text: str | None, allowlist: Sequence[dict[str, str]]) -> list[Finding]:
    normalized = path.replace("\\", "/")
    name = Path(normalized).name
    lower = name.lower()
    parts = normalized.split("/")
    findings: list[Finding] = []

    def add(rule: str, severity: str, detail: str) -> None:
        findings.append(
            Finding(rule=rule, severity=severity, path=normalized, detail=detail,
                    allowed=_allowance(normalized, rule, allowlist))
        )

    if "node_modules/" not in normalized and "source_runtime/" in normalized:
        relative = normalized.split("source_runtime/", 1)[1]
        if relative.startswith(("sources/", "user_sources/")):
            add("music_plugin", HIGH, NAME_RULES[0][2])
        elif relative.count("/") == 0 and relative.lower().endswith(".js") and relative not in FRAMEWORK_JS:
            add("music_plugin", HIGH, "音源插件脚本（运行框架之外）")
    if name == "source_registry.json":
        document: dict[str, object] = {}
        if text is not None:
            try:
                loaded = json.loads(text)
                document = loaded if isinstance(loaded, dict) else {}
            except ValueError:
                document = {}
        sources = document.get("sources")
        if isinstance(sources, list) and sources:
            add("source_registry", HIGH, f"注册表含 {len(sources)} 个个人音源条目")
        elif text is None and any(part in ("sources", "user_sources") for part in parts):
            add("source_registry", HIGH, "可能含个人音源条目")
    lowered = lower
    if lowered.endswith(tuple(DB_SUFFIXES)):
        add("user_database", HIGH, "SQLite 数据库或 WAL 文件")
    if lowered in USER_STATE_FILES:
        add("user_state", HIGH, "用户歌单 / 设置 / 播放历史")
    if lowered in SECRET_NAMES or lowered.endswith(tuple(SECRET_SUFFIXES)):
        add("credential_file", HIGH, "凭据或私钥文件")
    elif lowered.endswith(".pem") and any(hint in lowered for hint in PEM_HINTS):
        add("credential_file", HIGH, "私钥 PEM 文件（CA 证书包不算）")
    elif lowered.endswith((".dmp", ".etl")):
        add("log_or_dump", MEDIUM, "崩溃转储或事件日志")
    if lowered.endswith(("_source_probe.txt", ".probe.txt", "probe_output.txt")):
        add("probe_output", MEDIUM, "探测输出可能包含真实播放地址")
    if lowered.endswith(tuple(LOG_SUFFIXES)):
        add("log_or_dump", MEDIUM, "日志或转储文件")
    return findings


def _redacted(match: re.Match[str]) -> str:
    value = match.group(match.lastindex or 0) if match.lastindex else ""
    if not value:
        return "***"
    return f"***（长度 {len(value)}）"


# --------------------------------------------------------------------------- 文本规则
def scan_bytes(path: str, data: bytes, allowlist: Sequence[dict[str, str]] = ()) -> ScanResult:
    result = ScanResult(scanned_files=1, scanned_bytes=len(data))
    findings = _name_findings(path, None, allowlist)
    result.findings.extend(findings)
    if len(data) > MAX_TEXT_BYTES:
        return result
    if b"\x00" in data[:4096]:
        return result
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - 极端编码
            return result
    if path.replace("\\", "/").endswith("source_registry.json"):
        result.findings.extend(_name_findings(path, text, allowlist))
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(line) > 20000:
            continue
        for rule, severity, pattern, detail in RULES:
            for match in pattern.finditer(line):
                if rule in ("music_u_cookie", "music_a_cookie", "csrf_cookie", "cookie_header",
                            "bearer_token", "signed_url") and _is_placeholder(match.group(1)):
                    continue
                if rule == "user_home_path" and match.group(1).lower() in _GENERIC_USERS:
                    continue
                if rule == "personal_email" and "noreply" in match.group(0).lower():
                    continue
                result.findings.append(
                    Finding(
                        rule=rule,
                        severity=severity,
                        path=path,
                        line=line_number,
                        detail=f"{detail}：{_redacted(match)}",
                        snippet="",
                        allowed=_allowance(path, rule, allowlist),
                    )
                )
    return result


def scan_path(target: Path, allowlist: Sequence[dict[str, str]] = (), *, root_label: str = "") -> ScanResult:
    result = ScanResult()
    path = Path(target)
    if path.is_file():
        try:
            data = path.read_bytes()
        except OSError:
            return result
        return scan_bytes(root_label or str(path), data, allowlist)
    if not path.is_dir():
        return result
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        if any(part in {".git", "__pycache__", "node_modules"} for part in item.parts):
            continue
        try:
            data = item.read_bytes()
        except OSError:
            continue
        relative = item.relative_to(path).as_posix()
        label = f"{root_label.rstrip('/')}/{relative}" if root_label else relative
        result.extend(scan_bytes(label, data, allowlist))
    return result


def scan_paths(targets: Iterable[Path], allowlist: Sequence[dict[str, str]] = (), *, root_label: str = "") -> ScanResult:
    result = ScanResult()
    for target in targets:
        result.extend(scan_path(Path(target), allowlist, root_label=root_label))
    return result


# --------------------------------------------------------------------------- Git
def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, cwd=Path(__file__).resolve().parent.parent
    ).stdout


def scan_staged(allowlist: Sequence[dict[str, str]] = ()) -> ScanResult:
    result = ScanResult()
    names = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").split(b"\0")
    for raw in names:
        name = raw.decode("utf-8", errors="replace").strip()
        if not name:
            continue
        try:
            data = _git("show", f":{name}")
        except subprocess.CalledProcessError:
            continue
        result.extend(scan_bytes(name, data, allowlist))
    return result


def scan_tracked(allowlist: Sequence[dict[str, str]] = (), *, include_untracked: bool = False) -> ScanResult:
    result = ScanResult()
    flag = "-co" if include_untracked else "-c"
    names = _git("ls-files", flag, "--exclude-standard", "-z").split(b"\0")
    root = Path(__file__).resolve().parent.parent
    for raw in names:
        name = raw.decode("utf-8", errors="replace").strip()
        if not name:
            continue
        path = root / name
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        result.extend(scan_bytes(name, data, allowlist))
    return result


# --------------------------------------------------------------------------- Zip / Inno
def scan_zip(target: Path, allowlist: Sequence[dict[str, str]] = ()) -> ScanResult:
    result = ScanResult()
    try:
        with zipfile.ZipFile(target) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    result.findings.append(
                        Finding(rule="unsafe_zip_entry", severity=HIGH, path=name, detail="zip 内路径穿越")
                    )
                    continue
                try:
                    data = archive.read(info)[:MAX_TEXT_BYTES]
                except (OSError, zipfile.BadZipFile):
                    continue
                result.extend(scan_bytes(name, data, allowlist))
    except (OSError, zipfile.BadZipFile) as exc:
        result.findings.append(
            Finding(rule="unreadable_zip", severity=HIGH, path=str(target), detail=f"无法读取压缩包：{exc}")
        )
    return result


def scan_inno(script: Path, dist: Path, allowlist: Sequence[dict[str, str]] = ()) -> ScanResult:
    """检查 installer.iss 的 [Files] 来源：只允许来自 dist，且不得含个人数据。"""

    result = ScanResult()
    script = Path(script)
    dist = Path(dist)
    try:
        text = script.read_text(encoding="utf-8")
    except OSError as exc:
        result.findings.append(
            Finding(rule="missing_installer", severity=HIGH, path=str(script), detail=f"无法读取安装脚本：{exc}")
        )
        return result
    dist_norm = str(dist.resolve()).replace("\\", "/").rstrip("/")
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.lower().startswith("source:"):
            continue
        raw = stripped.split(":", 1)[1].split(";", 1)[0].strip().strip('"')
        expanded = raw.replace("{#SourceRoot}", str(dist))
        normalized = expanded.replace("\\", "/")
        if "*" not in normalized and not normalized.lower().endswith((".exe", ".dll", ".iss")):
            pass
        base = normalized.split("*", 1)[0]
        base_path = Path(base)
        try:
            resolved = str(base_path.resolve()).replace("\\", "/")
        except OSError:
            resolved = base.replace("\\", "/")
        if not resolved.startswith(dist_norm):
            result.findings.append(
                Finding(
                    rule="installer_source_escape",
                    severity=HIGH,
                    path=f"{script.name}:{number}",
                    detail=f"[Files] Source 指向发行目录之外：{raw}",
                )
            )
        lowered = normalized.lower()
        if "/sources/" in lowered or lowered.endswith("qq.js") or "settings.json" in lowered:
            result.findings.append(
                Finding(
                    rule="installer_private_file",
                    severity=HIGH,
                    path=f"{script.name}:{number}",
                    detail=f"[Files] 引入个人数据：{raw}",
                )
            )
    scan_result = scan_path(dist, allowlist)
    result.extend(scan_result)
    return result


# --------------------------------------------------------------------------- 发行布局
REQUIRED_RELEASE_FILES = (
    "HushPlayer.exe",
    "_internal/hushplayer/runtime/source_runtime/plugin_host.js",
    "_internal/hushplayer/runtime/source_runtime/runner.js",
    "_internal/hushplayer/runtime/source_runtime/source_registry.json",
)
FORBIDDEN_RELEASE_PATHS = (
    "_internal/hushplayer/runtime/source_runtime/sources",
    "sources",
    "Data",
    "settings.json",
    "play_queue.json",
    "hushplayer.db",
    "_internal/hushplayer/runtime/source_runtime/qq.js",
)


def release_layout_problems(dist: Path) -> list[str]:
    """发行包必须包含运行框架、且不得包含任何个人数据目录。"""

    root = Path(dist)
    problems: list[str] = []
    for required in REQUIRED_RELEASE_FILES:
        if not (root / required).is_file():
            problems.append(f"缺少运行框架文件：{required}")
    for forbidden in FORBIDDEN_RELEASE_PATHS:
        if (root / forbidden).exists():
            problems.append(f"发行包含个人数据：{forbidden}")
    registry = root / "_internal/hushplayer/runtime/source_runtime/source_registry.json"
    if registry.is_file():
        try:
            document = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            document = {}
        sources = document.get("sources") if isinstance(document, dict) else None
        if isinstance(sources, list) and sources:
            problems.append(f"发行包注册表含 {len(sources)} 个音源条目")
    return problems


# --------------------------------------------------------------------------- CLI
def _print(result: ScanResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {
                "summary": result.summary(),
                "files": result.scanned_files,
                "findings": [item.as_dict() for item in result.findings],
                "blocked": len(result.blocked),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return
    seen: set[tuple[str, str, int, str]] = set()
    for finding in result.findings:
        key = (finding.rule, finding.path, finding.line, finding.detail)
        if key in seen:
            continue
        seen.add(key)
        print(finding.format())
    print(result.summary())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HushPlayer 敏感信息与发行包检查")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--staged", action="store_true", help="检查 git 暂存区")
    source.add_argument("--tracked", action="store_true", help="检查仓库跟踪的文件")
    source.add_argument("--worktree", action="store_true", help="检查跟踪文件 + 未忽略的未跟踪文件")
    source.add_argument("--path", type=Path, help="检查目录或文件")
    source.add_argument("--zip", type=Path, help="检查 zip 发行包")
    source.add_argument("--inno", type=Path, help="检查 installer.iss")
    parser.add_argument("--dist", type=Path, default=Path("packaging/out/HushPlayer"), help="与 --inno 搭配的发行目录")
    parser.add_argument("--release", action="store_true", help="额外检查发行布局（配合 --path/--zip）")
    parser.add_argument("--allowlist", type=Path, help="白名单文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true", help="把 medium 也视为失败")
    args = parser.parse_args(argv)

    allowlist = load_allowlist(args.allowlist)
    if args.staged:
        result = scan_staged(allowlist)
    elif args.tracked:
        result = scan_tracked(allowlist)
    elif args.worktree:
        result = scan_tracked(allowlist, include_untracked=True)
    elif args.path:
        result = scan_path(args.path, allowlist)
    elif args.zip:
        result = scan_zip(args.zip, allowlist)
    elif args.inno:
        result = scan_inno(args.inno, args.dist, allowlist)
    else:  # pragma: no cover - argparse 已保证
        parser.error("需要指定检查来源")

    problems: list[str] = []
    if args.release:
        if args.path:
            problems = release_layout_problems(args.path)
        else:
            problems = ["--release 需要配合 --path（发行目录）使用"]
        for problem in problems:
            result.findings.append(Finding(rule="release_layout", severity=HIGH, path=str(args.path), detail=problem))

    _print(result, as_json=args.json)
    if problems:
        for problem in problems:
            print(f"[BLOCK ] 发行布局：{problem}")
    failed = bool(result.blocked) or (args.strict and bool(result.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
