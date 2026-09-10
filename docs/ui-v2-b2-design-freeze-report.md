# B2 Design Freeze & Implementation Handoff 报告

日期：2026-09-10。基准分支 `design/ui-v2-real-playback`，源码HEAD `f342a86`。用户已确认六个B2设计家族。本轮不开始Phase 0、不修改正式Python、不提交、不push、不调用Figma。

## 结果

| 交接项 | 结果 / 证据 |
|---|---|
| Online Prototype URL缺陷 | 已修复：importDraft保留用户原始URL，多行/停止/重试/完成不回到默认演示URL；HTML插值转义 |
| 内嵌副本 | Settings内嵌Online副本同步同一修复；go目标保持embedded-online.html，避免进入System stage错误路由；无视觉改版 |
| 完整Online验证 | 188组状态、50项检查PASS，0新截图；validation.json保存完整结果 |
| 内嵌导入验证 | Dark/Light ×1450/1080，12项URL与dialog边界检查PASS；首次服务未启动导致连接失败，启动8770后重新执行通过 |
| Sidebar/条件菜单 | 当前正式QMenu与条件动作逐项映射；隐藏/disabled/未接入分开记录 |
| Design System | 冻结颜色/文字角色/间距/圆角/图标与命中区/动画边界；保留家族差异 |
| Component Map | 优先复用原类、helper、delegate；明确文件、风险、耦合及实施期 |
| Surface / State | 区分已截图、组件继承、部分状态、原生和专项验收；状态关联真实代码来源 |
| Implementation Plan | P0–P11逐期范围、禁区、文件、测试、截图、回退和commit建议 |
| Non-Regression | 单双击、选择/播放、队列、歌词、窗口输入、在线、更新、字体等阻断契约 |

## 文档索引

- [主要视觉规格](ui-v2-b2-design-spec.md)
- [组件映射](ui-v2-b2-component-map.md)
- [菜单逐项映射](ui-v2-b2-menu-map.md)
- [最终Surface矩阵](ui-v2-b2-surface-coverage.md)
- [状态来源映射](ui-v2-b2-state-map.md)
- [实施与视觉回归计划](ui-v2-b2-implementation-plan.md)
- [不可回归契约](ui-v2-b2-non-regression-contract.md)

## 已确认的设计/源码差异

- Sidebar更多仅recent/artists/albums/lyrics；more_playlists是隐藏兼容句柄，不迁入可见界面。
- SourceRow实际为行内启停/重试/移除，不存在原型Source Menu；Online正式结果不显示下载。
- 普通TrackTable加入歌单是选择Dialog；Online/Browse使用现有子菜单，不能为了统一样式改业务路径。
- 原型instrumental不代表正式自动识别纯音乐；独立Verifying画面也不代表正式服务已有分离进度信号。
- 沉浸Playback Context/歌单选择器未找到正式入口，明确不实施。
- 原型compact存在1200阈值，正式Shell为1080；实施保持正式宽度契约，不直接复制CSS媒体查询。
- 当前TrackDelegate缺失优先级可能压过Playing绘制；后续只在保留所有原始flag的前提下协调B2绘制，不改播放能力判断。

## 仍存在的覆盖限制

主要正式界面家族均有设计方向。Sidebar更多的完整逐项截图、全部业务条件菜单和少数空/错组合通过继承现有系统组件覆盖，未逐帧独立画稿。最低900×600、多DPI、桌面歌词跨屏/鼠标穿透/实际音频须实现期专项验收。文件选择器、tray、Installer/UAC保留OS原生。

Settings旧validation.json和frozen-hashes.json是上一轮执行时的历史记录，不改写它们来假装没有修复；本轮结果以Online validation.json中的主矩阵及embeddedImport为准。冻结只禁止视觉改版，不禁止已授权原型缺陷修复。

## 建议下一步（未启动）

P0首选 `app/ui_v2/theme/tokens.py`、`styles.py`、`button_styles.py`、`icons.py`；先兼容字段与一个使用点，不全局改色。P1首选 `shell/navigation_sidebar.py`、`widgets/navigation_item.py`、`custom_title_bar.py`、`search_field.py`、`content_surface.py`、现有按钮控件。MainWindow和ContentRouter不重写。

## 本轮文件与验证

新增本报告及七份关联docs。Prototype仅修改Online `scripts/online.js`、验证脚本/报告，以及Settings内嵌 `scripts/online.js`；未更改CSS/封面/字体/审核截图。

执行：`node --check`检查变更JS，`node .../scripts/validate-final.cjs`完整在线验证，`node .../scripts/validate-embedded.cjs`内嵌补充验证；`git diff --check`。正式Python没有修改，因此未执行正式播放或Python回归套件。环境沿用现有Node Playwright/Chromium，无依赖安装。

Git预期状态：八份新增docs未跟踪，Prototype位于忽略的build；无暂存、无commit、无push。后续授权实施前仍需重新核对源码与用户工作区。
