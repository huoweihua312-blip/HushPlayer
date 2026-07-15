[CmdletBinding()]
param()

Set-StrictMode -Version Latest

function Prepare-HushPlayerNodeRuntime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $NodeVersion = "22.22.3"
    $NodeTag = "v$NodeVersion"
    $NodeArchiveName = "node-$NodeTag-win-x64.zip"
    $NodeArchiveUrl = "https://nodejs.org/dist/$NodeTag/$NodeArchiveName"
    $ExpectedArchiveSha256 = "6C8D54F635FEFF4DF76C2CA80F45332EB2FF57D25226EDCE36592E51A177EE33"
    $ExpectedNodeExeSha256 = "780F44F2C53C108BAE261ADA21A525B4BFE733C020AC85E41BFE94479090AC9B"

    $ResolvedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
    $CacheRoot = Join-Path $ResolvedProjectRoot ".build-cache\node"
    $ArchivePath = Join-Path $CacheRoot $NodeArchiveName
    $ExtractRoot = Join-Path $CacheRoot "node-$NodeTag-win-x64"
    $NodeExe = Join-Path $ExtractRoot "node.exe"
    $NpmCommand = Join-Path $ExtractRoot "npm.cmd"
    $LicensePath = Join-Path $ExtractRoot "LICENSE"

    New-Item -ItemType Directory -Path $CacheRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        Write-Host "Downloading fixed Node.js runtime: $NodeArchiveUrl"
        Invoke-WebRequest -Uri $NodeArchiveUrl -OutFile $ArchivePath -UseBasicParsing
    }

    $ArchiveSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($ArchiveSha256 -ne $ExpectedArchiveSha256) {
        throw "Node.js archive SHA-256 mismatch. Expected $ExpectedArchiveSha256, found $ArchiveSha256 at $ArchivePath"
    }

    $RequiredExtractedFiles = @($NodeExe, $NpmCommand, $LicensePath)
    if (@($RequiredExtractedFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }).Count -gt 0) {
        if (Test-Path -LiteralPath $ExtractRoot) {
            Remove-Item -LiteralPath $ExtractRoot -Recurse -Force
        }
        $ExpandRoot = Join-Path $CacheRoot ("extract-" + [Guid]::NewGuid().ToString("N"))
        try {
            Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExpandRoot -Force
            $ExpandedDirectory = Join-Path $ExpandRoot "node-$NodeTag-win-x64"
            if (-not (Test-Path -LiteralPath $ExpandedDirectory -PathType Container)) {
                throw "The verified Node.js archive did not contain the expected directory: $ExpandedDirectory"
            }
            Move-Item -LiteralPath $ExpandedDirectory -Destination $ExtractRoot
        } finally {
            if (Test-Path -LiteralPath $ExpandRoot) {
                Remove-Item -LiteralPath $ExpandRoot -Recurse -Force
            }
        }
    }

    foreach ($RequiredFile in $RequiredExtractedFiles) {
        if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
            throw "The verified Node.js archive is missing a required file: $RequiredFile"
        }
    }

    $NodeExeSha256 = (Get-FileHash -LiteralPath $NodeExe -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($NodeExeSha256 -ne $ExpectedNodeExeSha256) {
        throw "Node.js executable SHA-256 mismatch. Expected $ExpectedNodeExeSha256, found $NodeExeSha256 at $NodeExe"
    }

    $NodeArch = (& $NodeExe -p "process.arch").Trim()
    $DetectedNodeVersion = (& $NodeExe --version).Trim()
    if ($LASTEXITCODE -ne 0 -or $DetectedNodeVersion -ne $NodeTag -or $NodeArch -ne "x64") {
        throw "Node.js must be the fixed working Windows x64 runtime $NodeTag. Found version=$DetectedNodeVersion architecture=$NodeArch"
    }

    $NodeSignature = Get-AuthenticodeSignature -LiteralPath $NodeExe
    if ($NodeSignature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Node.js Authenticode signature is not valid: $($NodeSignature.Status)"
    }
    $NodeSigner = [string]$NodeSignature.SignerCertificate.Subject
    if ($NodeSigner -notmatch "OpenJS Foundation") {
        throw "Node.js signer is not the OpenJS Foundation: $NodeSigner"
    }

    $SourceRuntimeRoot = Join-Path $ResolvedProjectRoot "source_runtime"
    $PackageLockPath = Join-Path $SourceRuntimeRoot "package-lock.json"
    if (-not (Test-Path -LiteralPath $PackageLockPath -PathType Leaf)) {
        throw "The locked Node dependency manifest is missing: $PackageLockPath"
    }
    Push-Location $SourceRuntimeRoot
    try {
        & $NpmCommand ci --omit=dev --no-audit --no-fund | ForEach-Object { Write-Host ([string]$_) }
        $NpmCiExitCode = $LASTEXITCODE
        if ($NpmCiExitCode -ne 0) {
            throw "npm ci failed for the locked production Node dependency tree."
        }
        & $NpmCommand ls --omit=dev --all | ForEach-Object { Write-Host ([string]$_) }
        $NpmListExitCode = $LASTEXITCODE
        if ($NpmListExitCode -ne 0) {
            throw "The locked production Node dependency tree did not pass npm ls."
        }
    } finally {
        Pop-Location
    }

    [PSCustomObject]@{
        NodeExe             = [System.IO.Path]::GetFullPath($NodeExe)
        NpmCommand          = [System.IO.Path]::GetFullPath($NpmCommand)
        LicensePath         = [System.IO.Path]::GetFullPath($LicensePath)
        Version             = $DetectedNodeVersion
        Architecture        = $NodeArch
        Signer              = $NodeSigner
        ArchiveUrl          = $NodeArchiveUrl
        ArchiveSha256       = $ArchiveSha256
        NodeExeSha256       = $NodeExeSha256
        LicenseSha256       = (Get-FileHash -LiteralPath $LicensePath -Algorithm SHA256).Hash.ToUpperInvariant()
    }
}
