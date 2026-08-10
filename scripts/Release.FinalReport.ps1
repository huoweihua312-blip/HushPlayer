[CmdletBinding()]
param([string]$ArtifactRoot,[string]$OutputPath,[string]$Status='partial')
$ErrorActionPreference='Stop'; . (Join-Path $PSScriptRoot 'Release.Common.ps1')
$metaPath=Join-Path $ArtifactRoot 'release-metadata.json'; $meta=if(Test-Path $metaPath){Read-ReleaseJson $metaPath}else{$null}
Write-ReleaseJson $OutputPath ([ordered]@{status=if($meta){'completed'}else{$Status};version=if($meta){$meta.version}else{$null};sha256=if($meta){$meta.sha256}else{$null};remote_writes=$false})
