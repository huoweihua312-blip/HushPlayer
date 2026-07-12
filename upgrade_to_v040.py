from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v039"


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f"没有找到需要替换的位置：{name}")

    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, content: str, name: str) -> str:
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{name}")

    return text.replace(marker, content + marker, 1)


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.0" in text:
        print("当前文件看起来已经升级到 v0.4.0 了，不需要重复升级。")
        return

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = replace_once(
        text,
        '''        self.playlists_file = self.project_root / "data" / "playlists.json"
        self.cover_cache_dir = self.project_root / "cache" / "covers"
''',
        '''        self.playlists_file = self.project_root / "data" / "playlists.json"
        self.stats_file = self.project_root / "data" / "stats.json"
        self.cover_cache_dir = self.project_root / "cache" / "covers"
''',
        "添加 stats_file",
    )

    text = replace_once(
        text,
        '''        self.playlists = self.load_playlists()

        self.http_headers = {
            "User-Agent": "HushPlayer/0.3.9 (local music player prototype)",
''',
        '''        self.playlists = self.load_playlists()
        self.song_stats = self.load_song_stats()

        self.last_recorded_position = 0
        self.pending_listen_ms = 0
        self.current_session_listen_ms = 0
        self.play_count_marked = False

        self.http_headers = {
            "User-Agent": "HushPlayer/0.4.0 (local music player prototype)",
''',
        "初始化播放统计",
    )

    text = replace_once(
        text,
        '''        print("歌单保存位置：", self.playlists_file)
        print("封面缓存位置：", self.cover_cache_dir)
''',
        '''        print("歌单保存位置：", self.playlists_file)
        print("播放统计保存位置：", self.stats_file)
        print("封面缓存位置：", self.cover_cache_dir)
''',
        "打印 stats 文件路径",
    )

    text = replace_once(
        text,
        '''        self.now_artist.setFixedWidth(292)

        now_info_layout.addWidget(self.now_song_title)
        now_info_layout.addWidget(self.now_artist)
''',
        '''        self.now_artist.setFixedWidth(292)

        self.now_stats = QLabel("播放 0 次 · 累计 0:00")
        self.now_stats.setObjectName("nowStats")
        self.now_stats.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.now_stats.setFixedWidth(292)

        now_info_layout.addWidget(self.now_song_title)
        now_info_layout.addWidget(self.now_artist)
        now_info_layout.addWidget(self.now_stats)
''',
        "添加右侧播放统计 label",
    )

    stats_methods = r'''    def load_song_stats(self) -> dict:
        if not self.stats_file.exists():
            return {}

        try:
            with self.stats_file.open("r", encoding="utf-8") as file:
                raw_stats = json.load(file)

            if not isinstance(raw_stats, dict):
                return {}

            cleaned_stats = {}

            for path, stats in raw_stats.items():
                if not isinstance(stats, dict):
                    continue

                normalized_path = self.normalize_song_path(path)

                if not normalized_path:
                    continue

                cleaned_stats[normalized_path] = {
                    "play_count": max(0, int(stats.get("play_count", 0))),
                    "total_listen_time": max(0, int(stats.get("total_listen_time", 0))),
                    "last_played": max(0, int(stats.get("last_played", 0))),
                }

            return cleaned_stats

        except Exception as error:
            print("读取播放统计失败：", error)
            return {}

    def save_song_stats(self) -> None:
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        with self.stats_file.open("w", encoding="utf-8") as file:
            json.dump(self.song_stats, file, ensure_ascii=False, indent=2)

        print("播放统计已保存：", self.stats_file)

    def get_song_stats(self, path: str | None) -> dict | None:
        normalized_path = self.normalize_song_path(path)

        if not normalized_path:
            return None

        if normalized_path not in self.song_stats:
            self.song_stats[normalized_path] = {
                "play_count": 0,
                "total_listen_time": 0,
                "last_played": 0,
            }

        return self.song_stats[normalized_path]

    def format_listen_time(self, seconds: int) -> str:
        seconds = max(0, int(seconds))

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"

        return f"{minutes}:{remaining_seconds:02d}"

    def update_current_song_stats_label(self) -> None:
        if not hasattr(self, "now_stats"):
            return

        if not self.current_song_path:
            self.now_stats.setText("播放 0 次 · 累计 0:00")
            return

        stats = self.get_song_stats(self.current_song_path)

        if not stats:
            self.now_stats.setText("播放 0 次 · 累计 0:00")
            return

        play_count = int(stats.get("play_count", 0))
        total_listen_time = int(stats.get("total_listen_time", 0))
        formatted_time = self.format_listen_time(total_listen_time)

        self.now_stats.setText(f"播放 {play_count} 次 · 累计 {formatted_time}")

    def reset_playback_stats_session(self) -> None:
        self.last_recorded_position = 0
        self.pending_listen_ms = 0
        self.current_session_listen_ms = 0
        self.play_count_marked = False

    def record_listen_progress(self, position: int) -> None:
        if not self.current_song_path:
            self.last_recorded_position = position
            return

        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.last_recorded_position = position
            return

        if self.last_recorded_position <= 0:
            self.last_recorded_position = position
            return

        delta = position - self.last_recorded_position
        self.last_recorded_position = position

        if delta <= 0:
            return

        if delta > 5000:
            return

        self.pending_listen_ms += delta
        self.current_session_listen_ms += delta

        self.mark_current_song_played_if_needed()

        if self.pending_listen_ms >= 10000:
            self.flush_current_listen_time()

    def mark_current_song_played_if_needed(self) -> None:
        if self.play_count_marked:
            return

        if not self.current_song_path:
            return

        threshold = 30000

        if self.current_duration > 0:
            threshold = min(30000, max(8000, int(self.current_duration * 0.3)))

        if self.current_session_listen_ms < threshold:
            return

        stats = self.get_song_stats(self.current_song_path)

        if not stats:
            return

        stats["play_count"] = int(stats.get("play_count", 0)) + 1
        stats["last_played"] = int(time.time())

        self.play_count_marked = True
        self.save_song_stats()
        self.update_current_song_stats_label()

        print("本次播放已计入播放次数：", self.current_song_path)

    def flush_current_listen_time(self) -> None:
        if not self.current_song_path:
            self.pending_listen_ms = 0
            return

        saved_seconds = self.pending_listen_ms // 1000
        self.pending_listen_ms = self.pending_listen_ms % 1000

        if saved_seconds <= 0:
            return

        stats = self.get_song_stats(self.current_song_path)

        if not stats:
            return

        stats["total_listen_time"] = int(stats.get("total_listen_time", 0)) + int(saved_seconds)
        stats["last_played"] = int(time.time())

        self.save_song_stats()
        self.update_current_song_stats_label()

        print(f"已累计听歌时长：{saved_seconds} 秒")

'''

    text = insert_before(
        text,
        '''    def save_settings(self) -> None:
''',
        stats_methods,
        "插入播放统计函数",
    )

    text = replace_once(
        text,
        '''        print(f"你点击了：{title} - {artist}")

        self.current_song_path = file_path if file_path else None
''',
        '''        print(f"你点击了：{title} - {artist}")

        self.flush_current_listen_time()
        self.current_song_path = file_path if file_path else None
        self.reset_playback_stats_session()
''',
        "select_song 切歌前保存统计",
    )

    text = replace_once(
        text,
        '''        self.setWindowTitle(f"{title} - HushPlayer")
        self.update_like_button()
''',
        '''        self.setWindowTitle(f"{title} - HushPlayer")
        self.update_like_button()
        self.update_current_song_stats_label()
''',
        "select_song 更新统计显示",
    )

    text = replace_once(
        text,
        '''    def reset_now_playing_info(self) -> None:
        self.current_song_path = None
''',
        '''    def reset_now_playing_info(self) -> None:
        self.flush_current_listen_time()
        self.current_song_path = None
        self.reset_playback_stats_session()
''',
        "reset_now_playing_info 保存统计",
    )

    text = replace_once(
        text,
        '''        self.bottom_song_title.setText("未播放")
        self.bottom_song_artist.setText("请选择一首音乐")
''',
        '''        self.bottom_song_title.setText("未播放")
        self.bottom_song_artist.setText("请选择一首音乐")

        if hasattr(self, "now_stats"):
            self.now_stats.setText("播放 0 次 · 累计 0:00")
''',
        "reset_now_playing_info 重置统计文字",
    )

    text = replace_once(
        text,
        '''        self.media_player.play()
        self.play_btn.setText("暂停")
''',
        '''        self.last_recorded_position = self.media_player.position()
        self.media_player.play()
        self.play_btn.setText("暂停")
''',
        "播放时初始化统计位置",
    )

    text = replace_once(
        text,
        '''        self.media_player.setPosition(target_position)
''',
        '''        self.media_player.setPosition(target_position)
        self.last_recorded_position = target_position
''',
        "拖动进度条后重置统计位置",
    )

    text = replace_once(
        text,
        '''        progress = int(position * 100 / self.current_duration)
        self.progress_slider.setValue(progress)

        self.lyrics_view.update_by_position(position, self.current_lyrics)
''',
        '''        progress = int(position * 100 / self.current_duration)
        self.progress_slider.setValue(progress)

        self.record_listen_progress(position)
        self.lyrics_view.update_by_position(position, self.current_lyrics)
''',
        "播放进度变化时记录听歌时间",
    )

    text = replace_once(
        text,
        '''        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("暂停")
        else:
            self.play_btn.setText("播放")
''',
        '''        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("暂停")
        else:
            self.play_btn.setText("播放")
            self.flush_current_listen_time()
''',
        "暂停或停止时保存听歌时间",
    )

    text = replace_once(
        text,
        '''        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.handle_song_finished()
''',
        '''        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.flush_current_listen_time()
            self.handle_song_finished()
''',
        "歌曲结束时保存听歌时间",
    )

    text = insert_before(
        text,
        '''    def _style_sheet(self) -> str:
''',
        '''    def closeEvent(self, event) -> None:
        self.flush_current_listen_time()
        self.save_song_stats()
        super().closeEvent(event)

''',
        "关闭窗口时保存播放统计",
    )

    text = replace_once(
        text,
        '''        QLabel#nowArtist {
            color: #9096a3;
            font-size: 13px;
        }
''',
        '''        QLabel#nowArtist {
            color: #9096a3;
            font-size: 13px;
        }

        QLabel#nowStats {
            color: #6f7786;
            font-size: 12px;
        }
''',
        "添加 nowStats 样式",
    )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.0 播放统计系统已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()