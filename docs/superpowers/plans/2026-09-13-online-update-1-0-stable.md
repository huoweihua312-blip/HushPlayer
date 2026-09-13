# HushPlayer 1.0.0 Stable Online Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 HushPlayer 从当前 `0.6.0-beta.13` 平滑升级到 `1.0.0 Stable`，复用现有更新器，并为已包含兼容解析器的 beta 客户端提供同一个正式 1.0.0 安装包的迁移入口。

**Architecture:** 保留现有 `AppUpdateService`、portable ZIP 更新助手、完整安装包回退和 `UpdateDialog`。当前版本客户端改为读取 `stable` manifest；旧 beta 客户端继续读取 `beta` manifest，而 beta migration manifest 使用真实目标版本 `1.0.0`、数字版本 `1.0.0.0`，其安装包地址指向真正的 HushPlayer 1.0.0 产物。运行时解析器只放宽版本格式约束，不创建虚假的 beta 版本，不引入 `windows.mirrors[]` 或新的下载器。

**Tech Stack:** Python 3.13 target, PySide6, existing `QNetworkAccessManager`, JSON manifests, PowerShell packaging scripts, SHA-256, existing portable updater and Inno Setup fallback.

**Spec:** User-approved Phase 10.8 adjustment in the conversation: personal-device scope, one-time beta-to-1.0.0 migration, no push during implementation.

**Compatibility boundary:** The checked-in `0.6.0-beta.13` parser requires a
channel suffix in `version` and rejects `1.0.0` before it can inspect
`channel=beta`. The source parser is therefore widened in this change, but an
already-installed binary cannot receive that parser change through the same
manifest it currently rejects. Before publishing the migration manifest, verify
that each beta device has a compatible client; otherwise publish a separate,
legacy-readable bridge release first. Do not invent `1.0.0-beta.0`.

## Global Constraints

- `APP_VERSION = "1.0.0"`.
- `APP_NUMERIC_VERSION = (1, 0, 0, 0)`.
- `UPDATE_CHANNEL = "stable"`.
- `UPDATE_ARCHITECTURE = "win-x64"`.
- Do not introduce `windows.mirrors[]`.
- Do not rewrite `AppUpdateService`, `packaging/hushplayer_updater.py`, or `UpdateDialog`.
- Preserve `setup_*`, `package_*`, `release_notes`, and `release_history` fields.
- Preserve GitCode/GitHub manifest fallback in existing clients.
- Preserve installer SHA-256, portable ZIP safety checks, Inno Setup fallback, restart, and exit behavior.
- Do not modify playback, lyrics, queue, database, settings transactions, tray lifecycle, or B2 UI.
- Do not fabricate release URLs, sizes, or hashes; final manifests require real 1.0.0 artifacts.
- Do not push automatically.
- Keep `docs/ui-v2-b2-component-map.zip` untracked and out of every commit.

---

### Task 1: Extend the version contract for stable releases

**Files:**
- Modify: `F:\Projects\HushPlayer\app\core\version.py`
- Test: `F:\Projects\HushPlayer\tests\app_version_smoke.py`

**Interfaces:**
- Preserve `parse_numeric_version(value)` and `is_newer_numeric_version(candidate, current)`.
- Preserve the four-part numeric ordering used by the updater.
- Add stable-version constants without changing the public names imported by existing modules.

- [ ] **Step 1: Add failing stable-version assertions**

Extend `tests/app_version_smoke.py` to assert:

```python
assert APP_VERSION == "1.0.0"
assert APP_NUMERIC_VERSION == (1, 0, 0, 0)
assert UPDATE_CHANNEL == "stable"
assert UPDATE_ARCHITECTURE == "win-x64"
assert parse_numeric_version("1.0.0.0") == (1, 0, 0, 0)
assert is_newer_numeric_version("1.0.0.0", "0.6.0.13")
```

Keep beta ordering assertions such as `0.5.0.10 > 0.5.0.2`.

- [ ] **Step 2: Run the version smoke to verify the new assertions fail**

Run:

```powershell
.\.venv\Scripts\python.exe tests\app_version_smoke.py
```

Expected: failure because the current application constants still describe `0.6.0-beta.13`.

- [ ] **Step 3: Update the version constants and source URLs**

Set:

```python
APP_VERSION = "1.0.0"
APP_NUMERIC_VERSION = (1, 0, 0, 0)
UPDATE_CHANNEL = "stable"
UPDATE_ARCHITECTURE = "win-x64"
```

Point `UPDATE_MANIFEST_SOURCES` at `updates/stable/win-x64.json` on the existing GitCode and GitHub hosts, preserving the tuple shape and `UPDATE_MANIFEST_URL` compatibility alias.

- [ ] **Step 4: Run the version smoke again**

Run:

```powershell
.\.venv\Scripts\python.exe tests\app_version_smoke.py
```

Expected: PASS, including stable constants, four-part comparison, and centralized manifest source configuration.

