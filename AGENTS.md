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

The user is not a professional programmer.

After every implementation task, explain clearly:

- What changed
- Why it was changed this way
- Whether existing behavior changed
- How the user should test it
- What risks or unfinished items remain

Do not assume that a technically successful automated test is enough. The user may still need to perform manual UI and playback acceptance testing.

---

## Highest Priority

Stability comes first.

Do not break existing working features for the sake of:

- Optimization
- UI polish
- Refactoring
- Code style
- File splitting
- Architectural modernization
- Reducing line count

Changes should be:

- Small
- Focused
- Safe
- Easy to understand
- Easy to test
- Easy to revert

Prefer incremental improvements over large rewrites.

---

## Hard Rules

- Keep `app/ui/main_window.py` encoded as UTF-8.
- Do not turn Chinese text into mojibake such as `鏈壘鍒版瓕璇`.
- Follow the Backup Rules before modifying important files.
- Do not delete existing features.
- Do not rewrite the main window at large scale.
- Do not casually change the structure of:
  - `data/library.json`
  - `data/playlists.json`
  - `data/stats.json`
- `data/settings.json` may gain backward-compatible fields, but existing fields must be preserved.
- Do not add third-party dependencies unless there is a clear reason and the user has confirmed it.
- Do not add piracy-related music download interfaces.
- Do not scrape real audio URLs from NetEase Cloud Music, QQ Music, Kugou, or similar platforms.
- Do not bypass membership, DRM, login, regional, or copyright restrictions.
- Do not change core playback logic only for UI polish.
- Do not change the user's established interaction habits only for performance optimization.
- Do not perform large file-splitting refactors unless the user explicitly requests them.
- Do not silently recreate the project structure.
- Do not silently recreate or replace the virtual environment.
- Do not silently change the Python version.
- Do not remove compatibility behavior unless the user explicitly approves it.
- Do not claim that a test passed if it was not actually executed.
- Do not claim that a feature works only because the code compiles.
- Do not touch unrelated files to make the working tree look cleaner.
- Do not include unrelated user changes in a task commit.

---

## Allowed Room For Judgment

Codex may make reasonable, scoped improvements in these areas:

### UI Details

- Spacing
- Rounded corners
- Hover states
- Active states
- Font sizes
- Text hierarchy
- Card backgrounds
- Subtle borders
- Scrollbars
- Empty states
- Column sizing
- Elided text
- Tooltips
- Small accessibility improvements

### Windows 11 / Fluent Style

- Dark but not pure black
- Soft accent colors
- Card layout
- Clear active states
- Unified buttons
- Unified inputs
- Unified combo boxes
- Unified sliders
- Consistent spacing and hierarchy

### Small Performance Work

- Search debounce
- `setUpdatesEnabled(False)` during list refreshes
- `blockSignals(True)` during batch updates
- Cover scaling cache
- Avoiding duplicate refreshes
- Avoiding duplicate metadata reads
- Avoiding scans during page switches
- Lazy loading visible information
- In-memory caches that do not alter persistent data structures

### Small Code Cleanup

- Helper functions
- Clearer naming
- Reducing obvious duplication
- Necessary comments
- Small local extractions
- Removing unreachable code only when verified safe

### Better Error Handling

- Missing files
- Skipped scan failures
- Network failures without crashes
- JSON fallback behavior
- Invalid media files
- Unavailable optional resources
- Clear user-facing failure states

### Better User Experience

- Empty states
- Confirmation dialogs
- Non-blocking status prompts
- Operation-complete messages
- Clearer test instructions
- Clearer loading states
- Clearer disabled states

---

## High-Risk Areas

Do not directly modify the following areas unless:

1. The user explicitly asks for the change, or
2. Codex first explains the plan, risks, affected features, and rollback method.

High-risk areas include:

- Core playback logic
- `QMediaPlayer` initialization
- `QMediaPlayer` state management
- Playback context
- Previous / next song resolution
- Playback queue behavior
- Playback mode behavior
- Lyrics timeline parsing
- Lyrics synchronization
- Desktop floating lyrics core window behavior
- Immersive lyrics core window behavior
- Play queue data structure
- Liked songs data structure
- Custom playlist data structures
- `library.json` data structure
- `playlists.json` data structure
- `stats.json` data structure
- Multi-thread / Worker architecture
- Background scan architecture
- File path handling
- Packaging path handling
- PyInstaller packaging configuration
- Large-scale splitting of `main_window.py`
- Migration to SQLite or another database
- Network music download features
- Dependency upgrades that may affect PySide6 or media playback
- Replacing the current UI list architecture across the whole application
- Major signal / slot rewiring

