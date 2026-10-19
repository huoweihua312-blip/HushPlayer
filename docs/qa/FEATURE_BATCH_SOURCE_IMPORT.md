# 功能：批量导入在线音源（v1.0.9）

## 需求

> 要求加入批量导入音源功能

之前「添加音源…」一次只能选一个 `.js` 文件，装 10 个插件要点 10 次；社区插件包通常是
一个文件夹或多个文件。

## 实现

### 数据层（`hushplayer/online/registry.py`）

- `collect_plugin_files(folder, *, recursive=False)`：列出目录下可安装的 `.js / .json`，
  自动跳过 `node_modules`，按文件名排序。
- `@dataclass InstallReport`：`installed / duplicates / failed`，`summary()` 生成
  「已安装 N 个音源，跳过 M 个重复，失败 K 个」，`failure_text()` 列出前 8 条失败原因。
- `SourceRegistry.install_many(paths)`：
  - 同一路径重复出现 → 计入 `duplicates`；
  - 内容 sha256 与已装插件相同 → `RegistryError("该音源已经安装")` 也计入 `duplicates`；
  - 扩展名/大小/解析失败 → 计入 `failed`，**继续处理后续文件**；
  - 全部结束后只写一次日志汇总。

### 界面（`hushplayer/ui/pages/settings.py`）

- 「添加音源…」改用 `QFileDialog.getOpenFileNames`（多选）。
- 新增「批量导入 / 选择文件夹…」：`getExistingDirectory` + `collect_plugin_files`。
- `_install_source_files(paths)` 统一处理：调用 `install_many` → 成功提示 → 有失败时
  `QMessageBox.warning` 列出原因 → 刷新音源列表。

## 验证

- 单元测试（`tests/test_source_registry.py`，共 5 例）：
  - `collect_plugin_files` 只返回 `.js/.json` 且跳过 `node_modules`；
  - 批量安装 2 个有效 + 1 个同路径 + 1 个 `.txt`：`installed=2, duplicates=1, failed=1`，
    注册表新增 2 条 `user_source_*`；
  - 元数据解析、重复内容拒绝、删除与恢复、2 MB 上限。
- 真实 GUI 探针 `tools/probe_r9_batch.py`（临时数据目录）：
  文件夹含 `alpha.js`、`beta.js`、`alpha-copy.js`（同内容）、`readme.txt`；
  执行后列表出现「批量源 A」「批量源 B」，提示「已安装 2 个音源，跳过 1 个…」，
  `errors 0`；截图 `docs/screenshots/settings_batch_import.png`。
- 全量测试：**135 passed / 0 failed / 0 skipped**（`artifacts/junit_round9.xml`）。

## 行为约定

- 文件夹导入**不递归**子目录（避免误装 `node_modules` 里的工具模块）；需要递归可后续加选项。
- 重复判定优先按内容 sha256；同一文件重复选择则按路径去重。
- 安装仍受 2 MB 上限、扩展名白名单与运行时静态扫描约束。
