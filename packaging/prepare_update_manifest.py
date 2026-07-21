from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.version import (
    APP_NUMERIC_VERSION,
    APP_NUMERIC_VERSION_TEXT,
    APP_VERSION,
    UPDATE_ARCHITECTURE,
    UPDATE_CHANNEL,
    numeric_version_text,
    parse_numeric_version,
)


_RELEASE_HEADING_PATTERN = re.compile(
    r"^##\s+(?P<version>"
    r"(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)-(?P<channel>[a-z][a-z0-9-]*)\."
    r"(?P<sequence>0|[1-9]\d*)"
    r")\s+(?:—|-)\s+(?P<release_date>\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)
_MANIFEST_VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)-(?P<channel>[a-z][a-z0-9-]*)\."
    r"(?P<sequence>0|[1-9]\d*)$"
)
_SUMMARY_HEADING_PATTERN = re.compile(r"^### 在线更新摘要\s*$", re.MULTILINE)
_SECTION_HEADING_PATTERN = re.compile(r"^#{2,3}\s+", re.MULTILINE)
_BULLET_PATTERN = re.compile(r"^[-*]\s+(?P<note>.+?)\s*$")
_UNRELEASED_HEADING_PATTERN = re.compile(r"^## 未发布\s*$", re.MULTILINE)

MAX_NOTES_PER_RELEASE = 50
MAX_NOTE_LENGTH = 1000


class ChangelogValidationError(ValueError):
    """Raised when a formal changelog chapter cannot produce update notes."""


@dataclass(frozen=True, slots=True)
class ChangelogRelease:
    version: str
    numeric_version: tuple[int, int, int, int]
    numeric_version_text: str
    channel: str
    release_date: str
    notes: tuple[str, ...]

    def to_manifest_history(self) -> dict[str, object]:
        return {
            "version": self.version,
            "numeric_version": self.numeric_version_text,
            "release_date": self.release_date,
            "notes": list(self.notes),
        }


def _parse_summary_notes(version: str, content: str) -> tuple[str, ...]:
    notes: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bullet = _BULLET_PATTERN.fullmatch(line)
        if bullet is None:
            raise ChangelogValidationError(
                f"{version} 的在线更新摘要只能包含 Markdown 项目列表。"
            )
        note = bullet.group("note").strip()
        if not note or len(note) > MAX_NOTE_LENGTH:
            raise ChangelogValidationError(
                f"{version} 的在线更新摘要包含空白或过长内容。"
            )
        notes.append(note)
    if not notes or len(notes) > MAX_NOTES_PER_RELEASE:
        raise ChangelogValidationError(
            f"{version} 的在线更新摘要必须包含 1 至 "
            f"{MAX_NOTES_PER_RELEASE} 项内容。"
        )
    return tuple(notes)


def parse_changelog_releases(path: str | Path) -> tuple[ChangelogRelease, ...]:
    """Read formal release summaries without exposing Markdown parsing at runtime."""

    changelog_path = Path(path)
    try:
        text = changelog_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ChangelogValidationError(
            f"无法读取 CHANGELOG：{changelog_path}"
        ) from error
    if not _UNRELEASED_HEADING_PATTERN.search(text):
        raise ChangelogValidationError("CHANGELOG 缺少 ## 未发布 章节。")

    headings = list(_RELEASE_HEADING_PATTERN.finditer(text))
    if not headings:
        raise ChangelogValidationError("CHANGELOG 不包含可发布的正式版本章节。")

    releases: list[ChangelogRelease] = []
    seen_numeric_versions: set[tuple[int, int, int, int]] = set()
    for index, heading in enumerate(headings):
        version = heading.group("version")
        release_date = heading.group("release_date")
        try:
            if date.fromisoformat(release_date).isoformat() != release_date:
                raise ValueError(release_date)
        except ValueError as error:
            raise ChangelogValidationError(
                f"{version} 的发布日期无效：{release_date}。"
            ) from error

        numeric_version = parse_numeric_version(
            ".".join(
                (
                    heading.group("major"),
                    heading.group("minor"),
                    heading.group("patch"),
                    heading.group("sequence"),
                )
            )
        )
        if numeric_version in seen_numeric_versions:
            raise ChangelogValidationError(
                f"CHANGELOG 包含重复数字版本：{numeric_version_text(numeric_version)}。"
            )
        seen_numeric_versions.add(numeric_version)

        section_end = (
            headings[index + 1].start()
            if index + 1 < len(headings)
            else len(text)
        )
        section_text = text[heading.end() : section_end]
        summary_heading = _SUMMARY_HEADING_PATTERN.search(section_text)
        if summary_heading is None:
            raise ChangelogValidationError(
                f"{version} 缺少 ### 在线更新摘要。"
            )
        summary_end_match = _SECTION_HEADING_PATTERN.search(
            section_text,
            summary_heading.end(),
        )
        summary_end = (
            summary_end_match.start()
            if summary_end_match is not None
            else len(section_text)
        )
        notes = _parse_summary_notes(
            version,
            section_text[summary_heading.end() : summary_end],
        )
        releases.append(
            ChangelogRelease(
                version=version,
                numeric_version=numeric_version,
                numeric_version_text=numeric_version_text(numeric_version),
                channel=heading.group("channel"),
                release_date=release_date,
                notes=notes,
            )
        )
    return tuple(sorted(releases, key=lambda item: item.numeric_version))