If a high-risk change appears necessary, first explain:

- Why it needs to change
- What the risk is
- Which features may be affected
- Which files and functions would change
- How to roll back
- Whether it is recommended to do now
- Whether a lower-risk alternative exists

Do not begin a high-risk change until the user has approved the plan.

---

## Backup Rules

1. By default, the user manually backs up the entire HushPlayer project outside Codex.
2. If the user says at the start of a task that they have manually backed up, Codex must not run:
   - `Copy-Item`
   - `Compress-Archive`
   - Robocopy backup commands
   - Any other backup command
3. Do not request escalated permissions only to create a backup.
4. Do not stop low-risk tasks solely because automatic backup is unavailable.
5. If the user has not said they have backed up and the task modifies `main_window.py` or another important file, remind the user to manually back up first instead of requesting escalation.
6. Only attempt automatic backup when the user explicitly asks Codex to do it.
7. If automatic backup is rejected by the sandbox:
   - Stop the automatic backup attempt
   - Ask the user to back up manually
   - Do not repeatedly request escalated permissions
8. Do not place backup copies inside active source directories.
9. Do not include backup files in Git commits.
10. Do not overwrite an existing backup.

Suggested manual backup command:

```powershell
cd C:\Users\Administrator\Desktop
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Compress-Archive -Path HushPlayer -DestinationPath "HushPlayer_backup_$stamp.zip" -Force
```

---

## Standard Workflow

For every future implementation task:

1. Understand the task before making changes.
2. Inspect the current Git status.
3. Locate the relevant files, functions, signals, slots, and UI code.
4. Classify the task as:
   - Bug fix
   - UI polish
   - Performance optimization
   - New feature
   - Refactor
   - Maintenance
5. Determine whether the task touches any high-risk area.
6. If it is high risk:
   - Explain the proposed plan
   - Explain affected features
   - Explain risks
   - Explain rollback
   - Wait for user confirmation
7. If it is low risk:
   - Make the smallest relevant change
   - Avoid unrelated cleanup
8. Follow the Backup Rules before editing important files.
9. Preserve unrelated user changes already present in the working tree.
10. Review the resulting diff.
11. Run required syntax, diff, and task-specific checks.
12. If required checks pass:
   - Follow the Git Workflow
   - Create one focused local commit
13. If required checks fail:
   - Do not create a normal completion commit
   - Report the failure honestly
14. Provide a completion report containing:
   - Current branch
   - Files changed
   - Functions or classes changed
   - Why the change was made this way
   - Whether business logic changed
   - Whether persistent JSON structures changed
   - Tests and checks performed
   - How to test manually
   - Commit message
   - Commit hash
   - Final Git status
   - Remaining risks or unfinished items

---

## Git Workflow

Git commits are part of the standard task-completion workflow.

By default, Codex should automatically create a local Git commit after a task has been implemented and all required checks have passed.

Codex must not automatically push the commit to a remote repository.

### Before Editing

Before making any changes, run:

```powershell
git status --short
git branch --show-current
```

Then:

1. Inspect all existing modified, staged, deleted, and untracked files.
2. Treat all pre-existing uncommitted changes as user-owned.
3. Do not overwrite unrelated user changes.
4. Do not restore unrelated user changes.
5. Do not delete unrelated user changes.
6. Do not stage unrelated user changes.
7. Do not commit unrelated user changes.
8. Do not switch branches automatically.
9. Do not automatically run:
   - `git pull`
   - `git merge`
   - `git rebase`
   - `git reset`
10. Do not use Git commands merely to hide or discard an unexpected change.

If an important target file already contains uncommitted user changes:

- Inspect the diff carefully.
- Preserve those changes.
- Make only the required task changes.
- Do not assume the entire file belongs to the current task.
- Use precise staging or patch staging when necessary.

### During Implementation

While modifying files:

- Keep the task scope focused.
- Do not mix unrelated refactoring into the same task.
- Do not modify generated files unless required.
- Do not modify backup files.
- Do not modify caches.
- Do not modify log files.
- Do not stage files before reviewing their final diff.
- Do not use Git to undo changes unless Codex itself introduced them during the current task and the rollback is clearly safe.

### Diff Review

