# HushPlayer Codex Working Rules

## Project Context

HushPlayer is a Windows local music player built with Python and PySide6.

Current product direction:

- Local music playback
- Music library management
- Lyrics display
- Desktop floating lyrics
- Immersive lyrics / secondary-screen lyrics
- Cover and lyrics matching
- Windows 11 / Fluent Design style UI
- Stable, lightweight, quiet, and non-intrusive experience

The user is not a professional programmer. After every implementation task, explain clearly what changed and how to test it.

## Highest Priority

Stability comes first.

Do not break existing working features for the sake of optimization, UI polish, or refactoring. Changes should be small, safe, and easy to revert.

## Hard Rules

- Keep `app/ui/main_window.py` encoded as UTF-8.
- Do not turn Chinese text into mojibake such as `鏈壘鍒版瓕璇`.
- Follow the Backup Rules below before modifying important files.
- Do not delete existing features.
- Do not rewrite the main window at large scale.
- Do not casually change the structure of `data/library.json`, `data/playlists.json`, or `data/stats.json`.
- `data/settings.json` may gain backward-compatible fields, but existing fields must be preserved.
- Do not add third-party dependencies unless there is a clear reason and the user has confirmed it.
- Do not add piracy-related music download interfaces.
- Do not scrape real audio URLs from NetEase Cloud Music, QQ Music, Kugou, or similar platforms.
- Do not bypass membership, DRM, login, or copyright restrictions.
- Do not change core playback logic just for UI polish.
- Do not change the user's established interaction habits just for performance optimization.
- Do not perform large file-splitting refactors unless the user explicitly requests it.

## Allowed Room For Judgment

Codex may make reasonable, scoped improvements in these areas:

- UI details: spacing, rounded corners, hover states, active states, font sizes, text hierarchy, card backgrounds, subtle borders, scrollbars, and empty states.
- Windows 11 / Fluent style: dark but not pure black, soft accent colors, card layout, clear active state, unified buttons, inputs, combo boxes, and sliders.
- Small performance work: search debounce, `setUpdatesEnabled(False)` during list refreshes, `blockSignals`, cover scaling cache, avoiding duplicate refreshes, and avoiding scans during page switches.
- Small code cleanup: helper functions, clearer naming, reducing obvious duplication, and necessary comments.
- Better error handling: missing files, skipped scan failures, network failures without crashes, JSON fallback behavior.
- Better user experience: empty states, confirmation dialogs, non-blocking status prompts, operation-complete messages, and clearer test instructions.

## High-Risk Areas

Do not directly modify these areas unless the user explicitly asks, or unless Codex first explains the plan and waits for confirmation:

- Core playback logic
- `QMediaPlayer` initialization and state management
- Lyrics timeline parsing
- Desktop floating lyrics core window behavior
- Immersive lyrics core window behavior
- Play queue data structure
- Liked songs and custom playlist data structures
- `library.json` data structure
- Multi-thread / Worker architecture
- File path and packaging path handling
- PyInstaller packaging configuration
- Large-scale splitting of `main_window.py`
- Migration to SQLite or another database
- Network music download features

If a high-risk area appears necessary, first explain:

- Why it needs to change
- What the risk is
- Which features may be affected
- How to roll back
- Whether it is recommended to do now

## Backup Rules

1. By default, the user manually backs up the entire HushPlayer project outside Codex.
2. If the user says at the start of a task that they have manually backed up, Codex must not run `Copy-Item`, `Compress-Archive`, or any other backup command.
3. Do not request escalated permissions just to create a backup.
4. Do not stop low-risk tasks solely because automatic backup is unavailable.
5. If the user has not said they have backed up and the task modifies `main_window.py` or another important file, remind the user to manually back up first instead of requesting escalation to back up automatically.
6. Only attempt automatic backup when the user explicitly asks Codex to do it.
7. If automatic backup is rejected by the sandbox, stop and ask the user to manually back up; do not repeatedly request escalated permissions.

Suggested manual backup command:

```powershell
cd C:\Users\Administrator\Desktop
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Compress-Archive -Path HushPlayer -DestinationPath "HushPlayer_backup_$stamp.zip" -Force
```

## Standard Workflow
For every future task:

