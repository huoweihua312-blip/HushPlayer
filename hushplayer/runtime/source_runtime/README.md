# HushPlayer online source runtime

This directory hosts the optional Node.js process used for online source search,
metadata, lyrics, playback resolution, and download resolution. It does not run
inside the Python process.

## Protocol

`runner.js` reads one JSON object per line from standard input and writes one JSON
response per line to standard output. Every request and response carries the same
numeric `id`. Plugin logs are redirected to standard error.

Supported actions:

- `ping`
- `listSources`
- `search`
- `getMetadata`
- `getLyric`
- `resolvePlayback`
- `resolveDownload`
- `cancel`
- `testSource`
- `reloadSource`
- `shutdown`

Commercial-platform audio URL extraction is not implemented. Playback and download
are available only when all of these conditions are true:

- the registry/JSON manifest declares `contentPolicy` as `open` or `user_owned`;
- the matching capability is explicitly `true`;
- the JavaScript plugin implements the matching method.

Raw `.js` imports default to `contentPolicy: unknown` and cannot enable playback or
download by themselves. A reviewed JSON manifest may reference a JS file and declare:

```json
{
  "id": "my-open-source",
  "name": "My open source",
  "filename": "../user_sources/my_open_source.js",
  "contentPolicy": "open",
  "capabilities": {
    "search": true,
    "metadata": true,
    "lyrics": true,
    "playback": true,
    "download": true
  }
}
```

The plugin methods are `resolvePlayback(track, options)` and
`resolveDownload(track, options)`. Both return an object with a non-empty HTTP(S)
`url`; optional fields are `headers`, `mimeType`, `quality`, `expiresAt`, `seekable`,
and `filename`. HushPlayer currently accepts playback/download only when `headers`
is empty. Downloads are saved to a path selected by the user and are not added to
the local library automatically.

## Source storage

- `source_registry.json`: installed source metadata and enabled state.
- `sources/staging`: newly imported files before confirmation.
- `sources/active`: confirmed user-imported source files.
- `sources/backups`: reserved for later manual-update backups.

Existing source and test files are not overwritten by the runner.

## Security boundary

The runtime validates source paths, size, direct `require()` calls, and blocks direct
access to sensitive Node modules such as `fs`, `child_process`, and `worker_threads`.
Tests run in a separate Node process with timeouts. Resolution does not implement
DRM handling, decryption, login bypasses, proxies, or request-header forwarding.

These checks reduce risk but are not a complete sandbox. Only enable source code you
trust. No dependency is installed automatically.
