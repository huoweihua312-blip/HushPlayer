import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v044"


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


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

    if "HushPlayer/0.4.4.1" in text:
        print("当前文件看起来已经升级到 v0.4.4.1 了，不需要重复升级。")
        return

    if "def search_lrclib_synced_lyrics" not in text:
        raise RuntimeError("没有找到联网歌词函数。请先确认已经升级到 v0.4.4。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.4 (local music player prototype)",
        "HushPlayer/0.4.4.1 (local music player prototype)",
    )

    if "    QApplication,\n" not in text:
        text = text.replace(
            "from PySide6.QtWidgets import (\n",
            "from PySide6.QtWidgets import (\n    QApplication,\n",
            1,
        )

    if "self.browsing_song_path" not in text:
        text = replace_once(
            text,
            '''        self.current_song_path: str | None = None
''',
            '''        self.current_song_path: str | None = None
        self.browsing_song_path: str | None = None
        self.browsing_song_data: dict | None = None
''',
            "添加浏览歌曲状态",
        )

    if "self.lyrics_status_label" not in text:
        text = replace_once(
            text,
            '''        self.now_stats = QLabel("播放 0 次 · 累计 0:00")
        self.now_stats.setObjectName("nowStats")
        self.now_stats.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.now_stats.setFixedWidth(292)

        now_info_layout.addWidget(self.now_song_title)
        now_info_layout.addWidget(self.now_artist)
        now_info_layout.addWidget(self.now_stats)
''',
            '''        self.now_stats = QLabel("播放 0 次 · 累计 0:00")
        self.now_stats.setObjectName("nowStats")
        self.now_stats.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.now_stats.setFixedWidth(292)

        self.lyrics_status_label = QLabel("歌词：等待选择歌曲")
        self.lyrics_status_label.setObjectName("lyricsStatus")
        self.lyrics_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lyrics_status_label.setFixedWidth(292)

        now_info_layout.addWidget(self.now_song_title)
        now_info_layout.addWidget(self.now_artist)
        now_info_layout.addWidget(self.now_stats)
        now_info_layout.addWidget(self.lyrics_status_label)
''',
            "添加歌词状态标签",
        )

    helper_methods = r'''    def get_active_info_song_path(self) -> str:
        if self.browsing_song_path:
            return self.normalize_song_path(self.browsing_song_path)

        return self.normalize_song_path(self.current_song_path)

    def set_lyrics_status(self, message: str) -> None:
        print("歌词状态：", message)

        if hasattr(self, "lyrics_status_label"):
            self.lyrics_status_label.setText(f"歌词：{message}")

        QApplication.processEvents()

    def load_song_for_playback(self, song_data: dict | None) -> None:
        if not isinstance(song_data, dict):
            return

        if song_data.get("demo"):
            return

        title = song_data.get("title", "未知歌曲")
        artist = song_data.get("artist", "未知艺术家")
        file_path = song_data.get("path", "")

        if not file_path:
            return

        normalized_path = self.normalize_song_path(file_path)

        if not normalized_path:
            return

        current_normalized_path = self.normalize_song_path(self.current_song_path)

        if current_normalized_path == normalized_path and self.media_player.source().toString():
            return

        self.flush_current_listen_time()

        self.current_song_path = normalized_path
        self.current_duration = 0
        self.reset_playback_stats_session()

        self.bottom_song_title.setText(title)
        self.bottom_song_artist.setText(artist)

        self.media_player.stop()
        self.media_player.setSource(QUrl.fromLocalFile(self.current_song_path))
        self.progress_slider.setValue(0)

        print("已切换播放器当前歌曲：", title, "-", artist)
        print("文件路径：", self.current_song_path)
        print("已设置 source：", self.media_player.source().toString())

'''

    if "def load_song_for_playback" not in text:
        text = insert_before(
            text,
            '''    def select_song(self, item: QListWidgetItem) -> None:
''',
            helper_methods,
            "插入浏览/播放解耦辅助函数",
        )

    new_update_like_button = r'''    def update_like_button(self) -> None:
        if not hasattr(self, "like_btn"):
            return

        target_path = self.get_active_info_song_path()

        if not target_path:
            self.like_btn.setText("♡ 收藏")
            self.like_btn.setProperty("liked", False)
            self.like_btn.setEnabled(False)
        elif self.is_song_liked(target_path):
            self.like_btn.setText("♥ 已收藏")
            self.like_btn.setProperty("liked", True)
            self.like_btn.setEnabled(True)
        else:
            self.like_btn.setText("♡ 收藏")
            self.like_btn.setProperty("liked", False)
            self.like_btn.setEnabled(True)

        self.like_btn.style().unpolish(self.like_btn)
        self.like_btn.style().polish(self.like_btn)
        self.like_btn.update()
'''

    new_toggle_like_current_song = r'''    def toggle_like_current_song(self) -> None:
        target_path = self.get_active_info_song_path()

        if not target_path:
            print("当前没有可收藏的真实歌曲。")
            return

        liked_songs = self.get_liked_song_paths()

        if target_path in liked_songs:
            liked_songs.remove(target_path)
            print("已取消收藏：", target_path)
        else:
            liked_songs.append(target_path)
            print("已加入我喜欢：", target_path)

        self.save_playlists()
        self.update_like_button()

        if self.current_library_view == "liked":
            self.filter_song_list(self.search_input.text())
'''

    new_update_current_song_stats_label = r'''    def update_current_song_stats_label(self) -> None:
        if not hasattr(self, "now_stats"):
            return

        target_path = self.get_active_info_song_path()

        if not target_path:
            self.now_stats.setText("播放 0 次 · 累计 0:00")
            return

        stats = self.get_song_stats(target_path)

        if not stats:
            self.now_stats.setText("播放 0 次 · 累计 0:00")
            return

        play_count = int(stats.get("play_count", 0))
        total_listen_time = int(stats.get("total_listen_time", 0))
        formatted_time = self.format_listen_time(total_listen_time)

        self.now_stats.setText(f"播放 {play_count} 次 · 累计 {formatted_time}")
'''

    new_select_song = r'''    def select_song(self, item: QListWidgetItem) -> None:
        song_data = item.data(Qt.ItemDataRole.UserRole)

        if isinstance(song_data, dict):
            title = song_data.get("title", "未知歌曲")
            artist = song_data.get("artist", "未知艺术家")
            album = song_data.get("album", "未知专辑")
            file_path = song_data.get("path", "")
        else:
            text = item.text()
            parts = [part.strip() for part in text.split("·")]

            title = parts[0] if len(parts) > 0 else "未知歌曲"
            artist = parts[1] if len(parts) > 1 else "未知艺术家"
            album = parts[2] if len(parts) > 2 else "未知专辑"
            file_path = ""

        print(f"你正在浏览：{title} - {artist}")

        if file_path:
            self.browsing_song_path = self.normalize_song_path(file_path)
            self.browsing_song_data = song_data if isinstance(song_data, dict) else None
        else:
            self.browsing_song_path = None
            self.browsing_song_data = None

        self.now_song_title.setText(title)
        self.now_artist.setText(f"{artist} · {album}")

        self.update_cover(
            file_path=self.browsing_song_path,
            title=title,
            artist=artist,
            album=album,
        )

        self.load_lyrics_for_song(
            file_path=self.browsing_song_path,
            title=title,
            artist=artist,
        )

        self.setWindowTitle(f"浏览：{title} - HushPlayer")
        self.update_like_button()
        self.update_current_song_stats_label()

        if self.browsing_song_path:
            print(f"浏览文件路径：{self.browsing_song_path}")
            print("单击只浏览，不会打断当前播放。双击才会播放这首歌。")
        else:
            print("这是演示歌曲，没有真实音乐文件。")
'''

    new_reset_now_playing_info = r'''    def reset_now_playing_info(self) -> None:
        self.flush_current_listen_time()

        self.current_song_path = None
        self.browsing_song_path = None
        self.browsing_song_data = None

        self.current_duration = 0
        self.current_lyrics = []

        self.reset_playback_stats_session()

        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.progress_slider.setValue(0)

        self.now_song_title.setText("还没有播放音乐")
        self.now_artist.setText("请选择一首歌曲")

        if hasattr(self, "now_stats"):
            self.now_stats.setText("播放 0 次 · 累计 0:00")

        if hasattr(self, "lyrics_status_label"):
            self.lyrics_status_label.setText("歌词：等待选择歌曲")

        self.bottom_song_title.setText("未播放")
        self.bottom_song_artist.setText("请选择一首音乐")
        self.lyrics_view.set_placeholder("这里会显示歌词", "支持本地 .lrc 和联网同步歌词")
        self.reset_cover()
        self.setWindowTitle("HushPlayer")
        self.update_like_button()
'''

    new_play_selected_song = r'''    def play_selected_song(self, item: QListWidgetItem) -> None:
        self.select_song(item)

        song_data = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(song_data, dict):
            return

        self.load_song_for_playback(song_data)
        self.play_current_song()
'''

    new_play_current_song = r'''    def play_current_song(self) -> None:
        if not self.current_song_path:
            current_item = self.song_list.currentItem()

            if current_item:
                song_data = current_item.data(Qt.ItemDataRole.UserRole)

                if isinstance(song_data, dict):
                    self.load_song_for_playback(song_data)

        if not self.current_song_path:
            self.lyrics_view.set_placeholder(
                "请先导入并选择一首真实的本地音乐",
                "单击浏览，双击播放",
            )
            return

        print("准备播放：", self.current_song_path)
        print("当前音量：", self.audio_output.volume())
        print("当前 source：", self.media_player.source().toString())

        self.last_recorded_position = self.media_player.position()
        self.media_player.play()
        self.play_btn.setText("暂停")
'''

    new_load_lyrics_for_song = r'''    def load_lyrics_for_song(
        self,
        file_path: str | None,
        title: str,
        artist: str,
    ) -> None:
        self.current_lyrics = []
        self.lyrics_view.set_placeholder("正在查找歌词", "优先本地歌词，没有就尝试联网搜索")
        self.set_lyrics_status("正在查找歌词")

        if not file_path:
            self.lyrics_view.set_placeholder("歌词功能还没有接入演示歌曲", "")
            self.set_lyrics_status("演示歌曲无歌词")
            return

        music_path = Path(file_path)

        self.set_lyrics_status("正在查找本地歌词")
        lyric_file = self.find_lrc_file(music_path, title, artist)

        if lyric_file:
            self.set_lyrics_status("正在读取本地歌词")
            lyrics = self.parse_lrc_file(lyric_file)

            if lyrics:
                self.current_lyrics = lyrics
                self.lyrics_view.set_lyrics(self.current_lyrics)

                self.set_lyrics_status("已加载本地歌词")
                print(f"已加载本地歌词：{lyric_file}")
                print(f"歌词行数：{len(self.current_lyrics)}")
                return

            print("本地歌词解析失败：", lyric_file)

        self.set_lyrics_status("正在查找缓存歌词")
        cached_lyrics_file = self.get_lyrics_cache_path(music_path)

        if cached_lyrics_file.exists():
            self.set_lyrics_status("正在读取缓存歌词")
            lyrics = self.parse_lrc_file(cached_lyrics_file)

            if lyrics:
                self.current_lyrics = lyrics
                self.lyrics_view.set_lyrics(self.current_lyrics)

                self.set_lyrics_status("已加载缓存歌词")
                print(f"已加载缓存歌词：{cached_lyrics_file}")
                print(f"歌词行数：{len(self.current_lyrics)}")
                return

            print("缓存歌词解析失败，准备重新联网搜索：", cached_lyrics_file)

            try:
                cached_lyrics_file.unlink()
            except Exception:
                pass

        self.lyrics_view.set_placeholder("正在联网搜索同步歌词", "正在搜索 LRCLIB，第一次可能会等几秒")
        self.set_lyrics_status("正在联网搜索 LRCLIB")

        album = "未知专辑"
        current_item = self.song_list.currentItem()

        if current_item:
            song_data = current_item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict):
                album = song_data.get("album", "未知专辑")

        duration_seconds = self.get_audio_duration_seconds(music_path)

        synced_lyrics = self.search_lrclib_synced_lyrics(
            title=title,
            artist=artist,
            album=album,
            duration_seconds=duration_seconds,
        )

        if not synced_lyrics:
            self.lyrics_view.set_placeholder(
                "未找到同步歌词",
                "可以手动放一个同名 .lrc 文件到歌曲旁边",
            )
            self.set_lyrics_status("未找到同步歌词")
            print("未找到联网同步歌词：", title, artist)
            return

        self.set_lyrics_status("已找到歌词，正在写入缓存")
        self.write_lyrics_cache(cached_lyrics_file, synced_lyrics)

        lyrics = self.parse_lrc_file(cached_lyrics_file)

        if not lyrics:
            self.lyrics_view.set_placeholder(
                "联网歌词格式无法解析",
                "可以换成本地 .lrc 歌词",
            )
            self.set_lyrics_status("联网歌词解析失败")
            print("联网歌词写入后解析失败：", cached_lyrics_file)
            return

        self.current_lyrics = lyrics
        self.lyrics_view.set_lyrics(self.current_lyrics)

        self.set_lyrics_status("已加载联网歌词")
        print(f"已加载联网歌词：{title} - {artist}")
        print(f"歌词行数：{len(self.current_lyrics)}")
'''

    text = replace_method(text, "update_like_button", new_update_like_button)
    text = replace_method(text, "toggle_like_current_song", new_toggle_like_current_song)
    text = replace_method(text, "update_current_song_stats_label", new_update_current_song_stats_label)
    text = replace_method(text, "select_song", new_select_song)
    text = replace_method(text, "reset_now_playing_info", new_reset_now_playing_info)
    text = replace_method(text, "play_selected_song", new_play_selected_song)
    text = replace_method(text, "play_current_song", new_play_current_song)
    text = replace_method(text, "load_lyrics_for_song", new_load_lyrics_for_song)

    if "QLabel#lyricsStatus" not in text:
        text = replace_once(
            text,
            '''        QLabel#nowStats {
            color: #6f7786;
            font-size: 12px;
        }
''',
            '''        QLabel#nowStats {
            color: #6f7786;
            font-size: 12px;
        }

        QLabel#lyricsStatus {
            color: #7c8595;
            font-size: 12px;
        }
''',
            "添加歌词状态样式",
        )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.4.1 浏览歌曲不再打断播放，歌词状态提示已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()