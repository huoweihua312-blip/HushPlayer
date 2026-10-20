# 构建 HushPlayer Windows 发行版。
#
# 用法：
#   pwsh -File packaging/build.ps1              # 构建 onedir 目录版
#   pwsh -File packaging/build.ps1 -Zip         # 额外生成 zip 压缩包
#
# 产出：packaging/out/HushPlayer/HushPlayer.exe
param(
    [switch]$Zip,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "==> 版本信息" -ForegroundColor Cyan
& $python tools\make_versioninfo.py

if (-not $SkipTests) {
    Write-Host "==> 运行测试" -ForegroundColor Cyan
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "测试未通过，已停止打包。" }
}

$node = Join-Path $root "hushplayer\runtime\node\node.exe"
if (-not (Test-Path $node)) {
    Write-Host "==> 下载内置 Node.js 运行时" -ForegroundColor Cyan
    $nodeVersion = "22.22.3"
    $zip = Join-Path $root "packaging\node-v$nodeVersion-win-x64.zip"
    if (-not (Test-Path $zip)) {
        Invoke-WebRequest -Uri "https://nodejs.org/dist/v$nodeVersion/node-v$nodeVersion-win-x64.zip" -OutFile $zip -UseBasicParsing
    }
    $tmp = Join-Path $root "packaging\_node_tmp"
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force (Split-Path $node) | Out-Null
    Copy-Item (Join-Path $tmp "node-v$nodeVersion-win-x64\node.exe") $node -Force
    Remove-Item -Recurse -Force $tmp
}

Write-Host "==> PyInstaller" -ForegroundColor Cyan
# PyInstaller runs under the (possibly low-integrity) venv interpreter, so it
# must write inside the repo.  Right after the build this script — running as
# the normal user — copies the result to a Medium integrity folder, because an
# exe created inside this repo inherits its Low label and Windows then refuses
# tray-icon registration for it.
& $python -m PyInstaller packaging\hushplayer.spec --noconfirm --distpath packaging\out --workpath packaging\build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

$staged = Join-Path $root "packaging\out\HushPlayer"
$buildRoot = Join-Path $env:LOCALAPPDATA "HushPlayerBuild"
$buildOut = Join-Path $buildRoot "out"
$dist = Join-Path $buildOut "HushPlayer"
New-Item -ItemType Directory -Force $buildOut | Out-Null
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
Copy-Item $staged $dist -Recurse -Force
$label = (icacls (Join-Path $dist "HushPlayer.exe") | Select-String "Mandatory Label")
$labelText = if ($label) { $label.Line.Trim() } else { "no mandatory label (Medium)" }
$sizeMb = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "==> 完成：$dist（$sizeMb MB）" -ForegroundColor Green
Write-Host "    完整性：$labelText" -ForegroundColor DarkGray

if ($Zip) {
    $version = (& $python -c "import sys; sys.path.insert(0,'.'); from hushplayer.version import VERSION; print(VERSION)").Trim()
    $zipPath = Join-Path $buildOut "HushPlayer-$version-win64.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path $dist -DestinationPath $zipPath -CompressionLevel Optimal
    $hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash
    $repoOut = Join-Path $root "packaging\out"
    New-Item -ItemType Directory -Force $repoOut | Out-Null
    Copy-Item $zipPath (Join-Path $repoOut (Split-Path $zipPath -Leaf)) -Force
    "$hash  HushPlayer-$version-win64.zip" | Set-Content (Join-Path $repoOut "SHA256SUMS.txt") -Encoding ascii
    Write-Host "==> 压缩包：$zipPath" -ForegroundColor Green
    Write-Host "    (副本：packaging\out)" -ForegroundColor DarkGray
    Write-Host "    SHA256: $hash"
}
