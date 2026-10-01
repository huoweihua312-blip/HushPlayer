# Velopack 并行更新原型

这条链路用于 HushPlayer 的静默更新安装与更新。正式 Inno Setup 流程仍保留为用户主动选择或静默更新失败时的备用路径。Velopack 安装包默认使用当前用户的本地应用目录，不提供目录选择页；需要选择 D/F 等本地磁盘时，应使用 Inno Setup 安装包。

## 原型目标

- 使用按版本目录安装，避免直接覆盖正在运行的 `HushPlayer.exe`。
- 让更新助手独立于播放器进程完成替换和重启。
- 使用 Velopack 的增量包与更新清单，减少重复下载。
- 保留当前 Inno Setup 更新链路作为回退，直到跨电脑验收完成。

## 前置条件

需要在专用的构建环境中准备，并在执行 `build_windows_release.ps1` 之前完成安装：

1. 项目现有的 Python 3.13 x64 环境。
2. Python 包 `velopack`。
3. .NET SDK 和 Velopack 的 `vpk` 工具。

这些依赖已经锁定到正式 Windows 构建环境，避免测试包与正式包使用不同的更新运行时。

## 构建方式

先生成当前 PyInstaller `onedir` 目录：

```powershell
.\packaging\build_windows_release.ps1
```

然后生成 Velopack 安装包和更新包：

```powershell
.\packaging\build_velopack_release.ps1
```

如果希望脚本先构建当前 release 目录：

```powershell
.\packaging\build_velopack_release.ps1 -BuildRelease
```

只检查环境而不构建：

```powershell
.\packaging\build_velopack_release.ps1 -DiagnosticOnly
```

输出默认位于 `dist\velopack`。当前脚本不会删除已有输出，也不会修改现有 `updates\beta` 清单。

## 启动桥接

`main.py` 只在以下情况调用 Velopack 的早期启动桥接：

- 当前可执行文件旁边存在 Velopack 的 `Update.exe` 和 `sq.version`；或
- 测试时显式设置 `HUSHPLAYER_ENABLE_VELOPACK=1`。

源代码运行和 Inno Setup 安装默认保持传统更新行为；Velopack 安装会启用静默更新。若需要强制关闭 Velopack 桥接，可设置 `HUSHPLAYER_DISABLE_VELOPACK=1`。

## 本机更新链路测试

更新源可以通过 `HUSHPLAYER_VELOPACK_UPDATE_SOURCE` 临时注入，便于本机验收；正式 Velopack 包默认使用 HushPlayer GitHub Release 更新源。可以把 `dist\velopack` 目录作为本机静态更新源：

```powershell
python -m http.server 8765 --directory F:\Projects\HushPlayer\dist\velopack
```

然后在另一个 PowerShell 窗口中启动已安装的 Velopack 版本：

```powershell
$env:HUSHPLAYER_VELOPACK_UPDATE_SOURCE = "http://127.0.0.1:8765"
Start-Process "F:\HushPlayer Application\HushPlayer\HushPlayer.exe"
```

如果当前包与更新源版本相同，设置中的“检查更新”应显示已是最新版本。要测试真正的下载、重启和回滚流程，需要准备一个版本号更高的测试包，并将其与现有包分开保存；不能用相同版本覆盖测试。更新完成后可以选择“使用安装向导”作为备用路径。

## 验收顺序

1. 在测试电脑上全新安装原型包。
2. 验证设置、音乐库、歌单、收藏、缓存和桌面歌词数据仍然保留在用户数据目录。
3. 在播放器播放本地歌曲、在线歌曲、歌词和桌面歌词时退出，再执行更新。
4. 验证更新过程中不需要手动删除旧目录，不弹出文件占用错误。
5. 验证更新失败后仍能启动旧版本，并可从更新提示中选择传统安装向导作为回退。
6. 连续执行两次更新，确认快捷方式和启动入口始终指向当前版本。

通过上述验收前，不删除现有安装包和更新助手。正式 Inno Setup 安装包仍显示目录选择页；用户选择的目录由传统更新路径沿用，Velopack 测试包则使用独立的按版本目录。
