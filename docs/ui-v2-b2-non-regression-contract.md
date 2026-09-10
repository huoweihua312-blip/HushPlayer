# B2 Non-Regression Contract

日期2026-09-10。当前源码行为优先于HTML模拟；Git历史用于解释已修复问题，不代替读当前代码。本文件是每一期视觉验收的阻断项。

| 契约 | 当前实现依据 | 必须保留的行为 | 检查/历史证据 |
|---|---|---|---|
| 单击选择 / 双击播放 | ui_v2/widgets/track_table.py、online_result_table.py；shell/content_router.py | 单击浏览不打断播放；双击才发播放请求，收藏/更多独立命中 | test_ui_v2_real_actions.py、test_ui_v2_q5b1_real_interactions.py |
| Playing != Selected | TrackTableModel roles、TrackDelegate.row_visual_state | 浏览另一行仍显示当前播放；暂停仍有current身份；复合状态不丢 | test_ui_v2_track_model.py、test_ui_v2_track_identity.py |
| Playback context稳定 | adapters/playback_adapter.py；services/playback_queue.py、production_playback_controller.py | sort/filter/scroll/换页不能重建queue或改变next/previous；route缓存不触发扫描 | test_ui_v2_playback_adapter.py、test_ui_v2_real_playback.py |
| Seek/volume/mute | shell/player_bar.py::_PlayerSlider；adapters/playback_adapter.py::seek | 点击轨道/拖动/释放时机不变，进度单位ms，不改媒体初始化 | test_ui_v2_slider_styles.py + 真音频拖动 |
| Favorite同步 | library_collection / favorites_adapter / online_adapter / PlayerBar | 行、底栏、收藏页一致；缺失已收藏仍可取消 | test_ui_v2_real_actions.py、test_ui_v2_real_library_pages.py |
| Queue语义 | services/playback_queue.py；ImmersiveQueuePanel / _UpcomingQueueProxy | 当前/接下来映射正确；单击不播放；双击作用于正确全局索引 | test_ui_v2_immersive_player.py |
| Lyrics timing | adapters/lyrics_adapter.py；widgets/lyrics_canvas_v2.py | 不改解析、offset、position/segment、高亮时钟、暂停与同步；平滑变化不造成漂移 | lyrics_timing_offset_smoke.py、test_ui_v2_lyrics.py；9bb4c70 |
| Manual browsing / Translation | LyricsCanvasV2.browsing/return_to_current；LyricsAdapter.toggle_translation | 手动阅读不被普通更新抢回；返回当前恢复跟随；翻译独立开关 | test_ui_v2_lyrics.py；91f54ec |
| Immersive自动隐藏 | pages/immersive_lyrics_page.py::_schedule_controls_hide / wake_controls | 仅活动、播放、允许自动隐藏且非设置/交互时调度；拖动控件中不隐藏 | test_ui_v2_q4_immersive_contract.py、test_ui_v2_q4_immersive_lifecycle.py |
| Fullscreen / Esc | ImmersiveLyricsPage._handle_escape；MainWindow presentation | 当前顺序：设置内popup→队列→设置panel→退出fullscreen→退出沉浸；不直接关闭app | test_ui_v2_immersive_lyrics.py、test_ui_v2_q4_immersive_lifecycle.py |
| Settings事务 | SettingsEditSession、SettingsOverlay、LegacySettingsBridge | clean/dirty/preview/save/cancel一致；失败留草稿；取消恢复主题；来源/清缓存是独立即时命令 | test_ui_v2_settings.py、test_appearance_settings.py |
| 开关命中 | SettingsToggle.hitButton | 整个轨道可点，两端与滑块移动后都可点 | test_settings_toggle.py；a653996 |
| Desktop拖动 | DesktopLyricsWindow nativeEvent/拖动/锚点逻辑 | 原生拖动优先，拖动中延迟布局，切歌不挪位置，保存位置语义不变 | test_ui_v2_desktop_lyrics.py；3a91abc、aa8b78a、a9e7f99 |
| Desktop锁/穿透 | DesktopLyricsWindow._set_input_passthrough、独立LockButton、Popover | 锁后可通过锁控件或tray解锁，透明区域/独立window输入不回归；长行自动fit | e2c86ef、7751dd3、7b0d2d8；双屏人工验收 |
| Session restore | services/playback_session_store.py；MainWindow/PlaybackAdapter | 恢复歌曲和进度按设置，不擅自自动播放/丢失上下文；兼容旧数据 | test_playback_session_store.py；9bb4c70 |
| Missing recovery | services/online_track_recovery.py；MainWindow恢复处理；Track.needs_online_recovery | 换来源保留stable identity、收藏/歌单位置，不删暂时不可用记录 | test_online_track_recovery.py、test_ui_v2_online_recovery_dialog.py；26bcc94、6c945fc |
| Online source/search | OnlineAdapter/OnlineSourceAdapter及正式services | generation防旧结果；cancel有效；启停≠删除；能力≠健康；不扩大在线权限或加下载接口 | custom_source_management_smoke.py、source_removal_smoke.py、online_runtime_contract_smoke.py |
| Pending imports | PendingImportsPage/正式验证服务 | 扫描新增默认待导入；只处理选择项，忽略不删原文件；异步不阻塞 | test_ui_v2_pending_imports.py、manual_import_async_smoke.py；a124741 |
| Update lifecycle | services/app_update_service.py；ui_v2/dialogs/update_dialog.py | 大小/SHA-256验证后才能安装；安装/取消下载确认默认No；失败app继续运行；取消临时文件由服务清理；日志分版本 | app_update_smoke.py、in_app_update_smoke.py、update_manifest_changelog_smoke.py |
| Close/Tray | CloseBehaviorController | exit/tray/cancel/remember保持；tray不可用不能让app不可找回；桌面歌词锁恢复 | test_ui_v2_close_behavior.py；d320fe1 |
| Reduce Motion / Theme reveal | MainWindow/ContentRouter/Canvas已有设置链 | 不必要动画可关闭但终态/输入正常；不改已修复主题首帧和半径 | test_appearance_settings.py；ca4fe29、7138ca6、20861f5 |
| 字体清晰与FreeType | app/startup.py；ui_v2/theme/tokens.py字体加载 | Qt实例前Windows默认windows:fontengine=freetype，保留显式环境覆盖；PassThrough高DPI；MiSans随包；PreferNoHinting等现有策略 | test_font_runtime.py；ee9d257、dd0cb4c |
| 响应式宽度 | theme/responsive.py；ArtistDetailPage | info_rail使用window_width，1450不变；content/viewport不混用；safe_bottom不叠加 | test_ui_foundations.py、test_ui_v2_responsiveness.py；ec8bc77、f342a86 |
| 数据与后台稳定 | library/playlist/settings桥、既有worker生命周期 | 不改JSON结构、ID、路径格式；不在切页扫描；不重建线程架构或部署依赖 | test_stability_optimizations.py；b21c22f |

历史提交均为当前仓库可查参考，执行期先确认测试入口仍适用。源码有mock兼容分支不代表正式功能未接入；相反，mock成功不能证明真实业务成功。

## 阻断与恢复

任何契约失败：停止下一个迁移点，记录触发步骤、before/after、播放与选择id、异常与当前HEAD。先判断是否本期视觉patch引入；不为修复视觉随手重写受保护业务。不能把失败的检查删掉或把未执行项写PASS。回退只针对经确认的本期改动，保留用户已有文件与数据。

## 本次交接实际执行范围

仅修复Online HTML原型URL草稿并运行其Chromium/Playwright验证；188场景、50检查PASS，无新截图。正式Python未修改，正式播放/跨屏/安装回归测试未执行。本文件中的测试是未来实施要求，不是本轮测试成绩。
