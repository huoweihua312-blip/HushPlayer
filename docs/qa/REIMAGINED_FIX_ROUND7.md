# 第七轮反馈整改（v1.0.8）

反馈来源：用户 2026-10-19 截图 + 「添加 MusicFree 兼容插件时，点击添加音源报错。可以在 github 搜索
MusicFree 源码。」

## 现象

设置 → 在线音源 → 「添加音源…」立即弹出应用异常对话框：

```
NameError: name 'QFileDialog' is not defined
  File "hushplayer/ui/pages/settings.py", line 698, in _add_source
```

## 根因

`_add_source()` 直接调用了 `QFileDialog.getOpenFileName(...)`，但 `settings.py` 顶部只导入了
`QApplication/QHBoxLayout/QLabel/QScrollArea/QStackedWidget/QVBoxLayout/QWidget`——没有
`QFileDialog`。异常发生在按钮 clicked 槽里，因此表现为「点一下弹窗」，而不是启动即崩。

顺带发现「从链接添加」在方法内部临时 import `QInputDialog`，风格不一致；统一移到顶部。

## 修复

| 文件 | 改动 |
| --- | --- |
| `hushplayer/ui/pages/settings.py` | 顶部导入 `QFileDialog / QInputDialog / QMessageBox`；`_add_source()` 只负责选文件，安装与提示交给新的 `_install_source_file(path)`，与「从链接添加」共用同一套异常处理。 |
| `hushplayer/online/registry.py` | 新增 `peek_plugin_metadata(raw)`：不执行插件，仅从头部 8 KB 解析 `platform / version / author` 字面量；`install_file()` 用它设置 `name/version/author`，解析不到时回退文件名。 |

### 关于 MusicFree 兼容性

本项目运行时（`hushplayer/runtime/source_runtime/plugin_host.js`）本来就按 MusicFree 插件约定加载：
`require()` 插件文件、提供 `global.env`、允许 `axios / cheerio / crypto-js / dayjs / he / qs` 等依赖，
并同时支持 `search / getMediaSource / getLyric / getAlbumInfo…`。所以「装不上」完全是 UI 层的导入错误，
不是插件格式不兼容。安装后插件会被复制到可写目录 `%LOCALAPPDATA%\HushPlayerReimagined\sources\user_sources\`，
不修改打包内置的原始插件。

## 验证

- 新增 `tests/test_source_registry.py`：
  - `peek_plugin_metadata` 能读出 `测试音乐 / 0.1.2 / qa`；
  - 安装一个 MusicFree 风格插件 → 条目名取自 `platform`、文件落到 `user_sources/`、重复安装被拒；
  - `remove()` 后注册表与文件同时清理；
  - 拒绝 `.txt` 与 >2 MB 文件。
- 真实 GUI 探针 `tools/probe_r8_source.py`：
  1. 打开设置 → 在线音源；
  2. 安装 `artifacts/qa/r8/plugin.js`（`module.exports = { platform: "本地测试源", search(), getMediaSource() }`）；
  3. 列表刷新并出现「本地测试源」；
  4. 通过运行时 `client.search("user_source_69b91cc3c141", "你好")` 返回 `ok=True, 1 item`；
  5. `errors 0`，截图 `docs/screenshots/settings_installed_source.png`。
- 全量测试：**133 passed / 0 failed / 0 skipped**（`artifacts/junit_round8.xml`）。
- 打包 1.0.8：`packaging/out/HushPlayer-1.0.8-win64.zip`，`tools/verify_package.ps1` 启动/单实例/退出验证。

## 未解决 / 限制

- 安装的插件仍需自身接口可用（酷狗 / QQ海棠 / 小米的第三方 404 与插件无关，见第三轮台账）。
- 插件安装暂不做「导入前静态审计」的界面提示；运行时会做 2 MB 上限、路径白名单与静态扫描（禁止
  `fs/child_process/worker_threads`），与旧版一致。
