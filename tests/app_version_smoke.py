from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.version import (
    APP_NUMERIC_VERSION,
    APP_NUMERIC_VERSION_TEXT,
    APP_VERSION,
    UPDATE_ARCHITECTURE,
    UPDATE_CHANNEL,
    UPDATE_MANIFEST_URL,
    is_newer_numeric_version,
    parse_numeric_version,
)


def main() -> None:
    assert APP_VERSION == "0.5.0-beta.4"
    assert APP_NUMERIC_VERSION == (0, 5, 0, 4)
    assert APP_NUMERIC_VERSION_TEXT == "0.5.0.4"
    assert UPDATE_CHANNEL == "beta"
    assert UPDATE_ARCHITECTURE == "win-x64"
    assert UPDATE_MANIFEST_URL == (
        "https://raw.githubusercontent.com/huoweihua312-blip/"
        "HushPlayer/main/updates/beta/win-x64.json"
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
