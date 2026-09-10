# B2 PySide6 渐进实施计划

状态：仅交接，**尚未开始 Phase 0**。2026-09-10。当前用户明确禁止本轮提交、push和正式Python改动。以后每期须重新核查源码、用户授权与工作区，以下 commit 只是建议。

## 总门槛

1. 先保存该期现状截图与相关已有测试结果；不使用旧截图冒充当前版本。
2. 保留 tokens.py 的字段、兼容别名、类、信号及调用关系；每次只迁一个真实使用点，验收后扩展。
3. 修改重要文件前按项目规则提醒用户手动备份；不得擅自自动备份、装依赖或重建环境。
4. 禁止改变数据库/JSON结构、播放控制器、队列身份、歌词时间轴、在线服务/更新服务、ContentRouter机制。发现结构问题先单独提案。
5. 每个独立改动应有可回退的提交边界。出现契约失败立即停止扩展，保留证据；经确认回退该期提交或本期精确patch，不能reset/restore整个用户工作区。

## Phase 路线

以下文件均以 `app/ui_v2/` 为根，测试以 `tests/` 为根。每期截图默认1450×900/1080×900、Dark/Light，并增加表列场景。自动测试与人工播放验收不可互相替代。

| Phase / 范围 | 文件 | 禁止修改的行为 | 风险 | 建议测试 | 截图专项 | 回退标准 | 独立commit建议 |
|---|---|---|---|---|---|---|---|
| P0 Token/theme primitives/helpers | theme/tokens.py、styles.py、button_styles.py、icons.py；responsive.py只查契约 | 字体引擎/全局断点/业务状态，不大改调用方 | Medium，全局影响 | test_ui_foundations.py、test_ui_v2_theme.py、test_font_runtime.py | 调色角色样本/中文/disabled/focus | 明暗缺色、字重回退、非目标页面变化 | refactor(ui): add compatible B2 visual tokens |
| P1 Sidebar/TitleBar/Button/Search/Surface/Focus | shell/navigation_sidebar.py；widgets/navigation_item.py、custom_title_bar.py、search_field.py、content_surface.py、playback_button.py；现有样式helpers | 历史/route/search debounce/native drag/signal，MainWindow仅必要视觉接缝 | Medium | test_ui_v2_navigation_adapter.py、test_ui_v2_approved_shell.py、test_ui_foundations.py | 更多四项、长歌单、Tab、compact | 漏入口/按钮不能整面点击/查询跨页 | style(ui): apply B2 shell primitives |
| P2 TrackList/Library/Favorites/Recent | widgets/track_table.py、track_delegate.py、responsive_columns.py、collection_action_bar.py；pages/library_page.py、all_songs_page.py、track_list_page.py、favorites_page.py、recent_page.py | selection vs playback、model身份、排序上下文、收藏持久化；不改model架构 | High | test_ui_v2_track_model.py、test_ui_v2_real_actions.py、test_ui_v2_library_family.py、test_ui_v2_track_identity.py | 全部Track组合、空库/无结果/长文/滚动 | 单击播放、选中/播放混淆、排序重建queue | style(ui): migrate B2 collection track visuals |
| P3 PlayerBar | shell/player_bar.py；widgets/track_identity.py、playback_button.py | seek/volume/mute/favorite/播放状态；禁止改QMediaPlayer | High | test_ui_v2_playback_adapter.py、test_ui_v2_real_playback.py、test_ui_v2_slider_styles.py | 长歌名、暂停、静音、未知时长、seek拖动 | 底栏移位/进度拖动跳变/点击语义变 | style(ui): refine B2 player bar layout |
| P4 Playlist/Album/Artist/Browse | pages/playlist_page.py、album_detail_page.py、artist_detail_page.py、entity_grid_page.py、browse_page.py；现有Hero/Card/RelatedPlaylistsPanel | CRUD、推荐来源、排序、艺人1450 width来源 | Medium–High | test_ui_v2_content_pages.py、test_ui_v2_artist_page.py、test_ui_v2_browse_discovery.py、test_ui_v2_responsiveness.py | 长Hero、无介绍、右栏、网格/列表、在线不可用卡片 | 右栏阈值漂移/曲库或歌单上下文变 | style(ui): migrate B2 collection detail surfaces |
| P5 Normal Lyrics | pages/lyrics_page.py；widgets/compact_lyrics_toolbar.py、lyrics_state_view.py；Canvas仅视觉参数 | 解析/segment/position/manual browsing/翻译/seek | High | test_ui_v2_lyrics.py、lyrics_timing_offset_smoke.py | ready/empty/failed/手动浏览/中英翻译 | 同步偏移、返回当前无效、重复播放器 | style(lyrics): apply B2 ordinary lyric presentation |
| P6 Immersive两模式/Queue/Settings | pages/immersive_lyrics_page.py、now_playing_page.py；widgets/immersive_controls.py、immersive_queue_panel.py、实际快捷设置/overlay文件 | 生命周期、queue索引、auto-hide、Esc、全屏、事务；不换Canvas | High | test_ui_v2_immersive_player.py、test_ui_v2_q4_immersive_contract.py、test_ui_v2_q4_immersive_lifecycle.py | 可见/隐藏控制、空队列/当前/接下来、打开浮层、全屏 | panel吞输入/退出层级错/queue变化/失去焦点 | style(lyrics): migrate B2 immersive visual surfaces |
| P7 Desktop Lyrics | shell/desktop_lyrics_window.py；widgets/desktop_lyrics_quick_settings.py | native拖动、anchor、锁、穿透、跨屏、独立窗口flags | High | test_ui_v2_desktop_lyrics.py + 实机双屏100/125/150% | 明暗桌面、长文换行、hover锁/右键popup | 拖动漂移/不能解锁/播放切歌挪窗口 | style(lyrics): align desktop lyric controls with B2 |
| P8 Online/Sources/Recovery/Pending | pages/online_search_page.py、online_source_page.py、pending_imports_page.py；widgets/online_result_table.py、source_selector.py、source_import_dialog.py、online_recovery_dialog.py、相关state/toolbar | generation/来源能力/导入授权/恢复identity/真实网络；不加入下载项 | High | test_ui_v2_online_search.py、test_ui_v2_online_recovery_dialog.py、test_ui_v2_pending_imports.py、custom_source_management_smoke.py、source_removal_smoke.py | 异步全状态、长URL、选中缺失、busy来源 | 旧结果覆盖/URL丢失/恢复改成员/来源误删 | style(ui): migrate B2 online and import surfaces |
| P9 SettingsOverlay | widgets/settings_overlay.py、settings_sidebar.py、settings_section.py、settings_row.py、settings_footer.py、settings_control_factory.py | SettingsEditSession/bridge/save/cancel/preview、立即动作不改为草稿 | High | test_ui_v2_settings.py、test_settings_toggle.py、test_appearance_settings.py、settings_runtime_cache_smoke.py | 十分类、滚动footer、dirty/failed/取消恢复、嵌入页 | 取消不恢复/草稿丢失/危险操作误触 | style(settings): apply B2 settings layout |
| P10 Dialog/Menu/Update/Close | widgets/playlist_dialogs.py、track_action_dialogs.py、quiet_context_menu.py；dialogs/update_dialog.py；close_behavior_controller.py仅视觉 | QAction条件/确认语义/下载校验安装/退出托盘 | High（菜单样式局部为Medium） | test_ui_v2_real_actions.py、test_ui_v2_close_behavior.py、app_update_smoke.py、in_app_update_smoke.py | 长路径、全部菜单条件、更新全流程、tray不可用 | 未验证可安装/后台播放退出/隐藏项冒出 | style(ui): align B2 dialogs and system surfaces |
| P11 响应/DPI/可访问/回归 | 必要的已迁移视觉文件；不预设大改 | 所有Non-Regression Contract | High，跨模块 | 前述相关集 + test_ui_v2_production_integration.py、test_ui_v2_responsiveness.py、test_font_runtime.py | 900×600、所有阈值边缘、多DPI/双屏/键盘 | 任一核心契约失败或中文不可读 | test(ui): establish B2 desktop acceptance baselines |

