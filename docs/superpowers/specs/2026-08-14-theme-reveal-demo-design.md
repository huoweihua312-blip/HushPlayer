# Theme reveal transition demo

## Purpose

Provide the HushPlayer theme transition: the
new theme is revealed from the upper-right theme toggle button and expands
across the window. This behavior is enabled in the normal application.

## Design

- Capture the current window once immediately before a manual theme toggle.
- Apply the existing target theme underneath the captured image.
- Display the captured image in a mouse-transparent overlay.
- Fade an expanding circular hole through a 110px feathered radial gradient,
  centered on the visible sun/moon theme toggle button, so the target theme
  appears to softly radiate from the user's action.
- Use a 1200 ms ease-out transition and remove the overlay when finished.
- Start the overlay before the synchronous theme persistence pass, then defer
  applying the new theme by one render frame so the reveal responds immediately;
  start the radius animation only after the new theme is ready so no reveal
  frames are skipped.
- Disable the theme button during the short transition to avoid overlapping
  reveals.
- Keep theme persistence and the existing target theme colors unchanged.

## Scope and safety

This demo does not change theme colors, settings schemas, playback, lyrics,
window geometry, packaging, or update behavior. The overlay is temporary and
is not persisted. Offscreen tests can exercise the underlying theme switch
without requiring the animation to render.

## Acceptance criteria

1. A manual theme toggle starts at the theme button and
   reveals the target theme across the whole window.
2. The target theme, player state, route, and shell widget identities remain
   unchanged after the animation.
3. The overlay ignores mouse input and is removed after completion.
4. The normal application uses the complete reveal without an environment flag.
