[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [string]$IsccPath = "",
    [switch]$DiagnosticOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Python = if ($PythonPath) {
    [System.IO.Path]::GetFullPath($PythonPath)
} else {
    Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python was not found: $Python"
}

& $Python -c "import platform, struct, sys; assert sys.version_info[:2] == (3, 13); assert struct.calcsize('P') * 8 == 64; print('Python=' + platform.python_version()); print('Architecture=x64')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$VersionMetadataHelper = Join-Path $ProjectRoot "packaging\prepare_version_metadata.py"
$InstallerScript = Join-Path $ProjectRoot "packaging\installer\HushPlayer.iss"
foreach ($RequiredFile in @($VersionMetadataHelper, $InstallerScript)) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Required installer build input is missing: $RequiredFile"
    }
}

$Iscc = if ($IsccPath) {
    [System.IO.Path]::GetFullPath($IsccPath)
} else {
    @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc -PathType Leaf)) {
    throw "Inno Setup 6 compiler was not found. Pass -IsccPath explicitly."
}
$Iscc = [System.IO.Path]::GetFullPath($Iscc)

if ($DiagnosticOnly) {
    Write-Host "ProjectRoot=$ProjectRoot"
    Write-Host "Python=$Python"
    Write-Host "VersionMetadataHelper=$VersionMetadataHelper"
    Write-Host "InstallerScript=$InstallerScript"
    Write-Host "Iscc=$Iscc"
    Write-Host "DiagnosticOnly=OK"
    return
}

$ReleaseExe = Join-Path $ProjectRoot "dist\HushPlayer\HushPlayer.exe"
if (-not (Test-Path -LiteralPath $ReleaseExe -PathType Leaf)) {
    throw "Release output is missing: $ReleaseExe. Run build_windows_release.ps1 first."
}

$VersionOutputDir = Join-Path $ProjectRoot "build\version"
$VersionJson = @(& $Python $VersionMetadataHelper --output-dir $VersionOutputDir)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$VersionMetadata = ($VersionJson -join [Environment]::NewLine) | ConvertFrom-Json

$AppVersionDefine = '/DMyAppVersion=' + [string]$VersionMetadata.app_version
$NumericVersionDefine = '/DMyAppNumericVersion=' + [string]$VersionMetadata.numeric_version
$ArchitectureDefine = '/DMyAppArchitecture=' + [string]$VersionMetadata.architecture

& $Iscc $AppVersionDefine $NumericVersionDefine $ArchitectureDefine $InstallerScript
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$InstallerPath = Join-Path (
    Join-Path $ProjectRoot "dist\installer"
) ([string]$VersionMetadata.installer_filename)
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    throw "Expected installer output is missing: $InstallerPath"
}

$InstallerItem = Get-Item -LiteralPath $InstallerPath
$InstallerSha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Installer build complete."
Write-Host "AppVersion=$($VersionMetadata.app_version)"
Write-Host "NumericVersion=$($VersionMetadata.numeric_version)"
Write-Host "Installer=$InstallerPath"
Write-Host "SetupSize=$($InstallerItem.Length)"
Write-Host "SHA256=$InstallerSha256"
