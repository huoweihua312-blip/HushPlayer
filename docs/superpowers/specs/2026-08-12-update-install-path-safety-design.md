# 更新路径与测试安装保护设计

## 背景

旧版 HushPlayer 在缺少 `HushPlayerUpdater.exe` 时会回退到启动 Inno Setup 安装包。当前安装脚本使用 `UsePreviousAppDir=yes`，因此可能读取当前用户注册表中的历史安装目录，而不是使用正在运行的 `HushPlayer.exe` 所在目录。测试安装目录位于 `build\install-*` 下时，发布构建脚本又会递归清理整个 `build`，造成测试基线被删除。

## 目标

1. 安装包回退更新必须优先使用当前运行的打包程序目录。
2. 发布和 debug 构建不得递归删除测试安装目录。
3. `F:\HushPlayer` 等项目外测试基线不被任何项目清理逻辑触碰。
4. 不改变正式安装包的固定 `AppId`、用户数据目录或应用内 ZIP 更新流程。

## 方案

### 更新器

`AppUpdateService.launch_verified_installer()` 在校验安装包后解析 `_application_install_dir()`。冻结程序使用 `sys.executable` 的父目录；测试注入的 `application_dir` 继续使用显式覆盖值。启动 Inno Setup 时，在既有参数后追加 `/DIR="<当前安装目录>"`，让安装包回退路径不再受旧的 `UsePreviousAppDir` 注册表值影响。

该参数只影响安装包回退路径。包含 `HushPlayerUpdater.exe` 的新版仍使用现有应用内更新助手，并在原安装目录内完成替换。

### 构建清理

发布和 debug 脚本不再删除整个 `build` 与 `dist`。改为只删除明确的生成目录：PyInstaller 工作目录、版本元数据目录、发布清单目录，以及可安全重建的 `dist\HushPlayer`。保留 `build\install-*`、smoke 安装目录、正式安装包和其他用户可能正在测试的目录。

### 测试

- 更新器单元/冒烟测试验证安装包启动参数包含当前安装目录。
- 构建脚本静态测试验证不再包含对整个 `build`/`dist` 的递归删除。
- 运行 Python 编译、更新器冒烟测试和打包脚本静态检查。

## 失败处理

- 当前安装目录无法解析时，沿用现有异常信号，不启动安装程序。
- 安装程序拒绝 `/DIR` 或启动失败时，保留当前应用并通过现有失败信号报告。
- 本次不删除任何已有目录，不修改注册表，不改变正式发布包。

## 回滚

只需回滚本次更新器、构建脚本和测试文件的提交；不会触碰 `F:\HushPlayer`、用户数据、远端 Release 或 Git 标签。
