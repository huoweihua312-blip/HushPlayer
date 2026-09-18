# Settings Wheel and Refresh Fix

**Goal:** Prevent accidental wheel edits in settings and remove redundant theme
refreshes while preserving immediate preview and persistence.

**Approved scope:** The user approved closed dropdowns scrolling the settings
page, normal popup/keyboard selection, and skipping unchanged global styling.
No playback, timeline, window lifecycle, JSON schema, dependency, or user-owned
main-window changes.

**Implementation:** Use the existing settings variant of `ThemedComboBox` to
ignore wheel events while closed, allowing the containing scroll area to handle
them. Keep toolbar variants unchanged. In `ImmersiveLyricsPage`, persist local
settings through the existing bridge with `apply=False`; retain global apply
when the appearance setting changes. Skip unchanged theme/background setters
in local preview, including the save-failure path.

## Steps

- [x] Add regression tests in `tests/test_ui_v2_settings_input.py` for wheel
  scrolling, focused dropdowns, popup selection, keyboard selection, and toolbar
  compatibility. Add immersive tests for immediate persistence without repeated
  theme/background apply, genuine theme changes, and failed-save preview.
- [x] Run the new tests before editing production code and confirm failures
  reproduce accidental selection and redundant refreshes.
- [x] Modify `settings_control_factory.py` and `immersive_lyrics_page.py` only
  within the approved input/settings paths, then rerun the regressions.
- [x] Run adjacent settings, background, transparency, retry, close, and theme
  tests. Repeat the 20-blur-edit timing/profile harness against isolated mock
  settings and compare with the measured 11.806-second baseline.
- [x] Update the unreleased changelog, check Python 3.12.14 syntax and UTF-8,
  and review the task diff.

Delivery: stage only this task's files and changelog hunk, review the staged
diff, and create one focused local commit. Do not push or include existing user
changes.

## Acceptance

Wheel scrolling must move the page without changing a closed settings combo,
even when it retains focus. Expanded lists and keyboard choice must still work.
Local edits must remain saved immediately, survive reopening/restarting, retain
unknown settings, and preserve playback state. Failed saves must still retain
the draft and allow retry. Theme and transparency changes must still reach the
main window; ordinary slider edits must not invoke full-window restyling.

## Implementation Notes

The reset action updates the existing shared options object before applying
defaults, so removing the global save callback does not detach the main window's
runtime options. Failure-only preview still propagates actual appearance
changes, but local failures do not trigger whole-window theme refresh.

The same isolated offscreen mock-page profile (20 consecutive blur adjustments,
with synchronous persistence and no event-loop painting between edits) measured
11.806 seconds before and 0.058 seconds after. Both runs performed 20 saves.
These timings characterize the settings update path, not native desktop frame
rate or real-audio acceptance.

Verification: 26 input/immersive/background tests and 22 adjacent settings,
theme, custom-background, persistence, popup, and transparency tests passed.
The two modified production Python files and both test files compile alongside
`main.py` and `app/ui_v2/shell/main_window.py` using Python 3.12.14. UTF-8 and
whitespace checks passed. No packaged EXE rebuild or native real-audio acceptance
was performed.
