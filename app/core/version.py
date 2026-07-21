from __future__ import annotations

import re
from collections.abc import Sequence


APP_NAME = "HushPlayer"
APP_VERSION = "0.5.0-beta.6"
APP_NUMERIC_VERSION = (0, 5, 0, 6)
UPDATE_CHANNEL = "beta"
UPDATE_ARCHITECTURE = "win-x64"
UPDATE_MANIFEST_SOURCES = (
    (
        "GitCode",
        "https://api.gitcode.com/api/v5/repos/gcw_iPVB8B5g/"
        "HushPlayer-updates/raw/updates/beta/win-x64.json?ref=main",
    ),
    (
        "GitHub",
        "https://raw.githubusercontent.com/huoweihua312-blip/"
        "HushPlayer/main/updates/beta/win-x64.json",
    ),
)
# Keep the legacy single-source import available for injected callers.
UPDATE_MANIFEST_URL = UPDATE_MANIFEST_SOURCES[0][1]
APP_USER_AGENT = f"{APP_NAME}/{APP_VERSION}"


_NUMERIC_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
)


def parse_numeric_version(value: str | Sequence[int]) -> tuple[int, int, int, int]:
    """Parse the four-part Windows version used for update ordering."""

    if isinstance(value, str):
        match = _NUMERIC_VERSION_PATTERN.fullmatch(value.strip())
        if match is None:
            raise ValueError("数字版本必须是四段非负整数，例如 0.5.0.2。")
        return tuple(int(part) for part in match.groups())

    if isinstance(value, (bytes, bytearray)):
        raise ValueError("数字版本必须包含四个非负整数。")
    try:
        parts = tuple(value)
    except TypeError as error:
        raise ValueError("数字版本必须包含四个非负整数。") from error
    if len(parts) != 4:
        raise ValueError("数字版本必须包含四个非负整数。")
    if any(
        isinstance(part, bool) or not isinstance(part, int) or part < 0
        for part in parts
    ):
        raise ValueError("数字版本必须包含四个非负整数。")
    return parts


def numeric_version_text(value: str | Sequence[int] = APP_NUMERIC_VERSION) -> str:
    return ".".join(str(part) for part in parse_numeric_version(value))


def is_newer_numeric_version(
    candidate: str | Sequence[int],
    current: str | Sequence[int] = APP_NUMERIC_VERSION,
) -> bool:
    return parse_numeric_version(candidate) > parse_numeric_version(current)


APP_NUMERIC_VERSION_TEXT = numeric_version_text()
