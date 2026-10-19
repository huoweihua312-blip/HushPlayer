# 可收起在线音源列表（v1.0.10）

## 需求

用户：「导入多了太长了，要求能收起」——批量导入后音源数量可能到十几个，设置页被列表占满。

## 行为

| 状态 | 界面 |
| --- | --- |
| 音源 ≤ 4 | 全部显示，无折叠行 |
| 音源 > 4 且未展开 | 显示前 4 个 + 「展开全部音源（还有 N 个）/ 只显示前 4 个，展开后可逐个启用或删除」+「展开全部」按钮 |
| 已展开 | 显示全部 + 「收起音源列表 / 共 N 个音源」+「收起」按钮 |

状态保存在 `settings["online.sources_expanded"]`（默认 `false`），重启后保持。

## 实现

- `hushplayer/ui/pages/settings.py`：`SOURCES_COLLAPSED_VISIBLE = 4`、`source_window(total, expanded, limit)` 返回 `(visible, hidden)`；`_fill_sources()` 只渲染 `sources[:visible]` 并追加折叠行；`_toggle_sources_expanded()` 翻转设置并重填；`hushplayer/core/settings.py` 的 `DEFAULTS["online"]` 增加 `sources_expanded`。
- 重填时旧行先 `hide()` + `setParent(None)` 再 `deleteLater()`：否则折叠瞬间新旧列表会重叠（Qt 延迟销毁），截图与肉眼都能看到闪烁。

## 验证

- `tests/test_source_window.py`：3 个用例覆盖边界（≤4、7 个折叠、展开）。
- `tools/probe_r10_collapse.py`（真实 HushApp）：折叠态 4 条；点击后 7 条且 `online.sources_expanded=True`；`errors 0`。
- 截图：`docs/screenshots/sources_collapsed.png`、`sources_expanded.png`。
- 全量测试 **138 passed / 0 failed**（`artifacts/junit_round10.xml`）。
