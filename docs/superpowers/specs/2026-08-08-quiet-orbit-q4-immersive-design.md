# Quiet Orbit Q4 Immersive Player Design

## Goal

Q4 extends the approved Q1-Q3 desktop shell with one immersive presentation for Now Playing and Lyrics. It preserves the existing production playback controller, playback adapter, queue, lyric state, settings bridge, and shell geometry semantics. The immersive view is a MainWindow child presentation, not a second window and not a second player.

## Boundaries

Included:

- Now Playing identity, artwork, transport, progress, favorite, queue, lyrics, volume, shuffle, and repeat controls.
- Lyrics canvas with current-line state, previous/next context, translation when real data exists, manual scroll, return-to-current, and loading/empty/failed/instrumental states.
- Queue Floating Panel and Lyrics Quick Settings Floating Panel.
- Light/Dark themes and responsive 900/1200/1600 layouts.
- Playback and queue synchronization through existing adapters.
- Owned timers, stable panel instances, close/resize/theme/track-transition lifecycle coverage.

Excluded:

- New online search, online playback, online lyric source, download, import, packaging, release, or default-entry changes.
- New QMediaPlayer, QAudioOutput, PlaybackQueue, PlaybackAdapter, Settings store, or routing system.
- Changes to approved Q1-Q3 content, settings, or shell contracts except the minimum compatibility wiring required for immersive presentation.

## Architecture

`ImmersivePlayerShell` remains the cached semantic host and `ImmersiveLyricsPage` remains the compatibility implementation surface. Its stable child structure is:

```text
ImmersivePlayerShell
`-- ImmersiveLyricsPage
    |-- BackgroundLayer / ReadabilityOverlay
    |-- ImmersiveHeader
    |-- ContentHost
    |   |-- NowPlayingPage
    |   `-- LyricsCanvasV2 + LyricsStateView
    |-- ImmersiveControls
    `-- OverlayHost
        |-- QueueFloatingPanel
        `-- LyricsQuickSettingsFloatingPanel
```

The host receives the existing `PlaybackAdapter` and `LyricsAdapter`. All visible playback controls call adapter methods; no component stores an independent play, position, queue, or volume state. The queue panel renders the adapter-owned queue and changes only its own geometry. The quick settings panel edits the existing settings snapshot/session and never creates a second persistence path.

## Presentation and Geometry

Entering immersive presentation hides Sidebar, TopBar, and the global PlayerBar while retaining the MainWindow and its playback services. Exit restores those shell elements without changing track, position, queue, or lyric model. The overlay host is a fixed child covering the page; panels are stable children of that host and are only shown, hidden, moved, or resized.

Panel widths follow the approved floating-panel ranges:

- 1600: 360-410px
- 1200: 340-380px
- 900: 310-340px

Panels remain right-floated, internally vertically scrollable, and clear of window controls. They never become a drawer or bottom sheet and never participate in the content layout calculation.

Queue and Quick Settings are mutually exclusive. Escape closes the visible panel first, then exits immersive presentation. Full Settings Overlay remains higher priority than either quick panel.

## State and Lifecycle

The existing adapter signals are the source of truth for track, playing, position, duration, volume, mute, favorite, shuffle, repeat, queue, errors, lyric document, lyric phase, active line, and display options. Track changes update identity, artwork, queue current row, lyric state, and header together.

Auto-hide uses a `QTimer` owned by the immersive host. Panel visibility, keyboard focus, slider interaction, and open panels suppress hiding. The timer is stopped during host deactivation and destruction. No panel is reparented during resize, no row widgets are rebuilt for state changes, and no popup or lambda is allowed to outlive its owner.

## Visual Direction

The approved Quiet Orbit floating-panel prototype is authoritative. The implementation uses deep green/blue surfaces, low-saturation light surfaces, warm-gold state accents, Segoe UI typography, visible focus rings, no system blue selection, no pure-black rows, and no purple or high-glow effects. The only motion is restrained 150-300ms state continuity where the existing Qt implementation supports it without blocking the GUI.

## Verification Plan

1. Compile every modified Python file.
2. Run Q4 contract tests for route, shared adapter state, panels, settings transaction, lyric states, and geometry invariants.
3. Run 100-cycle enter/exit, Now Playing/Lyrics, Queue open/close, Quick Settings open/cancel, resize, and track transition stress loops.
4. Run shutdown stress with each panel and active playback.
5. Run the established UI V2, Q1, Q2, Q3, repository, legacy, playback, queue, audio-device, and responsive regressions.
6. Capture native Windows Qt screenshots at 900, 1200, and 1600 in both themes, then inspect the contact sheet manually.

The Q4 branch remains uncommitted and unpushed until visual acceptance is complete.
