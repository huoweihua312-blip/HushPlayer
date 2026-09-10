# B2 → 当前 PySide6 Component Map

基准：2026-09-10 / `f342a86`。文件以 `app/ui_v2/` 为根。样式可原位调整不代表可以改变信号、状态或业务。P0–P11 见实施计划。结构栏“局部”仅指现有容器内部布局，绝非替换协调器。

| Existing class / file | B2 target | 原位样式 | 结构重构 | 新可复用组件 | 业务耦合 | 风险 | Phase |
|---|---|---|---|---|---|---|---|
| ThemeColors/ThemeMetrics/ThemeFonts — theme/tokens.py | 语义Token | 是 | 否，兼容别名 | 否 | 全局调用方 | Medium | P0 |
| build_stylesheet — theme/styles.py；button_styles.py | 基础控件样式 | 是 | 否 | 优先函数 | 全局QSS/字体 | Medium | P0 |
| icons.py | 图标角色和命中区分离 | 是 | 否 | 否 | 图标缓存/状态 | Low | P0/P1 |
| LayoutWidths/ResponsiveThresholds — theme/responsive.py | 宽度契约 | 仅命名 | 否 | 否 | 各页面测量来源 | Medium | P0/P11 |
| MainWindow/ThemeRevealOverlay — shell/main_window.py | B2 Shell与主题 | 限局部 | 禁止重写 | 否 | 播放/服务/窗口协调 | High | P1接缝/P11 |
| ContentRouter — shell/content_router.py | 既有页面路由 | 不属视觉替换 | 否 | 否 | 缓存/历史/播放上下文 | High | 保护，不重构 |
| NavigationSidebar — shell/navigation_sidebar.py | Sidebar | 是 | 局部间距 | 否 | 路由/歌单CRUD | Medium | P1 |
| NavigationItem — widgets/navigation_item.py | 导航行/compact | 是 | 否 | 否 | clicked/context_requested | Low | P1 |
| CustomTitleBar — widgets/custom_title_bar.py | Back/Forward/Search/Settings/窗口按钮 | 是 | 局部权重 | 否 | 拖动/窗口状态/搜索 | Medium | P1 |
| SearchField — widgets/search_field.py | 轻量搜索字段 | 是 | 否 | 已存在 | text_changed/内部输入 | Low | P1 |
| SearchBox/OnlineSearchBar — widgets/search_box.py、online_search_bar.py | 现有搜索变体 | 是 | 不强行合类 | 否 | debounce/提交/清除 | Medium | P1/P8 |
| SearchInputController — widgets/search_input_controller.py | Typing/提交契约 | 无视觉 | 否 | 否 | 180ms debounce/路由同步 | High | 保护 |
| ContentSurface — widgets/content_surface.py | 开放内容底板 | 是 | 否 | 已存在 | insets/safe_bottom | Low | P1 |
| PlayerIconButton — widgets/playback_button.py | 图标按钮 | 是 | 否 | 已存在 | click信号 | Low | P1/P3 |
| SettingsToggle/FlatSlider/ThemedComboBox — widgets/settings_control_factory.py | 控件与Focus | 是 | 否 | 优先复用 | hitButton/drag/valueChanged | Medium | P1/P9 |
| TrackTable/TrackHeaderView — widgets/track_table.py | TrackList | 是 | 仅列/间距 | 否 | selection/play/menu | High | P2 |
| TrackDelegate — widgets/track_delegate.py | Track Row状态 | 是 | 保留delegate架构 | 否 | model roles/缺失优先级 | High | P2 |
| TrackTableModel — models/track_table_model.py | 状态输入 | 不改数据 | 否 | 否 | identity/sort/reset | High | 保护/P2验证 |
| QuietTrackTable/QuietTrackDelegate — widgets/content_primitives.py（另有兼容导出） | 同一Track家族 | 是 | 不建第三套 | 否 | 继承上述类 | High | P2 |
| TrackIdentity — widgets/track_identity.py | 底栏文字身份块 | 是 | 保留传入label所有权 | 已存在 | 外部更新label | Low | P3 |
| present_track_identity — widgets/track_display.py | 文本/可用性解释 | 无视觉逻辑改动 | 否 | 否 | 状态规范化/缺失解释 | High | 保护 |
| ArtworkThumbnail/ElidedLabel — widgets/artwork_thumbnail.py、elided_label.py | 封面/长文 | 是 | 否 | 已存在 | pixmap cache/elide | Low | P2/P3 |
| AllSongsPage(LibraryPage) — pages/all_songs_page.py、library_page.py | 音乐库 | 是 | Header局部 | 否 | adapter/filter/state | Medium | P2 |
| TrackListPage — pages/track_list_page.py | 集合基础 | 是 | 局部 | 否 | 页面上下文/表格 | High | P2/P4 |
| FavoritesPage/RecentPage — pages/favorites_page.py、recent_page.py | 收藏/最近 | 是 | 否 | 否 | 收藏/历史集合 | Medium | P2 |
| CollectionActionBar(CollectionActionRow) — widgets/collection_action_bar.py、collection_action_row.py | 页面动作 | 是 | 否 | 已存在 | play/shuffle信号 | Low | P2 |
| PlayerBar/_PlayerSlider — shell/player_bar.py | 安静连续播放器 | 是 | 三组布局局部 | 否 | seek/volume/favorite/queue | High | P3 |
| PlaylistPage/PlaylistHeader — pages/playlist_page.py、widgets/playlist_header.py | 歌单Header与内容 | 是 | 局部去容器 | 否 | CRUD/只读/成员 | High | P4 |
| TrackCollectionHero/AlbumHero/PlaylistHero — widgets/track_collection_hero.py、content_heroes.py | Collection Hero | 是 | 局部 | 不新增平行Hero | 播放动作 | Medium | P4 |
| AlbumDetailPage — pages/album_detail_page.py | 专辑详情 | 是 | 局部 | 否 | 专辑上下文 | Medium | P4 |
| EntityGridPage/ArtistsPage/AlbumsPage — pages/entity_grid_page.py、artists_page.py、albums_page.py | 列表/网格 | 是 | 保留布局回退 | 否 | 查询/排序/viewport | Medium | P4 |
| ArtistDetailPage/ArtistHero/ArtistActionRow — pages/artist_detail_page.py、widgets/artist_hero.py、artist_action_row.py | 歌手详情 | 是 | 局部 | 否 | 介绍1450/专辑/艺人导航 | Medium | P4 |
| RelatedPlaylistsPanel — widgets/related_playlists_panel.py | 页面可选右栏 | 是 | 否 | 否 | reference宽度/playlist路由 | Medium | P4 |
| BrowsePage/BrowseSection — pages/browse_page.py | 浏览分区 | 是 | 局部密度 | 否 | 本地/在线混合推荐 | High | P4 |
| MediaCard/AlbumCard/ArtistCard/ArtistAlbumCard/PlaylistCard — widgets对应文件、content_cards.py | 集合卡片 | 是 | 原类内部 | 否 | 卡片点击/菜单/封面 | Medium | P4 |
| LyricsPage/CompactLyricsToolbar/LyricsStateView — pages/lyrics_page.py、widgets/compact_lyrics_toolbar.py、lyrics_state_view.py | 普通歌词 | 是 | 保留单列 | 否 | seek/翻译/返回当前 | High | P5 |
| LyricsCanvasV2 — widgets/lyrics_canvas_v2.py | 当前行与周边字形 | 只度量/绘制参数 | 禁止改时间轴 | 否 | position/segment/browsing | High | P5/P6 |
| ImmersivePlayerShell(ImmersiveLyricsPage) — shell/immersive_player_shell.py、pages/immersive_lyrics_page.py | 沉浸Shell | 限视觉边界 | 不重写生命周期 | 否 | 全屏/Esc/自动隐藏 | High | P6 |
| NowPlayingPage — pages/now_playing_page.py | 正在播放 | 是 | 原容器重排 | 否 | 共用播放状态 | High | P6 |
| ImmersiveControls/ImmersiveTrackIdentity — widgets/immersive_controls.py、immersive_track_identity.py | 沉浸播放控制 | 是 | 局部 | 否 | seek/唤醒/身份 | High | P6 |
| ImmersiveQueuePanel/QueueTrackModel/_UpcomingQueueProxy/_QueueDelegate — widgets/immersive_queue_panel.py | 当前/接下来队列 | 是 | 不换model | 否 | 全局队列索引映射 | High | P6 |
| LyricsQuickSettingsFloatingPanel — widgets/lyrics_quick_settings_panel.py；ImmersiveSettingsPanel — widgets/immersive_settings_panel.py | 快捷设置 | 是 | 保留真实引用路径 | 不创建第三种浮层 | draft/preview/保存 | High | P6 |
| ImmersiveOverlayHost/ImmersiveFloatingPanel — widgets/immersive_overlay.py、immersive_side_drawer.py | 浮层定位 | 是 | 限接缝 | 否 | Overlay优先级 | High | P6 |
| ArtworkAtmosphere/ReadabilityOverlay — widgets/artwork_atmosphere.py | 沉浸背景保护 | 是 | 否 | 否 | 图片/透明度与性能 | Medium | P6 |
| DesktopLyricsWindow/DesktopLyricsLockButton — shell/desktop_lyrics_window.py | 独立透明歌词/锁控件 | 只paint/style | 禁止换窗口架构 | 否 | native drag/穿透/屏幕 | High | P7 |
| DesktopLyricsQuickSettingsPopover — widgets/desktop_lyrics_quick_settings.py | 桌面设置 | 是 | 保留popup定位 | 否 | 即时预览/锁定 | High | P7 |
| OnlineSearchPage/SearchStateView/SearchHistoryView — pages/online_search_page.py、widgets/search_state_view.py、search_history_view.py | 在线状态/历史 | 是 | 原容器局部 | 否 | generation/取消/服务 | High | P8 |
| OnlineResultTable/OnlineResultDelegate/OnlineResultToolbar — widgets对应文件 | 在线结果 | 是 | 保留model | 否 | formal状态/菜单/播放 | High | P8 |
| SourceSelector/SourceStatusBadge — widgets/source_selector.py、source_status_badge.py | 来源选择/健康 | 是 | 否 | 否 | enabled/searching/capability | Medium | P8 |
| OnlineSourcePage/SourceRow — pages/online_source_page.py | 来源管理 | 是 | 保留行内动作 | 否 | 导入/删除/启停 | High | P8 |
| SourceImportDialog/SourceRemoveConfirmDialog — widgets/source_import_dialog.py | 来源导入/确认 | 是 | 否 | 否 | importer异步/URL/授权 | High | P8 |
| OnlineRecoveryCandidateDialog — widgets/online_recovery_dialog.py | 恢复候选 | 是 | 否 | 否 | 身份/收藏/成员关系 | High | P8 |
| PendingImportsPage — pages/pending_imports_page.py | 待导入 | 是 | 局部 | 否 | 多选/验证/忽略 | High | P8 |
| SettingsOverlay/SettingsConfirmDialog — widgets/settings_overlay.py | 设置外框/确认 | 是 | 内部布局局部 | 否 | bridge/session/立即动作 | High | P9 |
| SettingsSidebar/SettingsSection/SettingsRow/SettingsFooter — widgets对应文件 | Section+row+固定footer | 是 | 否 | 全部已有 | edit session / signals | Medium | P9 |
| SettingsControlFactory及PathPicker/ActionButton/DangerAction | 按钮/路径/滑块 | 是 | 否 | 优先已有 | 验证、命中区 | Medium | P9 |
| PlaylistNameDialog/PlaylistConfirmDialog — widgets/playlist_dialogs.py | Input/Destructive | 是 | 否 | 优先样式函数 | 名称验证/确认 | Medium | P10 |
| TrackInfoDialog/PlaylistSelectionDialog — widgets/track_action_dialogs.py | 信息/选择 | 是 | 否 | 否 | id与成员选择 | Medium | P10 |
| QuietContextMenu/apply_menu_theme — widgets/quiet_context_menu.py | Menu/Tooltip/Focus | 是 | 否 | 已存在；可共享QSS函数 | QAction enable/trigger | Medium | P10 |
| UpdateDialog — dialogs/update_dialog.py | 更新生命周期 | 是 | 限布局 | 否 | 下载/校验/安装/退出 | High | P10 |
| CloseBehaviorController — shell/close_behavior_controller.py | 关闭/托盘 | 只dialog视觉 | 否 | 否 | 退出/后台/锁定恢复 | High | P10 |
| 现有QMessageBox — MainWindow._ignore_pending_paths、UpdateDialog、CloseBehaviorController | 忽略确认/安装确认/系统提示 | 仅原有dialog视觉 | 不抽业务流程 | 优先纯样式helper | 默认No、取消下载、忽略记录 | High | P8/P10 |
| EmptyState/InlineErrorState — widgets/empty_state.py、content_states.py | 空/错/反馈 | 是 | 否 | 优先复用 | retry信号 | Low | 分期 |

## 复用优先级与明确排除

1. 优先原类 set_theme / paint / margins；其次共享 QSS 或纯绘制 helper；仅发现两个真实重复使用点且接口清楚时才提取组件。
2. 不新增 B2MainWindow、B2TrackTable、B2Settings 等平行正式实现。TrackTable/QuietTrackTable 的继承与兼容导出先核查，不能因别名误判两份独立业务。
3. 同名 LyricsQuickSettingsFloatingPanel 有多处定义；当前 ImmersiveLyricsPage 从 lyrics_quick_settings_panel.py 导入，lyrics_quick_settings_drawer.py 不是这条正式构造链。禁止按类名批量替换。ArtistPage 则是 artist_page.py 对 ArtistDetailPage 的公开兼容别名，不是另一个页面实现。
4. SettingsPage、PreviewWindow、实验沉浸窗口、旧 LyricsHeader/Timeline 不自动迁移。普通 LyricsPage 不构造旧身份块与页内播放器；正式库是 AllSongsPage。
5. B2 Playback Context 菜单属于未确认的产品扩展，不对应现有正式组件；不因已有概念图创建它。

Component Map 是文件/职责交接，不是授权在所有文件上同时实施。每个 Phase 仍须只迁移一个使用点、验证后再扩展。
