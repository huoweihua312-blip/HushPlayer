"""Pre-commit guard: keep AGENTS.md in sync with the fragile parts of the app.

Rationale: AGENTS.md is injected into every session, but nothing forced it to be
*updated*. This script only looks at staged paths, so it is cheap and boring.
Commit messages containing ``[no-agents]`` bypass the check.
"""

from __future__ import annotations

import subprocess
import sys

HOT_PATHS = (
    "packaging/installer.iss",
    "hushplayer/ui/widgets/popup.py",
    "hushplayer/ui/widgets/tracklist.py",
    "hushplayer/ui/widgets/playerbar.py",
    "hushplayer/ui/widgets/queue_panel.py",
    "hushplayer/ui/widgets/settings_widgets.py",
    "hushplayer/ui/pages/settings.py",
    "hushplayer/core/theme.py",
    "hushplayer/core/display.py",
    "hushplayer/app.py",
)

DOC = "AGENTS.md"


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()]


def main() -> int:
    files = staged_files()
    touched_hot = [path for path in files if path in HOT_PATHS]
    if not touched_hot:
        return 0
    if DOC in files:
        return 0

    message = (
        subprocess.run(
            ["git", "-c", "core.pager=cat", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
        ).stdout
        or ""
    )
    if "[no-agents]" in message:
        return 0

    print("commit blocked: AGENTS.md must be updated together with these fragile modules:")
    for path in touched_hot:
        print(f"  - {path}")
    print()
    print("Add a line to section 9 of AGENTS.md (plus any new rule/pitfall),")
    print("`git add AGENTS.md`, then commit again. Use [no-agents] in the message to bypass.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
