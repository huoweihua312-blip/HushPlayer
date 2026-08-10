# Quiet Orbit UX Closure

## Goal

Close the user-facing gaps found during the read-only UX acceptance without changing the Q1-Q4 shell, playback ownership, online source protocol, RemoteTrack identity, or Q3 thread lifecycle.

## Scope

- Keep the TopBar as the single production search input, while exposing the active query and search scope on Online Search.
- Make idle, searching, empty, partial-failure, and total-failure states distinct and actionable.
- Add a stable source-management action and reuse the existing SourceRegistry URL validation, staging, security scan, install, reload, enable, update, and remove semantics.
- Make global Settings and Lyrics Quick Settings select custom background mode when a file is chosen, expose a reset action, and keep long paths compact with tooltips.
- Surface online playback availability beside the PlayerBar identity without mixing it into artist/album metadata.
- Improve playlist operation discoverability without changing playlist JSON or the liked-playlist rules.

## Boundaries

No new playback controller, queue, settings store, source protocol, plugin-host contract, RemoteTrack identity rule, or thread owner. No new network behavior beyond the existing URL source-management flow. Existing Q5B1 working-tree changes remain user-owned and are not reverted.

## Design

Online Search will show a compact query context row: the query, the current scope, and source health summary. The page will retain one input source in the shell and will not create a second search state. State copy will point directly to the next valid action.

Online Sources will add a Quiet Orbit import action backed by the existing registry manager. URL input will accept one `.js` or `.json` URL per line, require the existing content-policy confirmation, and report validation, duplicate, scan, install, reload, and failure outcomes in the page. Source rows will keep enable, retry, update, rename, and remove semantics from the existing manager where available.

Background settings will use one canonical path display helper. Choosing a valid image sets the formal mode to `custom`; clearing the path restores `cover` unless the user explicitly chooses another mode. The stored keys remain unchanged.

PlayerBar will use `TrackAvailabilityPresentation` for a subdued inline state label and tooltip. Artist/album metadata remains generated only by `format_track_metadata`.

## Acceptance

- A user can tell what keyword is being searched and why no results are shown.
- A user can reach source management from Online Search and add/remove a source through the existing safety boundary.
- Choosing a custom background works from both settings entry points and can be reset.
- Online unavailable/resolving status is visible without corrupting metadata.
- Existing Q5B1 deterministic tests and local playback regressions remain green.
- Light/Dark and 900/1200/1600 layouts remain stable.
