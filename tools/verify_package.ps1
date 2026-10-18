# 启动打包版、验证单实例与截图，然后优雅关闭。
$ErrorActionPreference = "Stop"
$root = "F:\Projects\HushPlayer-Reimagined"
$exe = Join-Path $root "packaging\out\HushPlayer\HushPlayer.exe"
$data = Join-Path $root "artifacts\packaged_run"
New-Item -ItemType Directory -Force $data | Out-Null
Get-Process HushPlayer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

function Start-App {
    $cmd = "cmd.exe /c set HUSHPLAYER_DATA_DIR=$data&& set HUSH_CONSOLE=0&& `"$exe`""
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd }
    return $r.ProcessId
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
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
Add-Type -AssemblyName System.Drawing

Write-Host "==> 启动第一个实例"
$pid1 = Start-App
Start-Sleep -Seconds 9
$proc = Get-Process HushPlayer -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) { throw "第一个实例没有启动" }
$proc.Refresh()
$hwnd = $proc.MainWindowHandle
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
[void][W]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 700
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
$shot = Join-Path $root "artifacts\shots\packaged_run.png"
$bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "screenshot=$shot"

Write-Host "==> 启动第二个实例（应立刻退出并把第一个窗口置前）"
$pid2 = Start-App
Start-Sleep -Seconds 5
$count = (Get-Process HushPlayer -ErrorAction SilentlyContinue | Measure-Object).Count
$secondAlive = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
Write-Host "instances=$count second_cmd_pid_alive=$([bool]$secondAlive)"
$req = Join-Path $data "activate.request"
Write-Host "activate_request_exists=$(Test-Path $req)"

$proc = Get-Process HushPlayer -ErrorAction SilentlyContinue | Select-Object -First 1
Write-Host "==> 发送 WM_CLOSE 关闭"
[void][W]::PostMessage($proc.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
Start-Sleep -Seconds 4
$still = Get-Process HushPlayer -ErrorAction SilentlyContinue
Write-Host "alive_after_close=$([bool]$still)"
if ($still) { $still | Stop-Process -Force }
if (Test-Path $log) {
    Write-Host "==> 退出日志尾部"
    Get-Content $log -Tail 8 | ForEach-Object { "  $_" }
}
