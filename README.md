# HushPlayer

HushPlayer 的 Windows 开发与打包环境使用 64 位 CPython 3.13。项目根目录中的 `.venv` 是脚本唯一默认使用的 Python 环境；构建脚本不会静默改用系统 Python。

## 运行与源码入口

在实际项目根目录（当前工作区为 `F:\Projects\HushPlayer`）执行：

```powershell
.\.venv\Scripts\python.exe main.py
```

- `main.py`：正式入口，默认加载真实音乐库；`--mock` 使用开发演示数据。
- `app/ui_v2/shell/main_window.py`：正式 UI V2 主窗口。
- `app/ui_v2/adapters/`：列表、设置、歌词和播放的界面适配层。
- `app/services/`：音乐库读取、扫描、播放控制、缓存和更新服务。
- `CHANGELOG.md`：用户可见更新日志；开发中的改进记录在“未发布”。

已有 `.venv` 与文档目标版本不一致时，先记录实际版本。可用环境可以执行本地检查，但不代表通过 CPython 3.13 的打包验收；不要因此自动重建环境或升级依赖。

## 创建开发环境

先确认使用的是 64 位 Python 3.13。若 Python 安装在默认的当前用户目录，可在项目根目录执行：

```powershell
$Python313 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
& $Python313 --version
& $Python313 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --require-hashes --requirement requirements-lock.txt
```

如果 Python 安装在其他位置，请将 `$Python313` 设置为实际的 Python 3.13 x64 可执行文件。不要在已有损坏环境上修补；先将旧 `.venv` 重命名为唯一的备份名称。

- `requirements.txt` 记录应用运行依赖。
- `requirements-lock.txt` 是经过验证的 CPython 3.13 / Windows x64 开发与打包锁文件，包含精确版本和哈希。

## 验证环境

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app tests
```

本轮稳定性回归检查使用临时应用数据和缓存目录，不读取或改写默认用户曲库；检查完成返回退出码 `0` 才代表通过：

```powershell
.\.venv\Scripts\python.exe -m tests.run_stability_checks
```

该入口覆盖设置文件保护、音乐库容错、封面缓存、歌曲排序、歌单、播放状态和关闭行为，不等于完整发布验收。实际音频输出、桌面歌词及多屏效果仍需人工检查，步骤见 [稳定性改进说明](docs/superpowers/specs/2026-09-08-stability-optimizations-design.md)。

构建脚本可从任意工作目录调用。诊断模式只检查项目根目录、`.venv`、依赖锁、Node 运行时准备入口和 PyInstaller spec，不下载 Node、不清理输出目录，也不生成安装包：

```powershell
.\packaging\build_windows_debug.ps1 -DiagnosticOnly
.\packaging\build_windows_release.ps1 -DiagnosticOnly
.\packaging\build_windows_installer.ps1 -DiagnosticOnly
```

正式生成安装程序时，先运行 release 构建，再调用安装器脚本。版本号和安装器文件名都由 `app/core/version.py` 生成，不要直接修改 Inno Setup 文件中的版本：

```powershell
.\packaging\build_windows_release.ps1
.\packaging\build_windows_installer.ps1
```
