# Online Track State Consistency

## Scope

This is a focused Q5B stability and presentation correction. It keeps the existing
single `ProductionPlaybackController`, `PlaybackAdapter`, `PlaybackQueue`,
`OnlineMediaResolver`, `RemoteTrackStore`, and Q5A/Q5B UI surfaces. It does not
change the source protocol, plugin host, persistent JSON schema, online queue
architecture, or the approved visual language.

## State Contract

Remote tracks use explicit runtime states instead of treating every non-local
track as unavailable:

- `unknown` / `not_resolved`: no resolve attempt has produced a result; no error icon
- `resolving`: a resolve request is active; use a quiet resolving indicator
- `playable`: media has resolved or playback has reached a usable state
- `source_unavailable`: the source capability/runtime explicitly rejects playback
- `resolve_failed`: this track's resolve attempt failed
- `permission_denied`: the source rejected access for this request
- `playback_error`: the resolved media failed during playback

Legacy `available` values remain accepted as playable aliases. Persisted remote
records without runtime state are projected as `not_resolved`; transient runtime
state is not written to `remote_tracks.json`.

`TrackAvailabilityPresentation` remains the only user-facing availability
presenter. It distinguishes resolving from confirmed error states, and it keeps
availability independent from artist/album metadata and favorite state.

## Data Flow

`ProductionPlaybackController` emits an identity-aware remote state event for
resolve start, resolve success, source/permission failures, and media errors.
`PlaybackAdapter` forwards it without creating another playback owner.
`OnlineAdapter` consumes the event by stable remote identity and updates the
online result, the shared in-memory library collection, and the current playback
track. It also accepts non-empty metadata/artwork and duration enrichment while
preserving existing non-empty fields.

The shared collection's runtime update path is UI-only even in real/read-only
mode. It broadcasts `track_updated`, allowing Favorites, Playlist, TrackTable,
PlayerBar, Queue, Now Playing, and Lyrics identity surfaces to refresh from the
same immutable `Track` value. Stale identity or stale generation results are
ignored.

## Error Boundaries

One track's resolve failure updates only that stable identity. Source-wide
`source_unavailable` is used only when the source capability or runtime makes
that conclusion explicit. Unknown, not-resolved, and resolving tracks never
render as unavailable.

## Verification

Tests cover initial state, all runtime states, successful and failed resolve,
metadata/duration enrichment, empty enrichment preservation, stale results,
Remote A -> B -> A, local/remote transitions, favorite independence, and all
shared presentation surfaces. Native Windows Qt screenshots cover unknown,
resolving, playable, playing, unavailable, Favorites, PlayerBar, Queue, and
Now Playing states.
