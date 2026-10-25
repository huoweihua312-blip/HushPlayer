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
# Stage on the repo's own drive (never the system drive): this folder has no
# Low integrity label, so the produced exe is a normal Medium process and the
# shell accepts its tray icon.
$buildRoot = "F:\HushPlayerBuild"
$buildOut = Join-Path $buildRoot "out"
New-Item -ItemType Directory -Force $buildOut | Out-Null
$versionForPath = (& $python -c "import sys; sys.path.insert(0,'.'); from hushplayer.version import VERSION; print(VERSION)").Trim()
$dist = Join-Path $buildOut "HushPlayer"
if (Test-Path $dist) {
    try {
        Remove-Item $dist -Recurse -Force -ErrorAction Stop
    } catch {
        # A running copy locks its files; stage this build next to it instead of
        # killing the user's session.
        $dist = Join-Path $buildOut ("HushPlayer-" + $versionForPath)
        Write-Host "==> 旧目录正在使用，输出到 $dist" -ForegroundColor Yellow
        if (Test-Path $dist) { Remove-Item $dist -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
Copy-Item $staged $dist -Recurse -Force

# 剪掉未使用的 Qt 组件（QML/Quick/Pdf 在本项目里 0 引用）。
# 保留 Qt6Multimedia/Qt6Network/opengl32sw（软件 GL 兜底）与 avcodec（解码）。
$unused = @(
    "Qt6Quick.dll", "Qt6QuickWidgets.dll", "Qt6Qml.dll", "Qt6QmlModels.dll",
    "Qt6QmlWorkerScript.dll", "Qt6Pdf.dll", "Qt6PdfWidgets.dll"
)
$trimmed = 0L
foreach ($name in $unused) {
    $file = Join-Path $dist "_internal\PySide6\$name"
    if (Test-Path $file) { $trimmed += (Get-Item $file).Length; Remove-Item $file -Force }
}
foreach ($rel in @("_internal\PySide6\plugins\imageformats\qpdf.dll", "_internal\PySide6\plugins\qmltooling")) {
    $target = Join-Path $dist $rel
    if (Test-Path $target) {
        if ((Get-Item $target).PSIsContainer) {
            $trimmed += (Get-ChildItem $target -Recurse -File | Measure-Object Length -Sum).Sum
            Remove-Item $target -Recurse -Force
        } else {
            $trimmed += (Get-Item $target).Length
            Remove-Item $target -Force
        }
    }
}
if ($trimmed -gt 0) { Write-Host ("==> 已裁剪未使用组件：{0:N1} MB" -f ($trimmed / 1MB)) -ForegroundColor DarkGray }
$label = (icacls (Join-Path $dist "HushPlayer.exe") | Select-String "Mandatory Label")
$labelText = if ($label) { $label.Line.Trim() } else { "no mandatory label (Medium)" }
$sizeMb = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "==> 完成：$dist（$sizeMb MB）" -ForegroundColor Green
Write-Host "    完整性：$labelText" -ForegroundColor DarkGray
Write-Host "    （输出固定在本机 F: 盘，不写入 C:）" -ForegroundColor DarkGray

if ($Zip) {
    $version = (& $python -c "import sys; sys.path.insert(0,'.'); from hushplayer.version import VERSION; print(VERSION)").Trim()
    $zipPath = Join-Path $buildOut "HushPlayer-$version-win64.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path $dist -DestinationPath $zipPath -CompressionLevel Optimal
    $hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash
    "$hash  HushPlayer-$version-win64.zip" | Set-Content (Join-Path $buildOut "SHA256SUMS.txt") -Encoding ascii
    Write-Host "==> 压缩包：$zipPath" -ForegroundColor Green
    Write-Host "    SHA256: $hash"
}
