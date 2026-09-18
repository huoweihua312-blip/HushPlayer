# Immersive Background and Transparent Lyrics

Approved scope: render the current cover for artwork backgrounds and offer
theme-following, light, or dark lyric text specifically in transparent mode.
Preserve the transparent window mechanism, playback, lyrics synchronization,
the expanded reading area, and pre-existing artwork work.

## Implementation

- [x] Reproduce with real red/blue artwork and settings transaction tests.
- [x] Cache the resolved cover in ArtworkAtmosphere; render it with the existing
  image opacity/overlay controls. Retain fallback visuals and other modes.
- [x] Add immersive_transparent_lyrics_color with default theme; route it through
  existing settings preview/save/cancel and the page's canvas theme interface.
- [x] Verify artwork refresh, missing covers, mode switching, settings
  compatibility, UI screenshots, syntax, and UTF-8.

Delivery: review partial staging, then create one local task-only commit.
Do not push or include pre-existing edits.

No new dependencies or user-data migrations. No changes to shared lyric timing
or transparent native window flags. Rollback: revert only this task's commit.

## Changed Files and Interfaces

- `app/ui_v2/widgets/artwork_atmosphere.py`: ArtworkAtmosphere.set_track,
  _refresh_soft_artwork, set_blur, paintEvent, _paint_image. Reuse cached artwork,
  keep a contrast veil, and retain opacity, transparency, and overlay controls.
- `app/ui_v2/widgets/artwork_thumbnail.py`: artwork_pixmap_for_track gains a
  keyword-only fallback option, defaulting to the unchanged placeholder behavior.
  Only the atmosphere opts out so missing/corrupt images use its previous field.
- `app/ui_v2/models/immersive_lyrics_options.py`: transparent_lyrics_color.
- `app/ui_v2/adapters/legacy_settings_bridge.py`: default, normalization, validation.
- `app/ui_v2/widgets/immersive_settings_panel.py`: transparent lyrics color combo.
- `app/ui_v2/widgets/lyrics_quick_settings_panel.py`: snapshot loading and saving.
- `app/ui_v2/pages/immersive_lyrics_page.py`: background cover refresh signal,
  _apply_lyrics_theme, set_transparent_lyrics_color, options and panel routing.
- `app/ui_v2/shell/main_window.py`: only the new color in _apply_settings_values.
- `tests/test_ui_v2_immersive_background.py`: ten regression tests.
- `CHANGELOG.md`: two entries under unreleased.
- This plan and verification record.

The one new settings key is backward-compatible. Missing or invalid values
follow the theme. Unknown settings survive save/cancel. Library, playlist and
statistics formats, playback logic, lyric timing and window flags are unchanged.
Only lyric canvas colors are independently overridden, not the entire shell.

## Verification

Environment: existing project Python 3.12.14 with PySide6; no dependencies
installed. This does not establish compatibility with the Python 3.13 build.

Final focused suite: 20 passed.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ui_v2_immersive_background tests.test_ui_v2_settings.SettingsContractTests tests.test_ui_v2_immersive_lyrics.UiV2ImmersiveLyricsTests.test_transparency_chain_uses_existing_window_and_restores_normal_shell tests.test_ui_v2_immersive_lyrics.UiV2ImmersiveLyricsTests.test_formal_page_accepts_dark_light_and_transparent_without_rebuild tests.test_ui_v2_q5b1_real_interactions.Q5B1RealInteractionTests.test_custom_background_selection_activates_and_renders_image tests.test_ui_v2_q5b1_real_interactions.Q5B1RealInteractionTests.test_quick_settings_persists_each_background_visual_mode -v
```

Additional cover compatibility checks: 3 passed. The last test belongs to the
pre-existing user work and was run for compatibility only, not added to this commit.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_stability_optimizations.StabilityOptimizationTests.test_replacing_cover_at_same_path_refreshes_scaled_image tests.test_stability_optimizations.StabilityOptimizationTests.test_scaled_cover_hit_does_not_decode_an_evicted_source tests.test_real_track_artwork.RealTrackArtworkTests.test_worker_mapping_and_shared_renderer_receive_local_cover -v
```

Syntax: all changed Python files plus main.py passed py_compile. UTF-8 decoding
passed. Diff checks passed before staging; staged checks are required before
commit. Rendering tests were first observed failing before their fixes.

Seven Qt screenshots were generated with isolated mock playback/settings in
`build/ui-baseline/immersive-background-2026-09-18/`. Inspected light/dark artwork,
transparent light/dark text and settings layout. Transparent screenshots are
composited over black/white; they are not live Windows desktop captures.

## Manual Acceptance

1. Restart from the modified source. Existing packaged executables are unchanged.
2. Play a track with a cover; switch between artwork and gradient backgrounds.
   Try image opacity, blur, overlay, and background transparency.
3. Choose transparent background and light lyrics over a black desktop;
   choose dark lyrics over a white desktop. Save and reopen to check persistence.
4. Change the color and cancel to restore the saved choice.
5. Check lyric synchronization, pause/resume and fullscreen exit during playback.

Live audio and actual desktop composition still need manual acceptance.
On a mismatched page theme, non-lyric labels retain the existing theme; change
the page theme as well if the title or playback controls lack contrast.
