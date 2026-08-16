# HushPlayer 窗口关闭与后台托盘设计

## 目标

为正式 UI V2 增加后台播放能力：点击窗口 X 时，在可用系统托盘环境中询问“直接退出”或“最小化到托盘”；用户可以勾选“记住我的选择”，并在设置的“常规”分类中关闭这项记忆。最小化到托盘只隐藏主窗口，不停止播放器、播放队列、歌词或在线服务。

## 方案

新增 `CloseBehaviorController` 作为应用生命周期控制器。它由 `QApplication` 持有，负责：

- 创建和管理 `QSystemTrayIcon`、托盘菜单及恢复窗口动作。
- 处理主窗口 `closeEvent`，区分询问、直接退出和最小化到托盘。
- 通过现有 `settings.json` 读写 `close_behavior` 和 `remember_close_choice`，保留未知设置字段。
- 为更新安装等内部退出路径提供一次性 bypass，避免重复弹出关闭询问。

主窗口只负责把关闭事件交给控制器，并且只在控制器确认真正退出后执行播放器、扫描、在线服务和窗口资源收尾。托盘隐藏路径不执行这些 shutdown 操作。

## 用户行为

- 默认 `remember_close_choice=false`、`close_behavior=ask`，首次点击 X 弹出选择。
- 弹窗提供“直接退出”“最小化到托盘”“取消”和“记住我的选择”。
- 勾选后保存本次动作；再次点击 X 直接执行已保存动作。
- “常规”设置增加“记住关闭窗口时的选择”；关闭并保存后清除动作记忆，恢复每次询问。
- 托盘菜单提供“打开 HushPlayer”和“退出 HushPlayer”。
- 系统托盘不可用时显示提示并直接退出，不尝试隐藏窗口。

## 数据兼容

只在现有 `settings.json` 增加向后兼容字段：

```json
{
  "remember_close_choice": false,
  "close_behavior": "ask"
}
```

旧设置缺少字段时使用安全默认值；关闭记忆时将 `close_behavior` 归一化为 `ask`。不修改 `library.json`、`playlists.json` 或 `stats.json`。

## 验证

新增控制器单元测试和设置兼容测试，覆盖：默认询问、记忆退出、记忆托盘、取消记忆、托盘恢复、真正退出时才执行资源收尾，以及系统托盘不可用分支。保留现有播放、歌词、在线播放和设置回归测试。
