# B2 Surface Coverage Freeze

以当前源码和 UI-INVENTORY.md 为范围，逐项对照各原型截图 manifest。日期2026-09-10。✓=已有该主题/尺寸视觉稿；继=可直接继承已确认组件，但未逐一独立截图；部=代表状态有稿，全部分支未穷举；原生=保留OS；专项=实现验收而非新设计。不要把“继/部”宣传为100%逐状态覆盖。

证据族：S=Collection 的 shell/main；C=Collection；P=Playback 原稿与 Collection 中 playback 明暗扩展；O=Online & Import；Y=Settings & System。各族位于 `build/ui-concepts/b2-*-experience/screenshots/manifest.json`；O完整自动矩阵另见 `validation-manifest.json`。

| 正式 Surface | 方向 | Light | Dark | 1450 | 1080 | 重要状态 | 交互规格 / 证据 |
|---|---|---|---|---|---|---|---|
| Shell/TitleBar/Sidebar | S | ✓ | ✓ | ✓ | ✓ | 默认/导航选中/compact | 菜单映射补正式低频入口；路由不变 |
| Sidebar 更多 | Y Menu继承 | 继 | 继 | 继 | 继 | hover/focus/路由active | menu-map逐项；未新画大型Prototype |
| Sidebar 歌单 | S+Y | 继 | 继 | 继 | 继 | 只读/CRUD/长名部 | 保留实际路由；更多歌单兼容按钮隐藏，不迁移 |
| Library | C | ✓ | ✓ | ✓ | ✓ | long/playing-selected；空/失败继承 | Collection library、Track状态 |
| TrackList | C+O | ✓ | ✓ | ✓ | ✓ | default/hover/selected/playing/paused/favorite/missing/复合 | state-map；角色来源不同保留 |
| Favorites | C | ✓ | ✓ | ✓ | ✓ | content/empty/search/no-results | 收藏同步 |
| Recent | C | ✓ | ✓ | ✓ | ✓ | content/empty | 历史上下文 |
| Playlist详情/相关右栏 | C | ✓ | ✓ | ✓ | ✓ | content/empty/long | CRUD与右栏条件按源码 |
| 歌单选择/新建/重命名/删除 | Y | ✓ | ✓ | ✓ | ✓ | 输入/错误/危险/选择 | Dialog state；每状态不限都有截图 |
| Artists 列表 | C | ✓ | ✓ | ✓ | ✓ | grid/list/search/empty/no-results | 网格viewport策略保留 |
| Artist详情/info rail | C | ✓ | ✓ | ✓ | ✓ | content/lower/无介绍继 | 1450 window_width条件 |
| Albums 列表 | C | ✓ | ✓ | ✓ | ✓ | grid/list/search/empty | EntityGrid家族 |
| Album详情 | C | ✓ | ✓ | ✓ | ✓ | content，空/错继 | 专辑元数据/歌曲上下文 |
| Browse | C | ✓ | ✓ | ✓ | ✓ | content/lower/empty/unavailable | 在线/本地卡片条件 |
| PlayerBar | S+P | ✓ | ✓ | ✓ | ✓ | 播放/暂停/长文/收藏部 | seek/音量/队列专项实测 |
| 普通 LyricsPage | P | ✓ | ✓ | ✓ | ✓ | ready/loading/empty/failed/long；idle/instrumental继 | manual browsing/translation/return-current |
| Immersive Lyrics | P | ✓ | ✓ | ✓ | ✓ | visible/hidden/transparent/fullscreen | Canvas/自动隐藏/Esc专项 |
| Immersive NowPlaying | P | ✓ | ✓ | ✓ | ✓ | 默认/长文继 | 共用播放状态 |
| Immersive Queue | P | ✓ | ✓ | ✓ | ✓ | normal/empty/only-current/selected | 保留queue索引，单击!=播放 |
| Immersive Quick Settings | P | ✓ | ✓ | ✓ | ✓ | background/lyrics/controls/advanced | 保存/取消/预览与正式字段对齐 |
| Desktop Lyrics正常/悬停/锁定 | P | ✓ | ✓ | ✓ | ✓ | normal/hover/locked/complex/light-bg | 是桌面背景样例尺寸，不是窗口响应断点 |
| Desktop 独立锁控件 | P | 继 | 继 | 继 | 继 | hover/lock/unlock | 原生窗口定位/穿透专项 |
| Desktop Settings Popup | P | ✓ | ✓ | ✓ | ✓ | default/自定义参数部 | 跨屏/锚点/输入专项 |
| Online Search/历史/结果 | O | ✓ | ✓ | ✓ | ✓ | idle/typing/searching/progress/cancel/results/empty/failed/retry/filter/sort/no-sources | 188矩阵的一部分 |
| Online Sources | O | ✓ | ✓ | ✓ | ✓ | list/disabled/busy/failed/limited/long/remove | 行内正式动作与概念菜单差异见menu-map |
| Source Import | O | ✓ | ✓ | ✓ | ✓ | empty/entered/invalid/importing/success/partial/failed/retry/closed | 自定义URL生命周期已补回归 |
| Recovery candidates | O | ✓ | ✓ | ✓ | ✓ | unavailable/复合/searching/candidates/no-candidate/failed/keyboard/success | 保留identity，不由HTML定义替换业务 |
| Pending Imports | O | ✓ | ✓ | ✓ | ✓ | list/selected/all/empty/processing/partial/failed/ignore/success | 批量加入/忽略/定位 |
| Settings外框/导航/footer | Y | ✓ | ✓ | ✓ | ✓ | clean/dirty/preview/save-failed/invalid/unsaved | 固定footer/草稿事务 |
| 常规/外观/播放 | Y | ✓ | ✓ | ✓ | ✓ | 各分类与preview/cancel | source字段映射 |
| Settings歌词 | Y | ✓ | ✓ | ✓ | ✓ | 持久参数/滚动 | 背景透明度≠整体窗口opacity |
| Settings音乐库 | Y | ✓ | ✓ | ✓ | ✓ | 长路径/缺失/空/增删 | 扫描真实服务专项 |
| Settings待导入/在线来源 | Y嵌入O | ✓ | ✓ | ✓ | ✓ | 嵌入默认，子状态继O | 立即操作不归Save事务 |
| Settings缓存 | Y | ✓ | ✓ | ✓ | ✓ | normal/warning/destructive/processing/success/failed | 清理边界按源码 |
| Settings更新/关于 | Y | ✓ | ✓ | ✓ | ✓ | 分类/版本说明 | 真实发布日志来自CHANGELOG链路 |
| UpdateDialog | Y | ✓ | ✓ | ✓ | ✓ | checking/no-update/available/logs/downloading/cancel/failed/retry/verifying/ready/install/launch-failed/fallback | 实际安装不在浏览器执行 |
| TrackInfoDialog | Y | ✓ | ✓ | ✓ | ✓ | 长路径/可复制 | 正式元数据不可猜测 |
| 通用confirm/input/error/warning/info | Y | ✓ | ✓ | ✓ | ✓ | 全部有状态入口 | 复用原QDialog，不改确认结果 |
| 待导入忽略确认 | O+Y | ✓ | ✓ | ✓ | ✓ | ignore/取消/继续 | MainWindow._ignore_pending_paths，不删音频 |
| 更新安装/完整包/取消下载确认 | Y继承 | 继 | 继 | 继 | 继 | Yes/No，默认No；busy/info/error | UpdateDialog内部QMessageBox，未独立逐项截图 |
| 系统托盘不可用提示 | Y Information继承 | 继 | 继 | 继 | 继 | 提示后按正式逻辑退出 | CloseBehaviorController.handle_close |
| Context menus / Tooltip | Y | ✓ | ✓ | ✓ | ✓ | checked/disabled/submenu/focus/long/path | 全部正式动作映射见menu-map |
| Close choice | Y | ✓ | ✓ | ✓ | ✓ | choice/remember | tray unavailable分支原生/专项 |
| Tray menu | 原生+Y示意 | 原生 | 原生 | 不适用 | 不适用 | open/unlock/exit | 不要求像HTML |
| Feedback / Focus | Y | ✓ | ✓ | ✓ | ✓ | toast/error/warning/success/loading/disabled/focus | 不新增通知中心 |
| 文件夹/图片选择器 | 原生 | 原生 | 原生 | OS | OS | 取消/选择/不可访问 | 原生路径操作专项 |
| Installer/UAC/外部打开 | 原生 | 原生 | 原生 | OS | OS | 成功/失败/拒绝 | 真实更新专项 |

## 真正缺口与冻结决策

- 未发现仍需要另起大型概念稿的正式界面家族。菜单实际条目通过源码映射补齐，复用已确认Menu视觉；它们不都有独立逐项截图。
- 低频组合仍有“继/部”：例如 Sidebar 更多完整展开、所有局部菜单随业务条件变化、空专辑/无歌手介绍、最低高度下多层Dialog。进入实现时补前/后/目标对照，不伪称已经运行全部状态。
- 最低900×600、100/125/150%DPI、跨屏、鼠标穿透、真实音频、实际更新/托盘切换属于专项验证，不继续扩展Prototype。
- 沉浸歌单选择器 / Playback Context：当前正式源码未找到对应产品入口，已有概念稿不能覆盖一个不存在的实现；冻结为不迁移、待另行确认。
- SettingsPage/PreviewWindow/实验页未接入正式路径，排除。正式More不能加入实验入口。

此矩阵冻结设计覆盖与限制，不等于发布验收。Qt实施每期仍按状态映射和不可回归契约执行。
