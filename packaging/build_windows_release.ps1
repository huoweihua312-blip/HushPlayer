[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [switch]$DiagnosticOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "main.py") -PathType Leaf)) {
    throw "main.py was not found in the project root."
}

$Python = if ($PythonPath) {
    [System.IO.Path]::GetFullPath($PythonPath)
} else {
    Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual environment Python was not found: $Python. Rebuild .venv with Python 3.13 x64 and requirements-lock.txt."
}

& $Python -c "import platform, struct, sys, PyInstaller, PySide6; assert sys.version_info[:2] == (3, 13); assert struct.calcsize('P') * 8 == 64; print('Python=' + platform.python_version()); print('PythonExecutable=' + sys.executable); print('PyInstaller=' + PyInstaller.__version__); print('PySide6=' + PySide6.__version__); print('Architecture=x64')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not available in the project virtual environment."
}

$NodeRuntimeHelper = Join-Path $PSScriptRoot "prepare_node_runtime.ps1"
if (-not (Test-Path -LiteralPath $NodeRuntimeHelper -PathType Leaf)) {
    throw "The fixed Node.js runtime preparation helper is missing: $NodeRuntimeHelper"
}
$RequirementsLock = Join-Path $ProjectRoot "requirements-lock.txt"
if (-not (Test-Path -LiteralPath $RequirementsLock -PathType Leaf)) {
    throw "The reproducible Windows dependency lock is missing: $RequirementsLock"
}
$Spec = Join-Path $ProjectRoot "packaging\HushPlayer.release.spec"
if (-not (Test-Path -LiteralPath $Spec -PathType Leaf)) {
    throw "The PyInstaller spec is missing: $Spec"
}
$VersionMetadataHelper = Join-Path $ProjectRoot "packaging\prepare_version_metadata.py"
if (-not (Test-Path -LiteralPath $VersionMetadataHelper -PathType Leaf)) {
    throw "The version metadata helper is missing: $VersionMetadataHelper"
}
$UpdateManifestHelper = Join-Path $ProjectRoot "packaging\prepare_update_manifest.py"
$UpdateManifest = Join-Path $ProjectRoot "updates\beta\win-x64.json"
foreach ($RequiredReleaseFile in @($UpdateManifestHelper, $UpdateManifest)) {
    if (-not (Test-Path -LiteralPath $RequiredReleaseFile -PathType Leaf)) {
        throw "Required release changelog input is missing: $RequiredReleaseFile"
    }
}
if ($DiagnosticOnly) {
    Write-Host "ProjectRoot=$ProjectRoot"
    Write-Host "RequirementsLock=$RequirementsLock"
    Write-Host "NodeRuntimeHelper=$NodeRuntimeHelper"
    Write-Host "Spec=$Spec"
    Write-Host "VersionMetadataHelper=$VersionMetadataHelper"
    Write-Host "UpdateManifestHelper=$UpdateManifestHelper"
    Write-Host "UpdateManifest=$UpdateManifest"
    Write-Host "DiagnosticOnly=OK"
    return
}
& $Python $UpdateManifestHelper --manifest $UpdateManifest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
. $NodeRuntimeHelper
$NodeRuntime = Prepare-HushPlayerNodeRuntime -ProjectRoot $ProjectRoot
$NodeExe = $NodeRuntime.NodeExe
$NodeArch = $NodeRuntime.Architecture
$NodeVersion = $NodeRuntime.Version
$NodeSigner = $NodeRuntime.Signer
Write-Host "Node=$NodeVersion ($NodeArch)"
Write-Host "NodeSigner=$NodeSigner"
Write-Host "NodeArchive=$($NodeRuntime.ArchiveUrl)"
Write-Host "NodeArchiveSha256=$($NodeRuntime.ArchiveSha256)"

