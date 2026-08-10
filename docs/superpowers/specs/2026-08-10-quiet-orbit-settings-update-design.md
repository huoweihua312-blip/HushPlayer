# Quiet Orbit 设置页在线更新入口设计

## 问题

Quiet Orbit 的 `LegacySettingsBridge` 没有注册 `check_updates` 操作，设置界面因此按现有可用性规则禁用了“检查更新”按钮。旧版更新服务仍然可用，但没有接入 Quiet Orbit 设置层。

## 方案

在 Quiet Orbit 主窗口中创建并持有现有 `AppUpdateService`，将一个 `check_updates` 回调注册到 `LegacySettingsBridge`。按钮点击后调用真实的多源 manifest 检查：GitCode 优先，GitHub 备用。检查结果写回设置层状态；发现新版本时复用既有 `UpdateDialog`，下载仍由 `AppUpdateService` 负责大小、文件头和 SHA-256 校验。

更新服务随 Quiet Orbit 主窗口关闭而停止。不会引入新的持久化字段，不改变播放、队列、歌词或更新清单格式。

## 验收

- Quiet Orbit 设置页的“检查更新”按钮可用。
- 当前版本能够显示“已是最新版本”。
- 主源失败时能够切换 GitHub 备用源。
- 使用旧版本安装包时能够下载并校验最新版安装包。
- 有代理和无代理环境下均能完成 manifest 检查与安装包校验。