P6拆成浮层、队列绘制、模式布局三个可独立验收小步；P8与P10同样逐个对话框迁移，不以“一个Phase”作为大补丁理由。业务耦合高的视觉调整必须先提出影响范围并获确认。

## 执行与测试方式

实施期先确认 `.venv/Scripts/python.exe --version`；当前已知可用为Python3.12，不代表CPython3.13发布构建兼容。unittest文件可用项目既有入口运行，例如 `python -m unittest discover -s tests -p test_ui_foundations.py`；先读该期测试头部/入口，smoke脚本按现有fixture约定执行，不能对用户真实库运行破坏性清理。

正式Python修改后必须逐文件py_compile，并至少检查main.py和app/ui_v2/shell/main_window.py；UTF-8/中文、git diff --check、diff逐项review。本轮未修改Python，不以“没运行正式测试”冒充通过。

## 视觉回归方案

现存目录：

- `build/ui-baseline/preparation-before/`、`preparation-before-verified/`、`preparation-after/`、`preparation-final/`：准备阶段历史快照。
- `build/ui-baseline/layout-contract-fixed/`：info_rail修复记录。
- `build/ui-baseline/dpi-1/`、`dpi-1.25/`、`dpi-1.5/`：Windows FreeType、DPR1/1.25/1.5，manifest记录fixture逻辑尺寸；不自动认定代表未来代码。
- `build/ui-current-inventory/`：正式副本与fixture来源有区别，详见各manifest。
- `build/ui-concepts/`：审核目标。Collection含后续Light与Playback扩展，不能只取最早Shell Light。

