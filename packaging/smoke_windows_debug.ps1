[CmdletBinding()]
param(
    [string]$PackagePath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $PackagePath) {
    $PackagePath = Join-Path $ProjectRoot "dist\HushPlayer"
}
$PackagePath = [System.IO.Path]::GetFullPath($PackagePath)
$SourceExe = Join-Path $PackagePath "HushPlayer.exe"
if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) {
    throw "Packaged executable was not found: $SourceExe"
}

$SmokeRoot = Join-Path $ProjectRoot "build\packaging-smoke"
$LaunchCwd = Join-Path $SmokeRoot "launch cwd outside project"
$SpacePackage = Join-Path $SmokeRoot "portable package with spaces\HushPlayer"
$ChineseName = ([string][char]0x4E2D) + ([string][char]0x6587) + " portable"
$ChinesePackage = Join-Path (Join-Path $SmokeRoot $ChineseName) "HushPlayer"
New-Item -ItemType Directory -Path $LaunchCwd -Force | Out-Null

function Reset-SmokePackageDestination([string]$Destination) {
    $ResolvedSmokeRoot = [System.IO.Path]::GetFullPath($SmokeRoot).TrimEnd("\")
    $ResolvedDestination = [System.IO.Path]::GetFullPath($Destination)
    if (-not $ResolvedDestination.StartsWith(
        $ResolvedSmokeRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to replace a path outside the smoke workspace: $ResolvedDestination"
    }
    if (Test-Path -LiteralPath $ResolvedDestination) {
        Remove-Item -LiteralPath $ResolvedDestination -Recurse -Force
    }
}

foreach ($Destination in @($SpacePackage, $ChinesePackage)) {
    Reset-SmokePackageDestination $Destination
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $PackagePath -Destination $Destination -Recurse -Force
}

$OriginalEnvironment = @{}
foreach ($Name in @(
    "HUSHPLAYER_APP_DATA_DIR",
    "HUSHPLAYER_CACHE_DIR",
    "HUSHPLAYER_LOG_DIR",
    "HUSHPLAYER_PACKAGING_SMOKE_EXIT_MS",
    "NODE_PATH",
    "PATH"
)) {
    $OriginalEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}

$NodeBefore = @(Get-Process node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
try {
    $env:HUSHPLAYER_PACKAGING_SMOKE_EXIT_MS = "4000"
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"

    function Test-BundledNodeRunner([string]$RunRoot) {
        $SupportRoot = Join-Path $RunRoot "_internal"
        $BundledNode = [System.IO.Path]::GetFullPath((Join-Path $SupportRoot "runtime\node\node.exe"))
        $Runner = [System.IO.Path]::GetFullPath((Join-Path $SupportRoot "source_runtime\runner.js"))
        if (-not (Test-Path -LiteralPath $BundledNode -PathType Leaf)) {
            throw "Bundled Node.js was not found: $BundledNode"
        }
        if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) {
            throw "Bundled runner.js was not found: $Runner"
        }
        $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
        $StartInfo.FileName = $BundledNode
        $StartInfo.Arguments = '"' + $Runner + '"'
        $StartInfo.WorkingDirectory = Split-Path -Parent $Runner
        $StartInfo.UseShellExecute = $false
        $StartInfo.CreateNoWindow = $true
        $StartInfo.RedirectStandardInput = $true
        $StartInfo.RedirectStandardOutput = $true
        $StartInfo.RedirectStandardError = $true
        $env:NODE_PATH = Join-Path $SupportRoot "source_runtime\node_modules"
        $RunnerProcess = New-Object System.Diagnostics.Process
        $RunnerProcess.StartInfo = $StartInfo
        if (-not $RunnerProcess.Start()) {
            throw "Bundled Node runner did not start: $BundledNode"
        }
        $RunnerProcess.StandardInput.WriteLine('{"id":1,"action":"ping"}')
        $RunnerProcess.StandardInput.WriteLine('{"id":0,"action":"shutdown"}')
        $RunnerProcess.StandardInput.Close()
        $RunnerStdout = $RunnerProcess.StandardOutput.ReadToEnd()
        $RunnerStderr = $RunnerProcess.StandardError.ReadToEnd()
        if (-not $RunnerProcess.WaitForExit(10000)) {
            $RunnerProcess.Kill()
            throw "Bundled Node runner did not exit after shutdown."
        }
        if ($RunnerProcess.ExitCode -ne 0 -or $RunnerStdout -notmatch '"runnerVersion"') {
            throw "Bundled Node runner ping failed. stderr=$RunnerStderr"
        }
    }

    $Runs = @(
        @{ Name = "original"; Root = $PackagePath },
        @{ Name = "spaces"; Root = $SpacePackage },
        @{ Name = "unicode"; Root = $ChinesePackage }
    )
    foreach ($Run in $Runs) {
        $RunRoot = [string]$Run.Root
        $RunName = [string]$Run.Name
        $UserRoot = Join-Path $SmokeRoot ("user-" + $RunName)
        $env:HUSHPLAYER_APP_DATA_DIR = Join-Path $UserRoot "appdata"
        $env:HUSHPLAYER_CACHE_DIR = Join-Path $UserRoot "cache"
        $env:HUSHPLAYER_LOG_DIR = Join-Path $UserRoot "logs"
        $Stdout = Join-Path $SmokeRoot ("stdout-" + $RunName + ".log")
        $Stderr = Join-Path $SmokeRoot ("stderr-" + $RunName + ".log")
        Test-BundledNodeRunner $RunRoot
        $Process = Start-Process -FilePath (Join-Path $RunRoot "HushPlayer.exe") -WorkingDirectory $LaunchCwd -WindowStyle Hidden -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -Wait -PassThru
        if ($Process.ExitCode -ne 0) {
            throw "Packaged application run '$RunName' failed with exit code $($Process.ExitCode)."
        }
        $RunStdout = Get-Content -LiteralPath $Stdout -Raw -Encoding UTF8
        if ($RunStdout -notmatch '\[packaging-smoke\] Node runner ready') {
            $RunStderr = Get-Content -LiteralPath $Stderr -Raw -Encoding UTF8
            throw "Packaged application run '$RunName' did not start its bundled Node runner. stderr=$RunStderr"
        }
        $Registry = Join-Path $env:HUSHPLAYER_APP_DATA_DIR "source_runtime\source_registry.json"
        if (-not (Test-Path -LiteralPath $Registry -PathType Leaf)) {
            throw "Run '$RunName' did not create its AppData registry."
        }
        if (-not (Test-Path -LiteralPath $env:HUSHPLAYER_CACHE_DIR -PathType Container)) {
            throw "Run '$RunName' did not create its cache directory."
        }
        if ($RunName -eq "original") {
            $RegistryDocument = Get-Content -LiteralPath $Registry -Raw -Encoding UTF8 | ConvertFrom-Json
            Add-Member -InputObject $RegistryDocument -NotePropertyName "smokePreserved" -NotePropertyValue $true -Force
            $RegistryText = $RegistryDocument | ConvertTo-Json -Depth 20
            [System.IO.File]::WriteAllText(
                $Registry,
                $RegistryText + [Environment]::NewLine,
                [System.Text.UTF8Encoding]::new($false)
            )
            $Restart = Start-Process -FilePath (Join-Path $RunRoot "HushPlayer.exe") -WorkingDirectory $LaunchCwd -WindowStyle Hidden -RedirectStandardOutput (Join-Path $SmokeRoot "stdout-restart.log") -RedirectStandardError (Join-Path $SmokeRoot "stderr-restart.log") -Wait -PassThru
            if ($Restart.ExitCode -ne 0) {
                throw "Packaged application restart failed with exit code $($Restart.ExitCode)."
            }
            $Preserved = Get-Content -LiteralPath $Registry -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($Preserved.smokePreserved -ne $true) {
                throw "Existing user registry was overwritten on restart."
            }
        }
        Write-Host "Smoke run passed: $RunName"
    }
} finally {
    foreach ($Name in $OriginalEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $OriginalEnvironment[$Name], "Process")
    }
}

Start-Sleep -Milliseconds 500
$NodeAfter = @(Get-Process node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$ResidualNode = @($NodeAfter | Where-Object { $_ -notin $NodeBefore })
if ($ResidualNode.Count -gt 0) {
    throw "Packaged application left Node.js processes running: $($ResidualNode -join ', ')"
}
Write-Host "Packaging smoke tests passed."
