# HushPlayer release architecture

The release operations repository exposes only manual workflows. `release.yml` is
the Environment-protected path: one candidate job performs the validation,
exact-commit checkout, installer build, artifact verification, and offline
acceptance. A single job bound to the `production` environment then performs all
production steps in order. It is skipped entirely when `dry_run` is true, so it
does not request approval or evaluate release secrets.

`prepare-release.yml` and `promote-release.yml` are the manual-promotion option
for private personal repositories where GitHub Environment reviewers are not
available. Prepare creates `hushplayer-prepare-<run-id>-<attempt>`. Promote
requires both values, downloads that exact artifact, verifies its run identity,
and only then performs its ordered promotion steps. The operator's manual
dispatch is the promotion checkpoint in this alternative.

## Scratch handling

GitHub Actions does not permit the `runner` context in workflow-level or job
`env`. Each job therefore invokes `scripts/Release.InitializeScratch.ps1` before
any release operation. The script derives an isolated directory from
`RUNNER_TEMP`, `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, and `GITHUB_JOB`, exports
it as `RELEASE_SCRATCH` through `GITHUB_ENV`, and exposes it as a step output for
Actions that need a path. Cleanup rejects every target outside
`RUNNER_TEMP/hushplayer-release`; it never treats the checkout workspace as
temporary storage.

## Artifact and safety rules

The installer is built once and all later stages consume the same artifact.
Metadata records the filename, size, SHA-256, source SHA, run ID, and run
attempt. Candidate manifests are generated and verified locally before any
formal manifest operation. The production order places anonymous GitCode
download verification before `PublishManifests`. That download uses a dedicated
`HttpClientHandler` with `UseProxy = false`, carries no credential, and verifies
both file size and SHA-256. Conflict handling refuses to replace an existing
version with a different SHA-256.

All PowerShell receives dispatch inputs only through environment variables.
Secrets are limited to live publishing jobs and are never written into reports,
files, URLs, or log messages. The GitHub App action is configured with the
repository's client-ID variable through its official `app-id` input; GitCode
uses only `GITCODE_TOKEN`.

The mock and static tests do not contact GitHub or GitCode. Live publisher
adapters require a separate production integration review before enabling real
remote calls.