def _target_release(
    document: dict[str, Any],
    releases: tuple[ChangelogRelease, ...],
) -> ChangelogRelease:
    version = str(document.get("version") or "").strip()
    try:
        numeric_version = parse_numeric_version(
            str(document.get("numeric_version") or "")
        )
    except ValueError as error:
        raise ChangelogValidationError(
            "更新清单的 numeric_version 无效，无法同步 CHANGELOG。"
        ) from error
    for release in releases:
        if release.version == version and release.numeric_version == numeric_version:
            return release
    raise ChangelogValidationError(
        "更新清单目标版本未在 CHANGELOG 正式章节中找到："
        f"{version} / {numeric_version_text(numeric_version)}。"
    )


def build_release_history(
    document: dict[str, Any],
    releases: tuple[ChangelogRelease, ...],
) -> list[dict[str, object]]:
    """Build ordered, same-channel history through the manifest target release."""

    target = _target_release(document, releases)
    return [
        release.to_manifest_history()
        for release in releases
        if release.channel == target.channel
        and release.numeric_version <= target.numeric_version
    ]


def synchronize_manifest_document(
    document: dict[str, Any],
    releases: tuple[ChangelogRelease, ...],
) -> dict[str, Any]:
    """Return a manifest whose notes and history are generated from CHANGELOG."""

    target = _target_release(document, releases)
    synchronized = dict(document)
    synchronized["release_notes"] = list(target.notes)
    synchronized["release_history"] = build_release_history(document, releases)
    return synchronized


def validate_manifest_document(
    document: dict[str, Any],
    releases: tuple[ChangelogRelease, ...],
) -> None:
    expected = synchronize_manifest_document(document, releases)
    if document.get("release_notes") != expected["release_notes"]:
        raise ChangelogValidationError(
            "更新清单 release_notes 与 CHANGELOG 目标版本在线更新摘要不一致。"
        )
    if document.get("release_history") != expected["release_history"]:
        raise ChangelogValidationError(
            "更新清单 release_history 未由 CHANGELOG 正式版本章节生成。"
        )


def _manifest_release_identity(
    document: dict[str, Any],
) -> tuple[tuple[int, int, int, int], str]:
    version = str(document.get("version") or "").strip()
    match = _MANIFEST_VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ChangelogValidationError("更新清单 version 格式无效。")
    try:
        numeric_version = parse_numeric_version(
            str(document.get("numeric_version") or "")
        )
    except ValueError as error:
        raise ChangelogValidationError("更新清单 numeric_version 无效。") from error
    label_numeric_version = (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        int(match.group("sequence")),
    )
    if numeric_version != label_numeric_version:
        raise ChangelogValidationError(
            "更新清单 version 与 numeric_version 不一致。"
        )
    return numeric_version, match.group("channel")


def _validate_manifest_platform(
    document: dict[str, Any],
) -> tuple[tuple[int, int, int, int], str]:
    numeric_version, channel = _manifest_release_identity(document)
    if channel != UPDATE_CHANNEL or document.get("channel") != UPDATE_CHANNEL:
        raise ChangelogValidationError(
            "更新清单 channel 与当前应用不一致。"
        )
    if document.get("architecture") != UPDATE_ARCHITECTURE:
        raise ChangelogValidationError(
            "更新清单 architecture 与当前应用不一致。"
        )
    return numeric_version, channel


def validate_published_manifest_for_source(document: dict[str, Any]) -> None:
    """Allow only the current or immediately previous beta during source prep."""

    numeric_version, _ = _validate_manifest_platform(document)
    if numeric_version[:3] != APP_NUMERIC_VERSION[:3]:
        raise ChangelogValidationError(
            "更新清单与当前应用的 major/minor/patch 不一致。"
        )
    if numeric_version > APP_NUMERIC_VERSION:
        raise ChangelogValidationError("更新清单版本不得高于当前源码版本。")
    sequence_lag = APP_NUMERIC_VERSION[3] - numeric_version[3]
    if sequence_lag > 1:
        raise ChangelogValidationError(
            "更新清单版本最多只能落后当前源码一个 beta 序号。"
        )


def validate_manifest_matches_application(document: dict[str, Any]) -> None:
    numeric_version, _ = _validate_manifest_platform(document)
    if document.get("version") != APP_VERSION:
        raise ChangelogValidationError(
            "更新清单 version 与 app/core/version.py 不一致。"
        )
    if numeric_version != APP_NUMERIC_VERSION or (
        document.get("numeric_version") != APP_NUMERIC_VERSION_TEXT
    ):
        raise ChangelogValidationError(
            "更新清单 numeric_version 与 app/core/version.py 不一致。"
        )


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChangelogValidationError(f"无法读取更新清单：{path}") from error
    if not isinstance(document, dict):
        raise ChangelogValidationError("更新清单顶层必须是 JSON 对象。")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 CHANGELOG 同步或校验 HushPlayer 更新清单。"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--changelog",
        type=Path,
        default=PROJECT_ROOT / "CHANGELOG.md",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="将目标版本摘要和有序 release_history 写入更新清单。",
    )
    arguments = parser.parse_args()

    document = _load_manifest(arguments.manifest)
    releases = parse_changelog_releases(arguments.changelog)
    if arguments.write:
        document = synchronize_manifest_document(document, releases)
        arguments.manifest.write_text(
            json.dumps(document, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
        print(
            "update manifest synchronized: "
            f"{arguments.manifest} ({len(document['release_history'])} releases)"
        )
        return
    validate_manifest_document(document, releases)
    validate_manifest_matches_application(document)
    print(
        "update manifest validation: OK "
        f"({arguments.manifest}, {len(document['release_history'])} releases)"
    )


if __name__ == "__main__":
    main()
