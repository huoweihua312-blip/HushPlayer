# Real Track Artwork

Date: 2026-09-15
Status: Scope approved; written specification awaiting review.

## Scope

Display genuine artwork for local songs and online search results using
the existing Track artwork fields and shared artwork renderer. Keep the
existing placeholder only when artwork is absent, unreadable, or invalid.
Do not substitute unrelated photographs or generated album artwork.

## Findings

- RealLibraryAdapter.map_snapshot currently sets local artwork_path to
  None, even when the record contains local_cover_path or cover_path.
- artwork_pixmap_for_track already supports artwork_data and artwork_path.
- OnlineArtworkService.request_many emits cached images synchronously.
  OnlineAdapter assigns _artwork_generation after that method returns,
  so a cache hit can be rejected as belonging to an older request.
- Online artwork requests currently use a shared cancelling batch and
  cap requests at 32. Regression checks must cover cancellation and
  results beyond the first batch, not just first-page network success.
- The project already uses mutagen for audio metadata.

## Approach

Prefer repairing the existing artwork pipeline over introducing a new
provider or replacing the application's rendering architecture.

An alternative is online metadata matching for every local song. Defer
this because it introduces privacy decisions, network traffic, and
incorrect-album matches. A complete artwork framework replacement is
also unnecessary for this scope.

### Local Artwork

Resolve in order: a valid existing cover reference, embedded front-cover
metadata, then recognized images in the audio file's directory.
Recognized adjacent images are cover, folder, and front with jpg, jpeg,
or png extensions, matched case-insensitively. Do not select an arbitrary
image in the directory.

Reuse the installed metadata library. Cover discovery must run outside
painting and the GUI thread, preferably within the existing library
snapshot worker; do not replace its architecture. Validate image content
and enforce a bounded image-size policy. Failures affect only the cover,
not library loading. Reuse resolved results during normal page changes.

Use existing Track fields. Do not modify audio files, persistent library
records, identities, or path conventions. Do not upload local metadata
or file paths. A missing audio file must not remove its library entry.

### Online Artwork

Use only artwork URLs supplied by existing source metadata. Correct
request-generation handling so cached and network results behave alike.
Preserve stale-result rejection after a new search or shutdown.

Ensure library warm-up requests cannot silently cancel active search
artwork without recovery. Cover visible search results beyond the first
32 using bounded requests, without unbounded simultaneous downloads.
Keep changes within artwork request scheduling, not source or playback
resolution.

Reuse the existing image cache and shared renderer. Network failures,
invalid images, and unavailable covers retain the placeholder without
blocking playback. Apply images by stable song identity so delayed
responses cannot replace another song's artwork.

### Surfaces

Verify song lists, online results, bottom playback artwork, and existing
song-detail/lyrics artwork surfaces use the corresponding Track artwork.
Update only necessary presentation projections; do not change playback
selection, playback context, queue order, or lyrics timing.

## Planned Code Boundaries

- app/ui_v2/adapters/real_library_adapter.py: project local artwork.
- A focused local artwork helper under app/services, if needed.
- app/services/online_artwork_service.py and
  app/ui_v2/adapters/online_adapter.py: cache and request lifecycle fixes.
- app/ui_v2/shell/main_window.py only if required for artwork propagation
  or isolation of its library warm-up requests.
- Focused regression tests and CHANGELOG.md under its unreleased section
  when implementation is complete; no release-version changes.

Do not change dependency manifests, playback controllers, worker
architecture, persistent JSON structures, or unrelated user edits.
If a broader change proves necessary, request approval first.

## Verification

- Test valid saved covers, embedded covers, adjacent covers, priority,
  missing files, corrupt images, and no-artwork fallback.
- Test first cached response, network response, stale search response,
  shared-service request interaction, and more than 32 search results.
- Verify artwork identity consistency across list and current-song
  projections without changing selected or playing identity.
- Run Python syntax checks for every changed Python file plus main.py
  and the formal main window. Report the actual interpreter version.
- Run relevant existing library, online discovery, artwork, and playback
  interaction regression tests; do not install missing dependencies.
- Check UTF-8 and the final staged diff.
- Manual acceptance: browse and play local songs with each cover type;
  search online, scroll past 32 results, repeat a cached search, switch
  searches quickly, and check current-song artwork while browsing another
  song. Confirm play/pause, previous/next, favorites, and lyrics still work.

## Risks And Rollback

Embedded-image extraction can increase library load time and memory.
Keep reads off the GUI thread and avoid repeated decoding or unlimited
image retention. Some files and online sources genuinely have no cover;
this feature cannot guarantee artwork for every song.

The user is responsible for manual backup before important-file edits.
No automatic backup is authorized. Keep the implementation in a focused
local commit so it can be reverted explicitly without changing user data.
Do not push remotely.

## Existing User Changes

Exclude app/services/online_source_importer.py,
source_runtime/package.json, source_runtime/package-lock.json, and
docs/ui-v2-b2-component-map.zip from this task's commits.
