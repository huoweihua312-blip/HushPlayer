[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [string]$VpkPath = "",
    [string]$ReleaseDir = "",
    [string]$OutputDir = "",
    [switch]$BuildRelease,
    [switch]$DiagnosticOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Python = if ($PythonPath) {
    [System.IO.Path]::GetFullPath($PythonPath)
} else {
    @(
        (Join-Path $ProjectRoot ".venv313\Scripts\python.exe")
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    ) | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    } | Select-Object -First 1
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python was not found: $Python"
}

$ReleasePath = if ($ReleaseDir) {
    [System.IO.Path]::GetFullPath($ReleaseDir)
} else {
    Join-Path $ProjectRoot "dist\HushPlayer"
}
$OutputPath = if ($OutputDir) {
    [System.IO.Path]::GetFullPath($OutputDir)
} else {
    Join-Path $ProjectRoot "dist\velopack"
}
$VersionMetadataHelper = Join-Path $ProjectRoot "packaging\prepare_version_metadata.py"
$IconPath = Join-Path $ProjectRoot "assets\icons\HushPlayer.ico"

$Vpk = if ($VpkPath) {
    [System.IO.Path]::GetFullPath($VpkPath)
} else {
    $command = Get-Command vpk -ErrorAction SilentlyContinue
    if ($command) { $command.Source } else { $null }
}

if ($DiagnosticOnly) {
    Write-Host "ProjectRoot=$ProjectRoot"
    Write-Host "Python=$Python"
    Write-Host "ReleaseDir=$ReleasePath"
    Write-Host "OutputDir=$OutputPath"
    Write-Host "Vpk=$Vpk"
    Write-Host "DiagnosticOnly=OK"
    return
}

if (-not $Vpk -or -not (Test-Path -LiteralPath $Vpk -PathType Leaf)) {
    throw "Velopack vpk was not found. Install the vpk tool or pass -VpkPath explicitly."
}
if (-not (Test-Path -LiteralPath $VersionMetadataHelper -PathType Leaf)) {
    throw "Version metadata helper is missing: $VersionMetadataHelper"
}
if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
    throw "Application icon is missing: $IconPath"
}

& $Python -c "import velopack; print('VelopackPython=' + getattr(velopack, '__version__', 'unknown'))"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python environment does not contain the optional 'velopack' package. Install it before building the PyInstaller directory."
}

if ($BuildRelease) {
    & (Join-Path $ProjectRoot "packaging\build_windows_release.ps1") -PythonPath $Python
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ReleaseExe = Join-Path $ReleasePath "HushPlayer.exe"
if (-not (Test-Path -LiteralPath $ReleaseExe -PathType Leaf)) {
    throw "Release output is missing: $ReleaseExe. Run build_windows_release.ps1 or pass -BuildRelease."
}

$VersionOutputDir = Join-Path $ProjectRoot "build\velopack-version"
$VersionJson = @(& $Python $VersionMetadataHelper --output-dir $VersionOutputDir)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$VersionMetadata = ($VersionJson -join [Environment]::NewLine) | ConvertFrom-Json

New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
$Arguments = @(
    "pack",
    "--packId", "HushPlayer",
    "--packTitle", "HushPlayer",
    "--packVersion", [string]$VersionMetadata.app_version,
    "--packDir", $ReleasePath,
    "--mainExe", "HushPlayer.exe",
    "--icon", $IconPath,
    "--outputDir", $OutputPath
)
& $Vpk @Arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Velopack package complete."
Write-Host "AppVersion=$($VersionMetadata.app_version)"
Write-Host "OutputDir=$OutputPath"
Get-ChildItem -LiteralPath $OutputPath -File | Select-Object Name, Length