After implementation and before committing, run:

```powershell
git status --short
git diff --check
git diff
```

If files are already staged, also inspect:

```powershell
git diff --cached
```

Review for:

- Accidental unrelated edits
- Mojibake
- Broken indentation
- Trailing whitespace errors
- Debug output
- Temporary code
- Hard-coded test paths
- Unintended JSON changes
- Unintended dependency changes
- Backup or generated files
- Unexpected large deletions
- Unexpected line-ending conversions
- Accidental changes to protected logic

Do not continue to commit until the diff has been reviewed.

### Staging Rules

Stage only files intentionally modified for the current task.

Prefer explicit file staging:

```powershell
git add app/ui/main_window.py
```

For multiple known task files:

```powershell
git add app/ui/main_window.py app/widgets/example_widget.py
```

When only part of a modified file belongs to the task, use careful patch staging when practical:

```powershell
git add -p
```

Do not use the following by default:

```powershell
git add .
git add -A
git add --all
```

These broad staging commands may only be used when the user has explicitly confirmed that every working-tree change belongs to the current task.

Do not stage:

- Backup files
- Temporary files
- Cache directories
- Python bytecode
- Logs
- Generated build output
- Unrelated documentation changes
- Unrelated configuration changes
- Unrelated user edits
- Test artifacts that should not be versioned

After staging, run:

```powershell
git diff --cached --check
git diff --cached
```

Confirm that the staged diff contains only the intended task changes.

### Commit Conditions

Create a local commit only when:

- The requested implementation is complete
- Required checks have passed
- The staged diff has been reviewed
- The staged diff contains only task-related changes
- No known critical regression remains
- The commit is not empty

Do not create a normal completion commit when:

- Required syntax checks failed
- `git diff --check` failed
- The staged diff contains unrelated changes
- The implementation is incomplete
- The current result is known to break a protected feature
- There are unresolved merge conflicts
- No actual changes were made

If a task-specific runtime or UI test cannot be performed because of an environment limitation, Codex may still commit only when:

- Syntax and diff checks pass
- The limitation is clearly reported
- The unperformed test is not falsely described as passed
- The code change is reasonably safe and scoped
- No known failure is being hidden

### Commit Message Format

Use clear Conventional Commits-style messages.

Allowed common types include:

- `feat`
- `fix`
- `perf`
- `refactor`
- `style`
- `docs`
- `test`
- `build`
- `chore`

Examples:

```text
feat(ui): add sortable library table
fix(player): preserve playback context during browsing
perf(library): cache visible track durations
refactor(lyrics): simplify lyric rendering helpers
style(ui): refine library empty state
docs: update Codex working rules
chore: update project configuration
```

Choose the commit type and scope according to the actual change.

Commit messages should:

- Describe the real change
- Be concise
- Use an imperative or direct style
- Avoid exaggerated claims
- Avoid mentioning tests as the main change unless the commit is primarily about tests

Do not use vague commit messages such as:

```text
update
fix
changes
misc
done
完成
修改代码
更新文件
修复问题
```

Do not create multiple unnecessary commits for one small task.

Prefer one focused commit per completed task.

### Commit Verification

After creating the commit, run:

```powershell
git status --short
git log -1 --oneline
```

When useful, also run:

```powershell
git show --stat --oneline --summary HEAD
```

The completion report must include:

- Current branch
- Files changed
- Files staged and committed
- Files deliberately excluded
- Tests and checks performed
- Commit message
- Commit hash
- Final `git status --short`

If the final working tree is not clean, explain exactly why.

Do not claim that the working tree is clean unless `git status --short` confirms it.

### Remote Repository Rules

By default:

- Automatically create a local Git commit after successful completion.
- Do not automatically run `git push`.
- Do not automatically create a remote branch.
- Do not automatically change the upstream branch.
- Do not automatically open a pull request.
- Do not automatically merge a pull request.

Only push when the user explicitly asks.

Before pushing:

1. Run:

   ```powershell
   git branch --show-current
   git status --short
   git log -1 --oneline
   git remote -v
   ```

2. Confirm the current branch is the intended branch.
3. Confirm the latest commit is the intended commit.
4. Confirm there are no unexpected uncommitted changes.
5. Use a normal push without force.
6. Clearly report the remote and branch pushed.

Never run:

```powershell
git push --force
git push --force-with-lease
git reset --hard
git clean -fd
git clean -fdx
git checkout -- .
git restore .
```

