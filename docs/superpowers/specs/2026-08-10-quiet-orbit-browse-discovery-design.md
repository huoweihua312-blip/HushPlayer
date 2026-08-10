# Quiet Orbit Browse Discovery

## Goal

Turn Browse into a useful start-listening surface backed by the existing local
collection, persisted remote tracks, playlists, recent plays, and enabled
online sources.

## Product Rules

- Recent Added includes local tracks and online tracks that the user has
  explicitly saved through Favorites or a playlist.
- Recommendations are derived from playlist membership, Favorites, and recent
  plays. The reason is visible as lightweight supporting text.
- When there is a useful seed, the Browse adapter may query the existing online
  source client for additional recommendations. Results remain temporary until
  the user plays, favorites, or adds them to a playlist.
- Saving an online recommendation goes through the existing
  `OnlineDiscoveryBridge` and keeps `source_id + remote track identity`.
- Browse never creates a second playback controller, playback queue, settings
  store, source registry, plugin host, or persistent recommendation database.
- A failed or unavailable online result is shown with its existing availability
  semantics; Browse never presents it as a successful playable local track.

## Architecture

`BrowseDiscoveryAdapter` is a small presentation adapter. It reads the shared
`LibraryCollectionAdapter` and `PlaylistAdapter`, and uses the existing
`OnlineAdapter` for online-track actions. In real mode it uses a second
`UnifiedSearchService` coordinator over the same `OnlineSourceClient`; it does
not create another runner or source registry. The coordinator has its own
generation and is shut down before the shared online runtime.

The adapter emits one snapshot for the three existing sections:

- `recent_added`: persisted local and remote tracks sorted by `added_at`.
- `recommended`: local and remote saved tracks ranked by playlist/recent
  affinity, followed by current online recommendation results.
- `recent_played`: the shared recent-play projection.

Online recommendation requests use a seed artist/title from the user's
playlist or recent-play history. A newer Browse refresh invalidates the older
generation. Temporary online results are registered only for action routing;
they are not persisted until the user explicitly saves them.

## Interaction

- The recommended heading exposes a real Refresh action.
- Empty online recommendation state exposes the existing Online Search route.
- Right-clicking a Browse card provides Play, Favorite, and Add to Playlist
  where the underlying shared adapters support the action.
- Existing single-click browsing and double-click/play behavior remain intact.

## Compatibility and Risk Control

- Existing playlist JSON, library JSON, stats JSON, remote-track JSON, source
  contracts, RemoteTrack identity, ProductionPlaybackController, and
  PlaybackQueue semantics are unchanged.
- Mock tests use deterministic adapter results and do not contact the network.
- Real online requests are bounded by the existing source-client timeouts and
  are cancelled through the recommendation search service on refresh/shutdown.