- [ ] **Step 5: Run syntax validation**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile app\core\version.py
```

Expected: exit code `0`.

### Task 2: Make runtime manifest parsing accept stable and beta migration versions

**Files:**
- Modify: `F:\Projects\HushPlayer\app\services\app_update_service.py`
- Test: `F:\Projects\HushPlayer\tests\app_update_smoke.py`
- Test: `F:\Projects\HushPlayer\tests\in_app_update_smoke.py`

**Interfaces:**
- Keep `UpdateManifest` fields and properties unchanged.
- Keep `AppUpdateService.start_download()`, `launch_verified_update()`, and `launch_verified_installer()` signatures unchanged.
- Keep the existing manifest-source fallback behavior unchanged.

- [ ] **Step 1: Add parser fixtures for stable and migration manifests**

Add fixtures covering:

```text
stable target: version=1.0.0, channel=stable, numeric_version=1.0.0.0
beta migration: version=1.0.0, channel=beta, numeric_version=1.0.0.0
```

Assert that both parse, both report `is_newer` when tested against a pre-1.0 current numeric version, and both retain the existing setup/package fields.

- [ ] **Step 2: Run the focused tests to verify the stable fixture fails**

Run:

```powershell
.\.venv\Scripts\python.exe tests\app_update_smoke.py
```

Expected: failure in the new stable fixture because `_VERSION_PATTERN` currently requires a channel suffix.

- [ ] **Step 3: Split version-shape validation from channel validation**

Update the parser so it accepts:

```text
stable: major.minor.patch
pre-release: major.minor.patch-channel.sequence
```

For stable manifests, require `channel == "stable"` and derive numeric version as `major.minor.patch.0`.

For beta migration manifests, allow `channel == "beta"` with a three-part stable version such as `1.0.0`, while keeping the existing beta-suffixed format for historical beta releases.

The numeric version must still equal the version label: `1.0.0` maps to `1.0.0.0`. No synthetic `1.0.0-beta.0` version is created.

Do not change URL validation, size limits, SHA-256 validation, package filename checks, or ZIP safety checks.

- [ ] **Step 4: Preserve installer filename behavior**

Keep `UpdateManifest.installer_filename` and `package_filename` behavior stable for the actual manifest version. Stable manifests must produce:

```text
HushPlayer-1.0.0-win-x64-setup.exe
HushPlayer-1.0.0-win-x64-update.zip
```

The beta migration manifest uses the same `1.0.0` asset filenames and URLs as the stable manifest; no installer launch or hash semantics may change.

- [ ] **Step 5: Run updater smoke tests**

Run:

```powershell
.\.venv\Scripts\python.exe tests\app_update_smoke.py
.\.venv\Scripts\python.exe tests\in_app_update_smoke.py
```

Expected: PASS for stable parsing, beta migration parsing, legacy beta manifests, downloads, SHA-256 rejection, ZIP validation, updater launch mocks, and installer fallback.

- [ ] **Step 6: Run syntax validation**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile app\services\app_update_service.py
```

Expected: exit code `0`.

### Task 3: Update the manifest preparation helper for stable 1.0.0

**Files:**
- Modify: `F:\Projects\HushPlayer\packaging\prepare_update_manifest.py`
- Test: `F:\Projects\HushPlayer\tests\update_manifest_changelog_smoke.py`
- Test: `F:\Projects\HushPlayer\tests\packaging_version_smoke.py`

**Interfaces:**
- Preserve existing CLI flags and their meanings.
- Preserve `build_staged_manifest()`, `validate_prebuild_manifest()`, and `validate_final_manifest()` call signatures unless a backward-compatible optional argument is required.
- Continue reading release notes from `CHANGELOG.md`.

- [ ] **Step 1: Add stable changelog and staged-manifest fixtures**

Update smoke fixtures to include a formal `1.0.0` stable release section and assert that `prepare_update_manifest.py` can synchronize notes and history for a stable target.

Add a migration fixture with `version=1.0.0` and `channel=beta`; do not treat the manifest channel as the installed product channel.

- [ ] **Step 2: Run the helper smoke to identify current stable-format failures**

Run:

```powershell
.\.venv\Scripts\python.exe tests\update_manifest_changelog_smoke.py
.\.venv\Scripts\python.exe tests\packaging_version_smoke.py
```

Expected: failure in stable release identity validation until the helper accepts a three-part stable version.

- [ ] **Step 3: Support stable release identity and filenames**

Update the helper’s release regex and identity checks so stable `1.0.0` is valid when `UPDATE_CHANNEL == "stable"` and maps to numeric `1.0.0.0`.

Keep beta release parsing and history compatibility intact.

Keep the existing GitCode release asset base URL as the default transport source. Do not add mirror arrays or a second publishing architecture.

- [ ] **Step 4: Keep real artifact metadata mandatory**

Ensure staged/final manifest generation still computes:

```text
setup_size
sha256
package_size
package_sha256
package_filename
```

from actual files. Reject missing installer/package paths and never emit fabricated values.

- [ ] **Step 5: Run helper and packaging tests**

Run:

```powershell
.\.venv\Scripts\python.exe tests\update_manifest_changelog_smoke.py
.\.venv\Scripts\python.exe tests\packaging_version_smoke.py
```

