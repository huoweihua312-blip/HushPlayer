# 订阅导入（v1.0.12）

用户提供示例：`https://source.shiqianjiang.cn/api/script/mf.json?key=...`，要求「能导入类似这种的链接」。

## 订阅格式（实测）

```json
{
  "plugins": [
    {"name": "bilibili", "url": "https://.../mf/bilibili.js?key=...", "version": "8.4+61b814293028"},
    {"name": "网易云音乐", "url": "https://.../mf/netease.js?key=...", "version": "8.4+..."}
  ],
  "yourinfo": {...}
}
```

HTTP 200 / `application/json` / 1095 B / 5 个插件。

## 行为

- 只接受 http(s) 订阅地址；订阅 JSON ≤2 MB，单个插件 ≤2 MB。
- `subscription_entries()` 兼容 `plugins` / `sources` / `data` / `items` 四种键以及纯数组。
- 逐个下载后复用 `_install_bytes()`：sha256 去重、写 `data/sources/user_sources/*.js`、
  更新 `source_registry.json`，**不执行插件代码**；`name/version` 优先取订阅里的字段，
  缺失时从插件源码头部解析。
- 结果用 `InstallReport` 汇总：成功 toast「已安装 N 个音源，跳过 M 个重复，失败 K 个」，
  有失败时弹窗列出「名称：原因」（最多 8 条），随后自动刷新音源列表。

## 验证

- 真实订阅（上面那条，5 个插件）：`installed 5 / duplicates 0 / failed 0`，包含
  `bilibili`、`酷狗音乐`、`酷我音乐`、`QQ音乐 · 1059`、`网易云音乐`。
- 真实 GUI（`tools/probe_r12_import.py`，桩掉 `QInputDialog` 返回值，走完整
  `_import_subscription()`）：音源数 **7 → 12**，toast「已安装 5 个音源」「重新加载源列表」，
  截图 `docs/screenshots/settings_subscription_imported.png`。
- 自动化：`tests/test_source_registry.py` 覆盖订阅结构解析与本地 HTTP 订阅安装
  （2 成功 + 1 个 404 继续完成），全量 **143 passed**。

## 边界

- 订阅服务器需要允许直接 GET；带登录态或需要额外请求头的订阅暂不支持。
- 若订阅里的插件依赖 `axios/cheerio` 等模块，仍受 `plugin_host.js` 的模块白名单限制，
  加载失败会在搜索结果状态里显示该音源失败。
