# Quiet Orbit Real Actions and Playlist CRUD

## Scope

This pass closes visible placeholder actions in the approved Q1-Q5B1 shell and
enables ordinary playlist management in real mode. It does not add Q5B2 online
audio behavior, change online-source protocols, or alter playback/thread
ownership.

## Visible Action Surface

- TopBar keeps Settings, theme switching, navigation history, search, and native
  window controls. The disabled View Options ellipsis is removed from the
  layout.
- PlayerBar keeps Queue, Lyrics, volume/mute, and existing transport actions.
  The unused More ellipsis is removed from the layout.
- Sidebar replaces More Playlists with a small Fluent Add action in the
  `歌单` section header. `我喜欢` remains a fixed system route. Ordinary
  playlists are rendered through the existing scroll area without a three-item
  cap.
- Other visible no-op actions in the Browse collection headers and generic
  collection hero are removed. Existing Artist, Lyrics, Queue, Settings, and
  Playlist menus remain because they have real signal paths.

## Playlist Persistence

Real-mode playlist mutations reuse the already-owned
`OnlineDiscoveryRuntime.bridge`, which writes the existing `playlists.json`
through an atomic temporary-file replacement. No second playlist store is
created. The bridge preserves unknown playlist fields and uses
`PlaylistMembership` for the existing `songs`, `remoteSongs`, `members`, and
`membershipVersion` contract.

The UI `PlaylistAdapter` keeps source-snapshot read-only semantics separate from
playlist mutation capability. In real mode, the library and playback
projections remain read-only where they were before, while approved playlist
operations are enabled through the bridge:

- create ordinary playlist;
- rename ordinary playlist;
- delete ordinary playlist;
- add/remove visible local or remote members.

The fixed `liked` record cannot be created, renamed, or deleted. A failed file
mutation leaves the in-memory adapter unchanged. Deleting the active playlist
routes to the library without touching the current playback adapter or queue.

## Quiet Orbit Dialogs

Create and rename use a small themed `QDialog` with a `QLineEdit`; blank names
are rejected in the dialog and adapter. Delete uses a themed confirmation
dialog with the exact safety copy: `删除歌单不会删除音乐库中的歌曲。` No
system `QInputDialog`, `QMessageBox`, or empty menu is introduced.

## Verification

The pass adds focused tests for action removal, playlist creation validation,
real-file preservation, fixed-liked protection, route safety, playback
continuity, and sidebar/card synchronization. Native Windows Qt screenshots
cover the final TopBar, Sidebar create action, create dialog, created playlist,
delete confirmation, fixed liked route, PlayerBar, and a contact sheet.
