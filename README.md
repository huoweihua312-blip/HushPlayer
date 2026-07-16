# HushPlayer

HushPlayer 的 Windows 开发与打包环境使用 64 位 CPython 3.12。项目根目录中的 `.venv` 是脚本唯一默认使用的 Python 环境；构建脚本不会静默改用系统 Python。

## 创建开发环境

先确认使用的是 64 位 Python 3.12。若 Python 安装在默认的当前用户目录，可在项目根目录执行：

```powershell
$Python312 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
& $Python312 --version
& $Python312 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install --require-hashes --requirement requirements-lock.txt
```

如果 Python 安装在其他位置，请将 `$Python312` 设置为实际的 Python 3.12 x64 可执行文件。不要在已有损坏环境上修补；先将旧 `.venv` 重命名为唯一的备份名称。

- `requirements.txt` 记录应用运行依赖。
- `requirements-lock.txt` 是经过验证的 CPython 3.12 / Windows x64 开发与打包锁文件，包含精确版本和哈希。

## 验证环境

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app tests
```

构建脚本可从任意工作目录调用。诊断模式只检查项目根目录、`.venv`、依赖锁、Node 运行时准备入口和 PyInstaller spec，不下载 Node、不清理输出目录，也不生成安装包：

```powershell
.\packaging\build_windows_debug.ps1 -DiagnosticOnly
.\packaging\build_windows_release.ps1 -DiagnosticOnly
```