Expected: PASS for stable and beta release parsing, changelog synchronization, staged manifests, final file-size/SHA checks, and packaging script references.

- [ ] **Step 6: Run syntax validation**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile packaging\prepare_update_manifest.py
```

Expected: exit code `0`.

### Task 4: Create the stable manifest and beta migration manifest from the real 1.0.0 artifacts

**Files:**
- Create: `F:\Projects\HushPlayer\updates\stable\win-x64.json`
- Modify: `F:\Projects\HushPlayer\updates\beta\win-x64.json`
- Test: `F:\Projects\HushPlayer\tests\app_update_smoke.py`
- Test: `F:\Projects\HushPlayer\tests\update_manifest_changelog_smoke.py`

**Interfaces:**
- Keep the existing manifest field set; do not add `windows.mirrors`.
- Keep the beta manifest’s `channel` as `beta`.
- Keep both setup and portable package metadata when the artifacts exist.

- [ ] **Step 1: Build the 1.0.0 release artifacts**

After the code version is `1.0.0`, run the existing packaging flow:

```powershell
.\.venv\Scripts\python.exe packaging\build_update_payload.py ...
.\packaging\build_windows_release.ps1
.\packaging\build_windows_installer.ps1
```

Use the project’s existing script parameters and do not invent upload URLs. The resulting files must be named:

```text
HushPlayer-1.0.0-win-x64-setup.exe
HushPlayer-1.0.0-win-x64-update.zip
```

- [ ] **Step 2: Upload the artifacts to the intended release hosts**

Create the GitCode 1.0.0 release and upload both artifacts. Create the matching GitHub release only if the user chooses to maintain the mirror. Do not perform these network operations automatically in this task.

- [ ] **Step 3: Generate `updates/stable/win-x64.json`**

Use `prepare_update_manifest.py --stage-installer` or the existing release build flow with the real artifact paths and GitCode setup/package URLs. Confirm the manifest contains:

```text
version=1.0.0
channel=stable
numeric_version=1.0.0.0
setup_url/setup_size/sha256
package_url/package_size/package_sha256/package_filename
release_notes/release_history
```

- [ ] **Step 4: Generate the beta migration manifest**

Keep `channel=beta`, set:

```text
version=1.0.0
numeric_version=1.0.0.0
```

Point its setup and package URLs at the same 1.0.0 release assets and compute the real sizes and SHA-256 values. Preserve the existing beta release history and add a clear migration note explaining that the installed result is HushPlayer 1.0.0 Stable.

- [ ] **Step 5: Validate both manifests locally**

Run:

```powershell
.\.venv\Scripts\python.exe tests\app_update_smoke.py
.\.venv\Scripts\python.exe tests\update_manifest_changelog_smoke.py
```

Also run the helper’s final-manifest validation against both real artifact files. Expected: both manifests parse, sizes and SHA-256 values match, and the beta migration manifest remains acceptable to the legacy parser fixture.

### Task 5: Regression and release handoff checks

**Files:**
- Test: `F:\Projects\HushPlayer\tests\app_update_smoke.py`
- Test: `F:\Projects\HushPlayer\tests\in_app_update_smoke.py`
- Test: `F:\Projects\HushPlayer\tests\update_manifest_changelog_smoke.py`
- Test: `F:\Projects\HushPlayer\tests\app_version_smoke.py`
- Modify only if needed: `F:\Projects\HushPlayer\docs\release-architecture.md`

**Interfaces:**
- No changes to playback, lyrics, queue, database, settings transactions, tray lifecycle, or B2 UI.
- No real installer execution in automated tests.

- [ ] **Step 1: Run the complete update test set**

Run:

```powershell
.\.venv\Scripts\python.exe tests\app_update_smoke.py
.\.venv\Scripts\python.exe tests\in_app_update_smoke.py
.\.venv\Scripts\python.exe tests\update_manifest_changelog_smoke.py
.\.venv\Scripts\python.exe tests\app_version_smoke.py
```

Expected: all four commands exit successfully.

- [ ] **Step 2: Run syntax and diff checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py
.\.venv\Scripts\python.exe -m py_compile app\services\app_update_service.py
.\.venv\Scripts\python.exe -m py_compile packaging\prepare_update_manifest.py
git diff --check
```

Expected: all commands succeed.

- [ ] **Step 3: Verify protected behavior remains untouched**

Review the final diff and confirm no changes to playback, lyrics timing, queue model, database structures, settings transaction behavior, tray lifecycle, or B2 UI files.

- [ ] **Step 4: Record the release handoff**

Document the manual release order:

```text
1. Build HushPlayer 1.0.0.
2. Build setup.exe and portable update.zip.
3. Upload GitCode release assets.
4. Optionally upload matching GitHub release assets.
5. Generate and validate stable manifest.
6. Generate and validate beta migration manifest.
7. Push the committed manifests and code to GitHub/GitCode manually.
```

State explicitly that no real installer was launched by tests and no push is performed automatically.