1. Understand the task before making changes.
2. Locate the relevant functions and UI code.
3. Classify the task as bug fix, UI polish, performance optimization, new feature, or refactor.
4. If it is high risk, propose a plan first instead of editing immediately.
5. If it is low risk, make the smallest relevant change.
6. Follow the Backup Rules before editing important files.
7. Run syntax checks after Python changes.
8. Report:
   - Which files changed
   - Which functions changed
   - Why the change was made this way
   - Whether business logic changed
   - How to test
   - Any remaining risk

## Required Checks

After modifying Python files, run at least:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py
.\.venv\Scripts\python.exe -m py_compile app\ui\main_window.py
```

If new Python files are added, run `py_compile` for them too.

The expected project directory is:

```powershell
cd C:\Users\Administrator\Desktop\HushPlayer
```

## UI Direction

HushPlayer should not feel like NetEase Cloud Music, QQ Music, or a complex social/music feed platform.

Target feeling:

- Windows 11 / Fluent Design
- Clean
- Quiet
- Dark-first
- Light theme support in the future
- Rounded cards
- Soft hover states
- Clear hierarchy
- Not flashy
- Not overloaded

Acceptable references:

- Windows 11 Settings
- Windows 11 File Explorer
- The simple information hierarchy of Apple Music
- Lightweight local music player workflows

Avoid:

- Feed-style music platform layouts
- Advertisement-like landing pages
- Complex social software patterns
- Excessive animation
- Heavy glassmorphism

## User Interaction Habits

Preserve these behaviors:

- Single-click a song: browse information; do not necessarily play.
- Double-click a song: play.
- Selected song and currently playing song must be visually distinguishable.
- Clicking `音乐库` returns to all songs.
- Clicking `我喜欢` shows only liked songs.
- Search should be smooth, preferably debounced.
- Switching pages should not trigger scans.
- Scanning music folders should not block the UI.
- New songs discovered by scans should default to the pending-import list, not pollute the library.
- Desktop lyrics and immersive lyrics are important features and must not be casually broken.

## Performance Principles

When optimizing performance, prioritize:

- Do not rebuild lists on every page switch.
- Use `setUpdatesEnabled(False)` during batch list refresh.
- Use `blockSignals(True)` during batch list refresh.
- Debounce search input.
- Avoid duplicate JSON reads.
- Avoid duplicate metadata reads.
- Avoid scanning music folders during page switches.
- Avoid polishing all lyric labels on every lyric position update.
- Cache scaled cover pixmaps.
- If a background scan finds no new content, do not force a full list rebuild.

Avoid jumping directly to:

- Database migration
- Full refactor
- Full file split
- Thread pool rewrite
- Model/View rewrite for the whole list

Those are larger engineering projects and require confirmation first.

## Theme Principles

If theme switching is implemented later, it should support:

- Follow system
- Dark mode
- Light mode

Theme colors should become variables instead of being hard-coded everywhere.

Desktop lyrics and immersive lyrics may keep independent settings and do not have to follow the main window theme strictly.

## Network And Music Download Boundaries

Allowed:

- Online lyrics matching
- Online cover matching
- Online song metadata matching
- Searching legal open music sources
- Opening official purchase or platform pages
- Scanning the user's own local music files
- Scanning local folders synced from Baidu Netdisk, Quark, OneDrive, NAS, SMB, WebDAV, rclone, or similar tools

Not allowed:

- Pirated music interfaces
- Scraping real playback URLs
- Bypassing membership restrictions
- Bypassing DRM
- Downloading copyrighted music from Apple Music, NetEase Cloud Music, QQ Music, Kugou, or similar platforms
- Bulk scraping copyrighted songs

## About `main_window.py`

Most current code is concentrated in `app/ui/main_window.py`.

Do not split it aggressively in the short term.

If cleanup is needed, only do gradual, low-risk extraction:

1. Extract pure UI helper widgets.
2. Extract dialogs.
3. Extract independent windows.
4. Extract service-style helpers last.

Any large split must be proposed first and should not be done silently.

## Current Functional Areas To Protect

Do not break:

- Playback
- Music library
- Search
- Liked songs / `我喜欢`
- Bottom favorite button
- Custom playlists
- Play queue / playlist page
- Lyrics page
- Desktop floating lyrics
- Immersive lyrics
- Online lyrics
- Online metadata matching
- Lyrics binding
- Cover cache
- Settings page
- Music folder scanning
- Pending import / music inbox flow