Do not:

- Rewrite existing history
- Amend existing commits
- Squash commits
- Rebase user commits
- Delete branches
- Delete tags
- Change remotes
- Remove upstream configuration
- Force-update remote branches

unless the user explicitly requests the exact operation and understands the risk.

---

## Required Checks

After modifying Python files, run syntax checks for every modified Python file.

Also run task-specific checks appropriate to the change.

### Expected Project Directory

```powershell
cd C:\Users\Administrator\Desktop\HushPlayer
```

Before running commands, verify that the current directory is the HushPlayer project root.

### Python Interpreter Selection

Use the first working interpreter in this order:

1. Project virtual environment:

   ```powershell
   .\.venv\Scripts\python.exe
   ```

2. Windows Python launcher with Python 3.12:

   ```powershell
   py -3.12
   ```

3. Default Windows Python launcher:

   ```powershell
   py
   ```

4. System Python command:

   ```powershell
   python
   ```

First determine which interpreter is usable.

Do not repeatedly run a known-broken interpreter.

A simple interpreter check may use:

```powershell
.\.venv\Scripts\python.exe --version
```

or:

```powershell
py -3.12 --version
```

or:

```powershell
py --version
```

or:

```powershell
python --version
```

Use the first command that succeeds.

### Mandatory Python Syntax Checks

For changes involving the main application, run at least:

```powershell
<available-python> -m py_compile main.py
<available-python> -m py_compile app\ui\main_window.py
```

Replace `<available-python>` with the actual working interpreter command.

Examples:

```powershell
py -3.12 -m py_compile main.py
py -3.12 -m py_compile app\ui\main_window.py
```

If additional Python files were modified or created, run `py_compile` for each of them.

Do not use successful compilation with a different Python version to claim full runtime compatibility. Report the exact Python version used.

### Mandatory Git Checks

Before staging:

```powershell
git diff --check
```

After staging:

```powershell
git diff --cached --check
```

Before completing:

```powershell
git status --short
```

### UTF-8 Check

When `app/ui/main_window.py` or another file containing Chinese text is modified:

- Confirm the file remains UTF-8.
- Search the changed area for obvious mojibake.
- Do not silently convert the file to an incompatible encoding.
- Do not introduce a UTF-8 BOM unless the file already uses one and preserving it is necessary.

Where practical, use Python to verify UTF-8 decoding:

```powershell
<available-python> -c "from pathlib import Path; Path(r'app/ui/main_window.py').read_text(encoding='utf-8'); print('UTF-8 OK')"
```

### Task-Specific Checks

Depending on the task, also perform relevant checks such as:

- Importing the modified module
- Creating the main window in an offscreen environment
- Testing signals and slots
- Testing sort results
- Testing empty states
- Testing JSON fallback behavior
- Testing playlist filtering
- Testing search filtering
- Testing playback state preservation
- Testing visible-row duration loading
- Testing that a page switch does not trigger a scan
- Testing that protected methods remain unchanged
- Testing that the program exits with code `0`

Do not add unnecessary heavyweight testing infrastructure for a small change.

### Broken Virtual Environment Handling

If the project `.venv` is unavailable because its underlying Python installation no longer exists:

- Do not repeatedly retry it.
- Do not treat the task as failed solely because `.venv` is broken.
- Use another available interpreter for syntax checks.
- Clearly report:
  - That `.venv` is unavailable
  - Why it appears unavailable
  - Which interpreter was used instead
  - Which checks were and were not performed

If another interpreter successfully completes the required syntax checks:

- Treat the syntax checks as passed.
- Do not claim that the project virtual environment works.
- Do not recreate `.venv` unless the user explicitly requests it.
- Do not install dependencies globally without approval.

If no usable Python interpreter is available:

- Report that syntax checks could not be performed.
- Do not falsely claim success.
- Do not create a normal completion commit unless the user explicitly approves an unverified checkpoint.

### Dependency-Limited Testing

If a fallback interpreter does not contain required project dependencies:

- Syntax checks may still be performed with `py_compile`.
- Runtime imports or UI tests may fail because dependencies are absent.
- Report this as an environment limitation.
- Do not misrepresent a missing-dependency failure as a code regression.
- Do not install dependencies unless the user has approved it.

---

## UI Direction

HushPlayer should not feel like:

- NetEase Cloud Music
- QQ Music
- Kugou Music
- A social feed
- A content recommendation platform
- An advertisement-heavy music service

