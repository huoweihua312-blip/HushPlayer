# Lyrics Reading Height Implementation Plan

**Goal:** Use more vertical space for immersive lyrics in tall windows.

**Approved design:** Keep small-window layout, typography, cover, transport,
lyrics rendering and playback behavior unchanged. Expand only the page-owned
lyrics viewport; do not increase the renderer's context radius.

**Architecture:** Adjust `ImmersiveLyricsPage._apply_responsive_layout` only.
Above 900 logical pixels, add 1.5 times the excess height to the existing reading
height, capped to leave 32 pixels above and below inside the content area.
Compact layouts retain their existing allocation.

**User refinement:** Extend farther than the first preview, allow the lyrics
area to exceed the cover height, and keep only the necessary vertical margins
in tall windows.

**Tech stack:** Existing Python/PySide6 and unittest; no new dependencies.

## Constraints

- Preserve all pre-existing user edits, especially the artwork work.
- Do not modify the main window, playback, synchronization, persistent formats,
  dependencies, or shared lyrics canvas.
- Stage only this task's changelog line, not the existing artwork entries.

## Steps

- [x] Add regression coverage in `tests/test_ui_v2_immersive_convergence.py`
  for tall-window space, visible rows, small-window restoration, unchanged
  playback state, and separation from the controls.
- [x] Run the added tests before implementation and confirm the height
  regression fails against the existing 48-percent allocation.
- [x] Add the bounded extra height to the page layout.
- [x] Run immersive layout and interaction tests, syntax checks,
  UTF-8 checks, and diff checks. Inspect before/after Qt screenshots.
- [x] Add the verified user-facing change to `CHANGELOG.md` under Unreleased.

Commit policy: one focused local commit after staged review; do not push.

## Verification

Python 3.12.14 from the existing project environment.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ui_v2_immersive_convergence tests.test_ui_v2_b2_immersive tests.test_ui_v2_immersive_lyrics tests.test_ui_v2_q4_immersive_contract -v
.\.venv\Scripts\python.exe -m py_compile main.py app\ui_v2\shell\main_window.py app\ui_v2\pages\immersive_lyrics_page.py tests\test_ui_v2_immersive_convergence.py
git diff --check
git diff --cached --check
```

- Final expanded layout: 45 tests passed; syntax and UTF-8 checks passed.
- Original allocation failed the new tall-window regression. The first,
  smaller expansion also failed the user's revised space requirement.
- Dark/light Qt captures at 1200x800, 1450x900, 1920x1080, and 2560x1440:
  cover and transport geometry unchanged; small-window metrics unchanged.
- At 1920x1080, canvas height increased from 518 to 788 and complete fixture
  rows from 5 to 7. At 2560x1440, height increased from 691 to 1148 and rows
  from 7 to 9. Actual line count depends on wrapping and translations.
- Local screenshots and metrics: `build/ui-baseline/lyrics-height-2026-09-18/`;
  `before` is the original layout, `after` the first preview, and `expanded`
  the final layout. These generated artifacts are excluded from the commit.
- An additional run including `tests.test_ui_v2_q4_immersive_lifecycle` on the
  first preview was stopped during lengthy repeated-cycle checks. Some
  lifecycle tests completed, but that entire run is not reported as passed.
- No live audio or native desktop acceptance performed; manual testing is
  still needed. The old EXE has not been rebuilt.
