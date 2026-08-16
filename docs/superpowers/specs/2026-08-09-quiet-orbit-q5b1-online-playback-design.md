# Quiet Orbit Q5B-1 Online Playback Core

## Scope

Q5B-1 connects the Q5A remote-track discovery surface to the existing production playback controller. It adds asynchronous online media resolution, local/remote mixed queue playback, playback state propagation, and deterministic failure handling.

This phase does not add persistent audio caching, download UI, online lyrics, or a second playback stack.

## Ownership

`OnlineDiscoveryRuntime` owns one `OnlineMediaResolver`. The resolver owns request bookkeeping and uses the existing `OnlineSourceClient`; it does not own a `QMediaPlayer`, `QAudioOutput`, queue, widget, or page.

`ProductionPlaybackController` remains the only owner of the production `QMediaPlayer`, `QAudioOutput`, and `PlaybackQueue`. It accepts an optional resolver and keeps all local and remote playback commands on the same controller surface.

Pages and adapters do not own resolver requests. Closing a page cannot stop an active global playback resolve. Application shutdown closes the runtime and controller in the existing main-window ownership order.

## Track And Queue Contract

`PlaybackQueueItem` remains the single queue item abstraction. Local items carry a local file path. Remote items carry normalized source ID, remote track ID, stable identity, provider payload, and metadata. Temporary media URLs are held only in the active controller session and are never written to queue storage or `remote_tracks.json`.

The existing V2 `Track` value object gains only in-memory remote playback fields needed to reconstruct the provider request. The repository and JSON document structures remain unchanged.

When a remote stable identity is present, `MediaItem` preserves it for the queue item identity. When it is absent, the existing source plus remote track ID identity remains the fallback.

## Resolve Flow

1. A page emits the existing play request.
2. `PlaybackAdapter` builds or replaces one mixed queue and sends the selected identity to `ProductionPlaybackController`.
3. The controller advances its playback generation, selects the queue item, and enters `resolving` for a remote item.
4. `OnlineMediaResolver` validates source capability, cancels the previous request, and calls `OnlineSourceClient.resolve_playback()`.
5. The resolver emits a result only when request ID, generation, and stable identity are current.
6. The controller validates the returned descriptor and gives the URL to the existing media player.
7. Qt media status and playback signals move the shared adapter through loading, buffering, playing, paused, end-of-media, or error states.

An old result can never replace a newer local or remote request. A remote URL is a session descriptor, not an identity and not a persistent cache entry.

## Capability And Error Policy

The resolver reads capabilities from the existing unified source catalog. Search visibility alone does not grant playback. Disabled, unavailable, permission-denied, missing-media, invalid-URL, request-failed, unsupported-header, stale, and cancelled cases remain explicit outcomes.

User-facing errors stay concise and do not expose raw JSON, exception details, stream URLs, plugin payloads, cache keys, or request IDs. `StalledMedia` is represented as buffering and is not converted directly into a permanent failure.

## UI Synchronization

`PlaybackAdapter` remains the single V2 state bridge. PlayerBar, Now Playing, immersive controls, queue panel, search results, Favorites, and Playlist rows continue to consume its track, playing, position, duration, queue, favorite, and error signals. A semantic playback status is added for resolving, buffering, unavailable, error, paused, and playing presentation without changing approved shell geometry.

Metadata and artwork shown during resolving come from the Q5A track identity and payload. Later updates are accepted only for the same stable identity.

## Verification

Deterministic fake resolver/client tests cover:

- one controller, player, audio output, and queue;
- remote success, pause/resume, seek support, and unsupported seek;
- source unavailable, permission denied, invalid media, network error, and stalled media;
- rapid Remote A → Remote B → Remote C and remote/local stale-result protection;
- previous, next, shuffle, repeat, repeat-one, and mixed queue transitions;
- search, Favorites, Playlist, PlayerBar, Now Playing, Queue, metadata, and artwork synchronization;
- page close and application shutdown while resolving or playing;
- 100 rapid requests and 100 local/remote alternations without native crashes.

Automatic checks use deterministic fakes and do not require real network access. A real-source smoke test is optional and is recorded separately when the environment permits it.
