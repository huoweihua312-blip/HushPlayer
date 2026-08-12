# HushPlayer 应用内更新设计

## 目标

让 HushPlayer 在应用内完成更新下载和校验。用户点击更新后，应用自动退出，由一个独立的更新助手替换程序文件并重新启动 HushPlayer；用户不再需要手动操作 Inno Setup 安装向导。

## 范围

- 更新清单继续使用 HTTPS、版本比较和 SHA-256 校验。
- 在清单中增加可选的 portable update package 字段。
- 新版本优先下载并应用 portable package。
- 旧清单或没有 portable package 的版本继续使用现有安装包流程。
- 更新助手只替换安装目录中的程序文件，不访问或删除用户数据目录。
- 用户数据继续由 `AppPaths.application_data_dir` 管理，和安装目录分离。

## 更新流程

1. `AppUpdateService` 检查清单。
2. 如果清单包含完整的 portable package 元数据，更新对话框显示应用内更新并下载 ZIP；否则显示兼容的安装包下载。
3. 下载到用户可写的临时更新目录，限制大小、响应类型、ZIP 路径和 SHA-256。
4. 更新前再次校验下载文件，并复制已打包的 `HushPlayerUpdater.exe` 到临时目录，避免更新助手被自身所在安装目录锁定。
5. 更新助手接收当前进程 PID、安装目录、ZIP 路径和重启程序路径。
6. HushPlayer 退出并释放媒体播放器、Node/QProcess 等子进程。
7. 更新助手等待父进程退出，将 ZIP 解压到安装目录旁的 staging 目录，检查主程序存在后交换目录，并启动新版本。
8. 失败时保留旧安装目录，并写入错误日志；不删除用户数据。旧版本可继续使用。

## 清单兼容性

以下字段成组出现，全部存在时才启用应用内更新：

- `package_url`
- `package_size`
- `package_sha256`
- `package_filename`

这四个字段全部缺失时视为旧清单，继续使用 `setup_url`、`setup_size` 和 `sha256`。只出现部分字段属于无效清单，避免在发布配置不完整时误启用更新。

portable ZIP 的文件名必须匹配当前版本和架构，内容必须包含 `HushPlayer.exe` 和 `HushPlayerUpdater.exe`，且不能包含绝对路径、父目录路径或安装目录外的目标。

## 更新助手与安全边界

- 更新助手是独立的 PyInstaller Windows GUI 可执行文件，随发布目录提供。
- 更新助手运行时不依赖项目虚拟环境或用户安装的 Python。
- 更新包和清单都来自现有 HTTPS 更新源，并继续执行 SHA-256 校验。
- 更新助手不以管理员权限运行；当前安装目录是用户目录下的 `{localappdata}\\Programs\\HushPlayer`。
- 更新助手只接受由应用生成的绝对路径，并验证安装目录、临时目录和 ZIP 成员路径。
- 不覆盖 `AppData` 用户数据，不修改 Git、远端 Release 或用户媒体文件。

## 回退策略

- 旧客户端读取新清单时只使用原有安装包字段。
- 新客户端读取旧清单时自动使用 Inno Setup fallback。
- portable package 下载、校验或更新助手启动失败时，不关闭应用，保留原有安装包更新按钮。
- 目录交换失败时不删除旧安装目录，并报告需要重试或使用安装包更新。

## 影响范围

- `app/services/app_update_service.py`：可选 package 字段、下载/校验和更新助手启动。
- `app/ui/update_dialog.py`：区分应用内更新和旧安装包更新，更新提示和按钮文案。
- `packaging/hushplayer_updater.py` 与 updater spec：独立更新助手。
- `packaging/build_windows_release.ps1`、更新清单生成器和发布测试：生成 portable ZIP 并写入可选字段。
- 新增单元/冒烟测试覆盖清单兼容、ZIP 安全校验、更新任务和旧安装包 fallback。

## 不在本轮范围

- 不改变用户数据 JSON 结构。
- 不删除或替换现有 Inno Setup 发布流程。
- 不自动发布新版本、创建 Git tag 或推送 Release。
- 不在应用运行期间覆盖正在使用的 EXE/DLL；始终通过独立更新助手完成交换。