Target feeling:

- Windows 11
- Fluent Design
- Clean
- Quiet
- Dark-first
- Future light-theme support
- Rounded cards
- Soft hover states
- Clear hierarchy
- Lightweight
- Calm
- Not flashy
- Not overloaded

Acceptable references:

- Windows 11 Settings
- Windows 11 File Explorer
- The simple information hierarchy of Apple Music
- Lightweight local music-player workflows

Avoid:

- Feed-style music-platform layouts
- Advertisement-like landing pages
- Complex social-software patterns
- Excessive animation
- Heavy glassmorphism
- Excessive gradients
- Excessive glow
- Excessive blur
- Too many accent colors
- Too many simultaneous cards
- Controls that move because text length changes
- Decorative changes that reduce readability

---

## User Interaction Habits

Preserve these behaviors:

- Single-click a song:
  - Browse its information
  - Do not interrupt current playback
- Double-click a song:
  - Play the song
- Right-click:
  - Show relevant song actions
- Selected song and currently playing song must be visually distinguishable.
- Current playback highlighting must remain visible when appropriate.
- Clicking `音乐库` returns to all songs.
- Clicking `我喜欢` shows only liked songs.
- Clicking a custom playlist shows only that playlist.
- Search should be smooth and preferably debounced.
- Switching pages should not trigger scans.
- Scanning music folders should not block the UI.
- New songs discovered by scans should default to the pending-import list instead of silently polluting the library.
- Desktop lyrics and immersive lyrics are important features and must not be casually broken.
- The bottom playback area should not shift because of different song-title lengths.
- Long song titles, artist names, and album names should not break the layout.
- Empty music library, playlist, and search views should show formal empty states rather than demo songs.
- Sorting should not unexpectedly change playback.
- Browsing another song should not silently replace the playback context.

---

## Performance Principles

When optimizing performance, prioritize:

- Do not rebuild lists on every page switch.
- Use `setUpdatesEnabled(False)` during batch list refreshes.
- Use `blockSignals(True)` during batch list refreshes.
- Debounce search input.
- Avoid duplicate JSON reads.
- Avoid duplicate metadata reads.
- Avoid scanning music folders during page switches.
- Avoid polishing every lyric label on every lyric-position update.
- Cache scaled cover pixmaps.
- Cache metadata in memory when appropriate.
- Load expensive visible information lazily when appropriate.
- If a background scan finds no new content, do not force a full list rebuild.
- Avoid creating large numbers of child widgets for large song lists when a delegate or model-based drawing approach is more efficient.
- Preserve selection and playback indicators during refreshes.
- Do not optimize by changing established interaction behavior.
- Measure performance before making broad performance claims.

Avoid jumping directly to:

- Database migration
- Full refactor
- Full file split
- Thread-pool rewrite
- Whole-application Model/View rewrite
- Worker architecture replacement
- Replacing all widgets at once
- Large caching systems
- Premature persistence-format changes

These are larger engineering projects and require confirmation first.

---

## Theme Principles

If theme switching is implemented later, it should support:

- Follow system
- Dark mode
- Light mode

Theme colors should gradually become variables rather than being hard-coded everywhere.

Theme work should:

- Preserve readability
- Preserve contrast
- Avoid pure black as the only background
- Avoid pure white text everywhere
- Use restrained accent colors
- Keep destructive actions visually distinct
- Keep selected and currently playing states distinguishable

Desktop lyrics and immersive lyrics may keep independent settings and do not have to follow the main-window theme strictly.

Do not implement a large theme architecture without first proposing the scope.

---

## Network And Music Download Boundaries

Allowed:

- Online lyrics matching
- Online cover matching
- Online song metadata matching
- Searching legal open-music sources
- Opening official purchase pages
- Opening official platform pages
- Scanning the user's own local music files
- Scanning folders synced from:
  - Baidu Netdisk
  - Quark
  - OneDrive
  - NAS
  - SMB
  - WebDAV
  - rclone
  - Similar user-controlled storage tools
- Caching legally retrieved lyrics or metadata when permitted
- Graceful network failure handling

Not allowed:

- Pirated music interfaces
- Bypassing membership restrictions
- Bypassing DRM
- Bypassing login restrictions
- Bypassing regional restrictions
- Downloading copyrighted music from:
  - Apple Music
  - NetEase Cloud Music
  - QQ Music
  - Kugou
  - Similar commercial platforms
