"""Development launcher for the opt-in UI V2 shell."""

from __future__ import annotations

import sys

from app.ui_v2.adapters.real_library_adapter import ui_v2_data_mode
from app.ui_v2.startup import run_ui_v2_application


def main() -> int:
    return run_ui_v2_application(
        sys.argv,
        data_mode=ui_v2_data_mode(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
