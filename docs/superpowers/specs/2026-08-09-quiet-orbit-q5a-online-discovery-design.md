# Quiet Orbit Q5A Online Discovery Design

## Goal

Add a production-capable Quiet Orbit online discovery page without adding an
online playback path. The page searches enabled legal sources, presents remote
tracks with explicit source identity, supports artwork and metadata enrichment,
and lets users favorite or add remote tracks to playlists through the existing
storage semantics.

Q1 through Q4 shell, content, settings, player-bar, immersive-player, queue,
and lyrics behavior remain unchanged.

## Constraints

- Reuse `OnlineSourceClient`, `SourceRegistry`/runner protocol,
  `UnifiedSearchService`, `RemoteTrackStore`, `OnlineArtworkService`, and
  `PlaylistMembership`.
- Do not modify the source protocol, JSONL contract, plugin host, source
  permission model, or remote identity algorithm.
- Do not create a second source registry, remote-track store, player,
  playback queue, or settings store.
- Do not send an online URL to `PlaybackAdapter`, `ProductionPlaybackController`,
  `PlaybackQueue`, or `QMediaPlayer`.
- Keep asynchronous ownership explicit and follow the Q3 shutdown rules.
- Automated tests use deterministic fakes; real network smoke is optional.
- The result is intentionally left uncommitted for manual visual acceptance.

## Architecture

### Runtime service boundary

`UiV2RuntimeServices` receives one online discovery service bundle. The bundle
owns the single `OnlineSourceClient`, `UnifiedSearchService`, and
`OnlineArtworkService` used by the V2 shell. It receives the already injected
`RemoteTrackStore`; it never constructs another store or registry.

The bundle exposes a small `OnlineDiscoveryBridge` for user actions. The page
does not write JSON or mutate Repository objects. The bridge persists remote
track records through `RemoteTrackStore` and updates playlist membership using
the existing compatibility semantics. It emits success/failure results so the
page can update the corresponding row without rebuilding the result model.

Mock mode injects deterministic fake source/search/action services. Production
mode uses the formal services and the same adapter contract.

### Search and generation

The existing `CustomTitleBar.search_text_changed` path remains the global query
source:

`CustomTitleBar -> ContentRouter.set_global_query -> page.adapter.set_query`

The online page keeps one visual result surface and does not create a second
independent shell search input. Search requests are delegated to
`UnifiedSearchService`. Its debounce, source selection, generation counter,
request cancellation, cache, and stale-result checks remain authoritative.

The adapter maps each accepted raw result to `OnlineTrack`. Updates are
accepted only when both generation and query match the current page state.

### Remote identity

Every remote row uses `RemoteTrackStore.stable_id_for_track()` with the formal
`source_id` plus source-provided remote ID (or the existing documented
metadata fallback). The stable ID is the row key, collection key, artwork key,
metadata key, favorite key, and playlist membership key. Title/artist text is
never used as a cross-source identity.

### Artwork and metadata

`OnlineArtworkService` remains the only artwork network/cache service. Its
request bookkeeping is extended to support bounded keyed row requests, with
generation and stable identity attached to every result. A cover response
updates only its matching row and never triggers a full result rebuild.

Metadata enrichment uses the existing `OnlineSourceClient.get_metadata()`
request. The adapter tracks request ID, generation, and stable identity; a
late response is ignored after a new query or page shutdown.

### User actions

- Favorite toggles call the bridge and update the row only after the formal
  persistence action succeeds.
- Add-to-playlist calls the bridge with the remote stable ID and preserves
  `PlaylistMembership.REMOTE` semantics.
- Track info uses the sanitized remote record and optional metadata response.
- Play/double-click/context-menu play shows a clear unavailable status for
  online-only rows. It never emits a successful playback request and never
  touches the production playback controller.
- Download is not exposed as a Q5A action; Q5B can address download policy
  separately.

### Lifecycle

The runtime bundle is owned by the V2 `MainWindow`. On close, the page first
stops accepting updates, then the adapter cancels its generation-bound work,
the artwork service cancels keyed requests, `UnifiedSearchService.shutdown()`
cancels debounce and active source requests, and `OnlineSourceClient.stop()`
waits for the source process according to its existing owner contract. No
callback may mutate a destroyed page.

## UI and responsive behavior

The existing Quiet Orbit online page, result delegate, source badges, toolbar,
context menu, and theme tokens are reused. Mock-only copy is replaced with
source-neutral production copy. Local and remote result semantics remain
visually distinct through source labels and availability states.

Light and dark themes use the existing Q1/Q2 token system. At 900, 1200, and
1600 pixels, columns use the existing responsive policy, long text is elided,
and the player bar remains the only bottom player surface. Online status and
source popups remain within the page geometry.

## Verification plan

Deterministic tests cover:

- source catalog and source status states;
- search debounce, generation changes, cancellation, and stale results;
- 20/100/200 result sets without full-model rebuilds;
- duplicate titles across sources and stable remote identity;
- keyed artwork and metadata success/failure after query changes;
- favorite and remote playlist membership persistence;
- unavailable online playback boundary;
- context menu behavior and removal of download playback actions;
- global query routing, Light/Dark themes, 900/1200/1600 responsive layout;
- page close and repeated startup/shutdown lifecycle pressure.

After automated checks, native Windows Qt screenshots are generated for the
specified Q5A state matrix. The worktree remains uncommitted, unpushed, and
unmerged for manual visual acceptance.
