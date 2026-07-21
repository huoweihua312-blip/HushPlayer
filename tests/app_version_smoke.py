from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.version import (
    APP_NUMERIC_VERSION,
    APP_NUMERIC_VERSION_TEXT,
    APP_USER_AGENT,
    APP_VERSION,
    UPDATE_ARCHITECTURE,
    UPDATE_CHANNEL,
    UPDATE_MANIFEST_URL,
    UPDATE_MANIFEST_SOURCES,
    is_newer_numeric_version,
    parse_numeric_version,
)


def main() -> None:
    match = re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.(0|[1-9]\d*)",
        APP_VERSION,
    )
    assert match is not None
    assert len(APP_NUMERIC_VERSION) == 4
    assert all(
        isinstance(part, int) and not isinstance(part, bool) and part >= 0
        for part in APP_NUMERIC_VERSION
    )
    assert APP_NUMERIC_VERSION == tuple(int(part) for part in match.groups())
    assert APP_NUMERIC_VERSION_TEXT == ".".join(
        str(part) for part in APP_NUMERIC_VERSION
    )
    assert parse_numeric_version(APP_NUMERIC_VERSION_TEXT) == APP_NUMERIC_VERSION
    assert APP_VERSION in APP_USER_AGENT
    assert UPDATE_CHANNEL == "beta"
    assert UPDATE_ARCHITECTURE == "win-x64"
    assert UPDATE_MANIFEST_URL == (
        "https://api.gitcode.com/api/v5/repos/gcw_iPVB8B5g/"
        "HushPlayer-updates/raw/updates/beta/win-x64.json?ref=main"
    )
    assert UPDATE_MANIFEST_SOURCES == (
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

    assert is_newer_numeric_version("0.5.0.2", "0.5.0.1")
    assert is_newer_numeric_version("0.5.0.10", "0.5.0.2")
    assert not is_newer_numeric_version("0.5.0.2", "0.5.0.2")
    assert not is_newer_numeric_version("0.5.0.1", "0.5.0.2")
    assert parse_numeric_version((0, 5, 0, 10)) == (0, 5, 0, 10)

    for invalid in ("0.5.0", "0.5.0.-1", "0.5.0.beta2", "00.5.0.2", 2):
        try:
            parse_numeric_version(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid numeric version accepted: {invalid}")

    print("app version smoke: OK")


if __name__ == "__main__":
    main()
