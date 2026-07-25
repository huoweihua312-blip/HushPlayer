Set-StrictMode -Version Latest

function Write-ReleaseJson([string]$Path, $Value) {
    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($Path))
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($Path), ($Value | ConvertTo-Json -Depth 32) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Read-ReleaseJson([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing release JSON: $Path" }
    Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-ReleaseSha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing release file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-ReleaseInputs([string]$Version, [string]$NumericVersion, [string]$SourceCommit, [string]$PreviousVersion, [string]$Channel) {
    if ($Version -notmatch '^\d+\.\d+\.\d+-[a-z][a-z0-9-]*\.\d+$') { throw 'Invalid version.' }
    if ($NumericVersion -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid numeric_version.' }
    if ($SourceCommit -notmatch '^[0-9a-fA-F]{40}$') { throw 'source_commit must be a full SHA.' }
    if ($Channel -notmatch '^[a-z][a-z0-9-]*$' -or $Version -notmatch ("-" + [regex]::Escape($Channel) + '\.\d+$')) { throw 'Invalid release_channel.' }
    $match = [regex]::Match($Version, '^(\d+)\.(\d+)\.(\d+)-[a-z][a-z0-9-]*\.(\d+)$')
    if ((@($match.Groups[1].Value,$match.Groups[2].Value,$match.Groups[3].Value,$match.Groups[4].Value) -join '.') -ne $NumericVersion) { throw 'version and numeric_version differ.' }
    if ($PreviousVersion -and $PreviousVersion -notmatch '^\d+\.\d+\.\d+-[a-z][a-z0-9-]*\.\d+$') { throw 'Invalid previous_version.' }
}

function Assert-ManifestPair($GitHub, $GitCode) {
    foreach ($field in @('schema_version','channel','version','numeric_version','architecture','setup_size','sha256','release_notes')) {
        if ($GitHub.$field -ne $GitCode.$field) { throw "Manifest semantic mismatch: $field" }
    }
}
