# 启动打包版、验证单实例与截图，然后优雅关闭。
$ErrorActionPreference = "Stop"
$root = "F:\Projects\HushPlayer-Reimagined"
# The repo folder inherits a Low integrity label, and Windows refuses tray-icon
# registration from low-integrity processes.  Verify from a normal (Medium)
# folder so the run matches what users get after extracting the zip.
$mediumOutput = "F:\HushPlayerBuild\out\HushPlayer"
$sourceDir = if (Test-Path $mediumOutput) {
    $mediumOutput
} else {
    Join-Path $root "packaging\out\HushPlayer"
}
$medium = "F:\HushPlayerBuild\verify"
if (Test-Path $medium) { Remove-Item $medium -Recurse -Force }
New-Item -ItemType Directory -Force $medium | Out-Null
Copy-Item (Join-Path $sourceDir "*") $medium -Recurse -Force
$exe = Join-Path $medium "HushPlayer.exe"
$data = Join-Path $root "artifacts\packaged_run"
if (Test-Path $data) { Remove-Item $data -Recurse -Force }
New-Item -ItemType Directory -Force $data | Out-Null
# Deterministic close behaviour for automation: quit on close, no dialog.
$settingsJson = '{"general": {"close_action": "quit", "close_prompt_migrated": true}}'
Set-Content -Path (Join-Path $data "settings.json") -Value $settingsJson -Encoding UTF8
# Never kill a HushPlayer the user may have open; the isolated mutex below
# lets this verification run alongside it.

function Start-App {
    $cmd = "cmd.exe /c set HUSHPLAYER_DATA_DIR=$data&& set HUSH_CONSOLE=0&& set HUSHPLAYER_MUTEX_SUFFIX=-verify&& set HUSHPLAYER_NO_CLOSE_PROMPT=1&& `"$exe`""
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd }
    return $r.ProcessId
}
function Get-AppProcess($launcherPid, $timeout = 20) {
    $deadline = (Get-Date).AddSeconds($timeout)
    while ((Get-Date) -lt $deadline) {
        $child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$launcherPid" |
            Where-Object { $_.Name -eq "HushPlayer.exe" } | Select-Object -First 1
        if ($child) { return Get-Process -Id $child.ProcessId }
        Start-Sleep -Milliseconds 400
    }
    return $null
}

function Wait-Process2($name, $timeout = 30) {
    $deadline = (Get-Date).AddSeconds($timeout)
    while ((Get-Date) -lt $deadline) {
        $p = Get-Process $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($p) { return $p }
        Start-Sleep -Milliseconds 300
    }
    return $null
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
Add-Type -AssemblyName System.Drawing

# The close dialog defaults to "ask"; make the automated check deterministic.
$settingsPath = Join-Path $data "settings.json"
if (-not (Test-Path $settingsPath)) {
    New-Item -ItemType Directory -Force -Path $data | Out-Null
    '{"general":{"close_action":"quit"}}' | Set-Content -Path $settingsPath -Encoding UTF8
}

Write-Host "==> 启动第一个实例"
$pid1 = Start-App
Start-Sleep -Seconds 3
$proc = Get-AppProcess $pid1
if (-not $proc) { throw "第一个实例没有启动" }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
# The window may not exist yet on a fast start; poll instead of reading once.
for ($i = 0; $i -lt 40 -and ($hwnd -eq [IntPtr]::Zero); $i++) {
    Start-Sleep -Milliseconds 500
    $proc.Refresh()
    $hwnd = $proc.MainWindowHandle
}
if ($hwnd -eq [IntPtr]::Zero) { throw "窗口没有出现" }
Write-Host "pid=$($proc.Id) hwnd=$hwnd title=$($proc.MainWindowTitle)"

$log = Join-Path $data "logs\hushplayer.log"
if (Test-Path $log) {
    Write-Host "==> 日志尾部"
    Get-Content $log -Tail 12 | ForEach-Object { "  $_" }
}

$rect = New-Object W+RECT
[void][W]::GetWindowRect($hwnd, [ref]$rect)
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
Write-Host "window=${w}x${h} at $($rect.Left),$($rect.Top)"
    # Focus stealing prevention can ignore SetForegroundWindow when the terminal
    # owns the foreground; raise the window explicitly and capture it with
    # PrintWindow so the shot shows the app even when a browser is on top.
    [void][W]::ShowWindow($hwnd, 5)
    [void][W]::BringWindowToTop($hwnd)
    [void][W]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 900
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    $captured = [W]::PrintWindow($hwnd, $hdc, 2)
    $g.ReleaseHdc($hdc)
    if (-not $captured) {
        Write-Host "PrintWindow failed, falling back to screen capture"
        $g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
    }
$shot = Join-Path $root "artifacts\shots\packaged_run.png"
$bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "screenshot=$shot"

Write-Host "==> 启动第二个实例（应立刻退出并把第一个窗口置前）"
$pid2 = Start-App
Start-Sleep -Seconds 5
$firstAlive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
$secondAlive = Get-AppProcess $pid2 3
$count = [int][bool]$firstAlive + [int][bool]$secondAlive
Write-Host "instances=$count second_cmd_pid_alive=$([bool]$secondAlive)"
$req = Join-Path $data "activate.request"
Write-Host "activate_request_exists=$(Test-Path $req)"

Write-Host "==> 发送 WM_CLOSE 关闭"
[void][W]::PostMessage($proc.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
Start-Sleep -Seconds 4
$still = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
Write-Host "alive_after_close=$([bool]$still)"
if ($still) { $still | Stop-Process -Force }
if (Test-Path $log) {
    Write-Host "==> 退出日志尾部"
    Get-Content $log -Tail 8 | ForEach-Object { "  $_" }
}
