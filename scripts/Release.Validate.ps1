[CmdletBinding()]
param([string]$Version,[string]$NumericVersion,[string]$SourceCommit,[string]$PreviousVersion,[string]$ReleaseChannel,[string]$OutputPath)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Release.Common.ps1')
Assert-ReleaseInputs $Version $NumericVersion $SourceCommit $PreviousVersion $ReleaseChannel
Write-ReleaseJson $OutputPath ([ordered]@{version=$Version;numeric_version=$NumericVersion;source_commit=$SourceCommit.ToLowerInvariant();previous_version=$PreviousVersion;release_channel=$ReleaseChannel;validated=$true})