function Remove-ProjectOutputDirectory([string]$Name) {
    if ($Name -notin @("build", "dist")) {
        throw "Refusing to remove unexpected output directory: $Name"
    }
    $Target = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Name))
    $Parent = [System.IO.Path]::GetFullPath((Split-Path -Parent $Target))
    if ($Parent.TrimEnd("\") -ne $ProjectRoot.TrimEnd("\")) {
        throw "Refusing to remove path outside project root: $Target"
    }
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

Remove-ProjectOutputDirectory "build"
Remove-ProjectOutputDirectory "dist"

$VersionOutputDir = Join-Path $ProjectRoot "build\version"
$VersionJson = @(& $Python $VersionMetadataHelper --output-dir $VersionOutputDir)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$VersionMetadata = ($VersionJson -join [Environment]::NewLine) | ConvertFrom-Json
$VersionInfoFile = [System.IO.Path]::GetFullPath([string]$VersionMetadata.version_info_file)
if (-not (Test-Path -LiteralPath $VersionInfoFile -PathType Leaf)) {
    throw "Generated Windows version info is missing: $VersionInfoFile"
}
$env:HUSHPLAYER_VERSION_INFO = $VersionInfoFile
$env:HUSHPLAYER_NODE_EXE = $NodeExe
Write-Host "AppVersion=$($VersionMetadata.app_version)"
Write-Host "NumericVersion=$($VersionMetadata.numeric_version)"
Write-Host "UpdateArchitecture=$($VersionMetadata.architecture)"

& $Python -m PyInstaller --noconfirm --clean --workpath (Join-Path $ProjectRoot "build\pyinstaller") --distpath (Join-Path $ProjectRoot "dist") $Spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$OutputRoot = Join-Path $ProjectRoot "dist\HushPlayer"
$SupportRoot = Join-Path $OutputRoot "_internal"
$ExePath = Join-Path $OutputRoot "HushPlayer.exe"
$BundledNode = Join-Path $SupportRoot "runtime\node\node.exe"
$Runner = Join-Path $SupportRoot "source_runtime\runner.js"
$RequiredFiles = @(
    $ExePath,
    $BundledNode,
    $Runner,
    (Join-Path $SupportRoot "source_runtime\plugin_host.js"),
    (Join-Path $SupportRoot "source_runtime\source_test_worker.js"),
    (Join-Path $SupportRoot "app\resources\defaults\source_registry.json")
)
foreach ($RequiredFile in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Required build output is missing: $RequiredFile"
    }
}
$ExeBytes = [System.IO.File]::ReadAllBytes($ExePath)
if ($ExeBytes.Length -lt 256) {
    throw "Release executable is too small to contain a valid PE header: $ExePath"
}
$PeOffset = [BitConverter]::ToInt32($ExeBytes, 0x3C)
$OptionalHeaderOffset = $PeOffset + 24
$Subsystem = [BitConverter]::ToUInt16($ExeBytes, $OptionalHeaderOffset + 68)
if ($Subsystem -ne 2) {
    throw "Release executable is not a Windows GUI application. PE subsystem=$Subsystem"
}
Write-Host "ExecutableSubsystem=Windows GUI"
if (Test-Path -LiteralPath (Join-Path $SupportRoot "source_runtime\source_registry.json")) {
    throw "Private source_runtime\source_registry.json must not be packaged."
}
foreach ($PrivatePath in @(
    (Join-Path $OutputRoot "data"),
    (Join-Path $SupportRoot "data"),
    (Join-Path $SupportRoot "user_sources"),
    (Join-Path $SupportRoot "source_runtime\sources")
)) {
    if (Test-Path -LiteralPath $PrivatePath) {
        throw "Private user data must not be packaged: $PrivatePath"
    }
}

$DefaultRegistryPath = Join-Path $SupportRoot "app\resources\defaults\source_registry.json"
$DefaultRegistry = Get-Content -LiteralPath $DefaultRegistryPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (@($DefaultRegistry.sources).Count -ne 0) {
    throw "Bundled default source registry must not contain real source entries."
}

$BundledNodeVersion = (& $BundledNode --version).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Bundled Node.js failed to run: $BundledNode"
}
& $BundledNode --check $Runner
if ($LASTEXITCODE -ne 0) {
    throw "Bundled Node.js failed to parse runner.js: $Runner"
}
Write-Host "BundledNode=$BundledNodeVersion"
Write-Host "BundledRunnerCheck=OK"

$RuntimeInfo = @(
    "NodeVersion=$NodeVersion"
    "NodeArchitecture=$NodeArch"
    "NodeSigner=$NodeSigner"
    "NodeArchiveUrl=$($NodeRuntime.ArchiveUrl)"
    "NodeArchiveSha256=$($NodeRuntime.ArchiveSha256)"
    "NodeExecutableSha256=$($NodeRuntime.NodeExeSha256)"
    "NodeLicenseSha256=$($NodeRuntime.LicenseSha256)"
) -join [Environment]::NewLine
[System.IO.File]::WriteAllText(
    (Join-Path $SupportRoot "runtime\node\NODE_RUNTIME_INFO.txt"),
    $RuntimeInfo + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\NODE_RUNTIME_NOTICE.txt") -Destination (Join-Path $SupportRoot "runtime\node\NODE_RUNTIME_NOTICE.txt") -Force
Copy-Item -LiteralPath $NodeRuntime.LicensePath -Destination (Join-Path $SupportRoot "runtime\node\LICENSE") -Force

$TotalBytes = (Get-ChildItem -LiteralPath $OutputRoot -Recurse -File | Measure-Object -Property Length -Sum).Sum
$TotalMiB = [Math]::Round($TotalBytes / 1MB, 2)
Write-Host "Build complete."
Write-Host "BuildVariant=Release"
Write-Host "Executable=$ExePath"
Write-Host "OutputSizeMiB=$TotalMiB"