- Bulk scraping copyrighted songs
- Extracting protected audio streams
- Circumventing platform APIs or access controls

When adding online integrations:

- Prefer documented, legal APIs.
- Respect rate limits.
- Handle network failures without crashing.
- Do not block the main UI thread.
- Do not silently upload the user's library.
- Do not send local file paths to third parties unless necessary and approved.
- Do not add a new dependency without user confirmation.

---

## About `main_window.py`

Most current code is concentrated in:

```text
app/ui/main_window.py
```

Do not split it aggressively in the short term.

If cleanup is necessary, use gradual, low-risk extraction in this preferred order:

1. Extract pure UI helper widgets.
2. Extract dialogs.
3. Extract independent windows.
4. Extract delegate or model helpers that have clear boundaries.
5. Extract service-style helpers last.

Any large split must:

- Be proposed first
- Explain the target files
- Explain dependency boundaries
- Explain affected features
- Include a rollback plan
- Be approved by the user
- Be completed incrementally

Do not silently perform a broad architecture rewrite.

---

## Current Functional Areas To Protect

Do not break:

- Application startup
- Playback
- Play / pause
- Previous song
- Next song
- Progress seeking
- Volume control
- Playback state persistence
- Music library
- Library persistence
- Song metadata
- Song duration display
- Library sorting
- Search
- Liked songs / `我喜欢`
- Bottom favorite button
- Custom playlists
- Adding songs to playlists
- Removing songs from playlists
- Play queue
- Playlist page
- Playback context
- Lyrics page
- Local `.lrc` lyrics
- Lyrics timeline
- Lyrics synchronization
- Desktop floating lyrics
- Immersive lyrics
- Online lyrics
- Online metadata matching
- Lyrics binding
- Cover display
- Cover cache
- Settings page
- Music-folder scanning
- Pending import
- Music inbox flow
- Single-click browsing
- Double-click playback
- Current-playing visual state
- Selected-song visual state
- Formal empty states
- UTF-8 Chinese text
- Existing JSON compatibility

When modifying one functional area, verify that closely related protected areas still behave correctly.

---

## Data Compatibility Rules

Persistent user data must be treated as valuable.

Before changing persistent data behavior:

- Inspect the current structure.
- Preserve unknown existing fields.
- Preserve backward compatibility.
- Avoid rewriting an entire file only to add one field.
- Avoid changing IDs or path formats.
- Avoid changing timestamp formats without approval.
- Avoid changing song identity rules without approval.
- Avoid automatically deleting records that reference temporarily unavailable files.

For settings:

- New fields should have safe defaults.
- Missing fields should not crash the application.
- Old settings files should remain readable.

For library and playlist data:

- Do not silently migrate structures.
- Do not silently normalize or rewrite all entries.
- Do not remove unknown fields.
- Do not merge duplicate songs using a new rule without user approval.

Any migration must include:

- A backup recommendation
- Versioning or detection logic
- Backward-compatibility explanation
- Rollback instructions
- Explicit user approval

---

## Completion Report Format

At the end of every implementation task, provide a clear report using this structure:

### Result

State whether the task was:

- Completed
- Partially completed
- Blocked
- Reverted

### Files Changed

List every changed file.

### Code Areas Changed

List the important:

- Functions
- Classes
- Signals
- Slots
- UI components
- Data fields

### Behavior Changes

Explain:

- What the user can now do
- What behavior changed
- What behavior intentionally stayed the same

### Protected Areas

State whether any of these changed:

- Core playback logic
- Playback context
- Queue logic
- Lyrics logic
- Persistent JSON structures
- Dependencies

### Checks Performed

List the exact commands and their results.

Do not write “tests passed” without listing what was run.

### Git

Report:

- Branch
- Commit message
- Commit hash
- Files included in the commit
- Files excluded from the commit
- Final `git status --short`

### Manual Testing

Give clear, numbered steps the user can perform.

### Remaining Risks

Explain any:

- Environment limitation
- Untested runtime path
- Known edge case
- Deferred work
- Broken virtual environment
- Dependency limitation

Keep the report understandable to a non-professional programmer.

---

## Final Safety Principle

When uncertain, choose the smaller change.

When a change could affect playback, lyrics, queues, playlists, persistent data, packaging, or user files:

- Stop
- Inspect
- Explain
- Protect existing behavior
- Prefer a reversible solution

A stable partial improvement is better than a broad risky rewrite.