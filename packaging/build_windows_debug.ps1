[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$CurrentRoot = [System.IO.Path]::GetFullPath((Get-Location).Path)
if ($CurrentRoot.TrimEnd("\") -ne $ProjectRoot.TrimEnd("\")) {
    throw "Run this script from the HushPlayer project root: $ProjectRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "main.py") -PathType Leaf)) {
    throw "main.py was not found in the project root."
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual environment Python was not found: $Python"
}

& $Python -c "import platform, struct, PySide6; assert struct.calcsize('P') * 8 == 64; print('Python=' + platform.python_version()); print('PySide6=' + PySide6.__version__); print('Architecture=x64')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not available in the project virtual environment."
}

$RepositoryNode = Join-Path $ProjectRoot "runtime\node\node.exe"
if (Test-Path -LiteralPath $RepositoryNode -PathType Leaf) {
    $NodeExe = [System.IO.Path]::GetFullPath($RepositoryNode)
} else {
    $NodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($null -eq $NodeCommand) {
        throw "No Node.js runtime was found. Install an official Node.js Windows x64 runtime or place node.exe at runtime\node\node.exe."
    }
    $NodeExe = [System.IO.Path]::GetFullPath($NodeCommand.Source)
}

$NodeArch = (& $NodeExe -p "process.arch").Trim()
$NodeVersion = (& $NodeExe --version).Trim()
if ($LASTEXITCODE -ne 0 -or $NodeArch -ne "x64") {
    throw "Node.js must be a working Windows x64 runtime. Found architecture: $NodeArch"
}
$NodeSignature = Get-AuthenticodeSignature -LiteralPath $NodeExe
if ($NodeSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Node.js Authenticode signature is not valid: $($NodeSignature.Status)"
}
$NodeSigner = [string]$NodeSignature.SignerCertificate.Subject
if ($NodeSigner -notmatch "OpenJS Foundation") {
    throw "Node.js signer is not the OpenJS Foundation: $NodeSigner"
}
Write-Host "Node=$NodeVersion ($NodeArch)"
Write-Host "NodeSigner=$NodeSigner"

$NodeModules = Join-Path $ProjectRoot "source_runtime\node_modules"
if (-not (Test-Path -LiteralPath $NodeModules -PathType Container)) {
    throw "source_runtime\node_modules is missing. This script will not install dependencies automatically."
}
$NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $NpmCommand) {
    throw "npm.cmd is required only to audit the already-installed production dependency tree."
}
Push-Location (Join-Path $ProjectRoot "source_runtime")
try {
    & $NpmCommand.Source ls --omit=dev --all
    if ($LASTEXITCODE -ne 0) {
        throw "The installed production Node dependency tree did not pass npm ls."
    }
} finally {
    Pop-Location
}

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

$env:HUSHPLAYER_NODE_EXE = $NodeExe
$Spec = Join-Path $ProjectRoot "packaging\HushPlayer.debug.spec"
& $Python -m PyInstaller --noconfirm --clean --workpath (Join-Path $ProjectRoot "build\pyinstaller") --distpath (Join-Path $ProjectRoot "dist") $Spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$OutputRoot = Join-Path $ProjectRoot "dist\HushPlayer"
$ExePath = Join-Path $OutputRoot "HushPlayer.exe"
$BundledNode = Join-Path $OutputRoot "runtime\node\node.exe"
$RequiredFiles = @(
    $ExePath,
    $BundledNode,
    (Join-Path $OutputRoot "source_runtime\runner.js"),
    (Join-Path $OutputRoot "source_runtime\plugin_host.js"),
    (Join-Path $OutputRoot "source_runtime\source_test_worker.js"),
    (Join-Path $OutputRoot "app\resources\defaults\source_registry.json")
)
foreach ($RequiredFile in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Required build output is missing: $RequiredFile"
    }
}
if (Test-Path -LiteralPath (Join-Path $OutputRoot "source_runtime\source_registry.json")) {
    throw "Private source_runtime\source_registry.json must not be packaged."
}
if (Test-Path -LiteralPath (Join-Path $OutputRoot "data")) {
    throw "User data directory must not be packaged."
}

$RuntimeInfo = @(
    "NodeVersion=$NodeVersion"
    "NodeArchitecture=$NodeArch"
    "NodeSigner=$NodeSigner"
) -join [Environment]::NewLine
[System.IO.File]::WriteAllText(
    (Join-Path $OutputRoot "runtime\node\NODE_RUNTIME_INFO.txt"),
    $RuntimeInfo + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\NODE_RUNTIME_NOTICE.txt") -Destination (Join-Path $OutputRoot "runtime\node\NODE_RUNTIME_NOTICE.txt") -Force

$TotalBytes = (Get-ChildItem -LiteralPath $OutputRoot -Recurse -File | Measure-Object -Property Length -Sum).Sum
$TotalMiB = [Math]::Round($TotalBytes / 1MB, 2)
Write-Host "Build complete."
Write-Host "Executable=$ExePath"
Write-Host "OutputSizeMiB=$TotalMiB"