每期新建忽略目录 `build/ui-baseline/b2-phase-N/<run-id>/{before,after,target}/`，禁止覆盖历史baseline。manifest必须包含源码HEAD、工作区diff摘要/哈希、窗口logical size、截图pixel size、DPR、Qt/Python/平台/fontengine、实际字体family/style/size、主题、route、mock或真实数据来源、selected/playing/available、滚动位置、弹层/焦点状态与target文件路径。PNG像素尺寸须读取图片验证，不能仅按logical×DPR推断。

固定同一数据fixture、选中/播放身份、歌曲名/封面、窗口位置、字体、滚动、时钟状态；等布局与异步数据稳定，暂停装饰动画后截图。真实歌词动态帧另录短视频或时间点记录，不拿不同音频时间的截图作几何差异。

每期至少8张正式图（before/after × 两宽 × 两主题），加对应B2 target四张引用；特殊状态按该期表追加。允许用裁剪/并排/半透明叠图定位差异；比较Geometry、Hierarchy、Spacing、Typography、Color、State semantics、Control weight，不用单个pixel diff百分比判PASS。

验收标准：

- 几何：标题/列/底栏/页脚对齐，无重叠/截断/新增横滚；逻辑像素1–2px抗锯齿边缘差异可接受，持续性列偏移须人工判定。
- 文字：Qt与Chromium字形hinting、基线、描边、亚像素抗锯齿、换行点可不同；中文笔画必须清晰，文字不裁切。无需为匹配像素关掉FreeType。
- 色彩：半透明背景合成/原生窗口阴影可不同；主题语义、对比层级、错误/选中/播放区分必须一致。
- 输入：focus必须可见且不等于hover；点击区域不得因小图标缩小；原生文件框/tray/UAC无需B2像素一致。
- 业务：任何截图好看都不能覆盖播放/队列/歌词契约失败。无障碍可访问名称、Tab顺序、Esc逐层退出逐项验收。

宽度口径继续使用window_width（顶层Qt逻辑宽）、content_width（页面host）、viewport_width（scroll/table实际viewport）；不得减固定sidebar宽猜测。正式950/960/1000/1080/1100/1200/1220/1400/1440/1450/1600/1700阈值不合并；原型1200 compact与正式1080的差异先保留正式阈值，目标验收固定1450/1080，不悄悄迁阈值。

## Phase 0 / Phase 1 开工建议

P0只准备兼容语义字段及共享样式helper，首个使用点选普通ContentSurface或一个非业务按钮；不先全局切换所有QSS。P1先NavigationItem/Sidebar的间距与选中样式，再TitleBar，再SearchField/Focus；每步核对路由与查询。MainWindow只允许必要的主题调用接缝，不在本计划中批准协调逻辑修改。
