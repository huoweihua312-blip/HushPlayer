import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v047"


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

    return text.replace(marker, content.rstrip() + "\n\n" + marker, 1)


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.7.1" in text:
        print("当前文件看起来已经升级到 v0.4.7.1 了，不需要重复升级。")
        return

    if "def _create_full_lyrics_page" not in text:
        raise RuntimeError("没有找到 v0.4.7 的单独歌词页面代码。请先确认已经升级到 v0.4.7。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.7 (local music player prototype)",
        "HushPlayer/0.4.7.1 (local music player prototype)",
    )

    old_lyrics_widget = '''        self.lyrics_view = LyricsView()

        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(now_info_box)
        layout.addSpacing(6)
        layout.addWidget(self.lyrics_view, 1)

        return panel
'''

    new_lyrics_widget = '''        self.lyrics_view = LyricsView()

        self.side_info_panel = QFrame()
        self.side_info_panel.setObjectName("sideInfoPanel")
        self.side_info_panel.hide()

        side_info_layout = QVBoxLayout(self.side_info_panel)
        side_info_layout.setContentsMargins(4, 8, 4, 8)
        side_info_layout.setSpacing(10)

        side_info_title = QLabel("歌曲信息")
        side_info_title.setObjectName("sideInfoTitle")

        side_info_hint = QLabel("歌词页打开时，这里显示当前浏览歌曲的信息。")
        side_info_hint.setObjectName("sideInfoHint")
        side_info_hint.setWordWrap(True)

        self.side_artist_detail = ElidedLabel("未知艺术家")
        self.side_album_detail = ElidedLabel("未知专辑")
        self.side_like_detail = QLabel("未收藏")
        self.side_play_count_detail = QLabel("0 次")
        self.side_listen_time_detail = QLabel("0:00")
        self.side_last_played_detail = QLabel("还没有播放记录")
        self.side_lyrics_status_value = QLabel("等待选择歌曲")
        self.side_file_detail = QLabel("")
        self.side_file_detail.setWordWrap(True)

        side_info_layout.addWidget(side_info_title)
        side_info_layout.addWidget(side_info_hint)
        side_info_layout.addSpacing(4)
        side_info_layout.addWidget(self._create_side_info_row("歌手", self.side_artist_detail))
        side_info_layout.addWidget(self._create_side_info_row("专辑", self.side_album_detail))
        side_info_layout.addWidget(self._create_side_info_row("收藏", self.side_like_detail))
        side_info_layout.addWidget(self._create_side_info_row("播放次数", self.side_play_count_detail))
        side_info_layout.addWidget(self._create_side_info_row("累计时长", self.side_listen_time_detail))
        side_info_layout.addWidget(self._create_side_info_row("最近播放", self.side_last_played_detail))
        side_info_layout.addWidget(self._create_side_info_row("歌词状态", self.side_lyrics_status_value))

        file_box = QFrame()
        file_box.setObjectName("sideInfoRow")
        file_layout = QVBoxLayout(file_box)
        file_layout.setContentsMargins(12, 10, 12, 10)
        file_layout.setSpacing(6)

        file_label = QLabel("文件路径")
        file_label.setObjectName("sideInfoName")

        self.side_file_detail.setObjectName("sideInfoFileValue")

        file_layout.addWidget(file_label)
        file_layout.addWidget(self.side_file_detail)

        side_info_layout.addWidget(file_box)
        side_info_layout.addStretch()

        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(now_info_box)
        layout.addSpacing(6)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.side_info_panel, 1)

        return panel
'''

    if old_lyrics_widget in text:
        text = text.replace(old_lyrics_widget, new_lyrics_widget, 1)
    elif "self.side_info_panel" not in text:
        raise RuntimeError("没有找到右侧歌词区域的替换位置。")

    info_methods = r'''    def _create_side_info_row(self, name: str, value_widget: QWidget) -> QFrame:
        row = QFrame()
        row.setObjectName("sideInfoRow")

        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(4)

        name_label = QLabel(name)
        name_label.setObjectName("sideInfoName")

        value_widget.setObjectName("sideInfoValue")

        layout.addWidget(name_label)
        layout.addWidget(value_widget)

        return row

    def set_right_panel_mode(self, mode: str) -> None:
        if not hasattr(self, "lyrics_view") or not hasattr(self, "side_info_panel"):
            return

        if mode == "info":
            self.lyrics_view.hide()
            self.side_info_panel.show()
            self.update_side_info_panel()
        else:
            self.side_info_panel.hide()
            self.lyrics_view.show()

    def format_last_played_text(self, timestamp: int) -> str:
        timestamp = int(timestamp or 0)

        if timestamp <= 0:
            return "还没有播放记录"

        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
        except Exception:
            return "未知时间"

    def get_current_info_song_data(self) -> dict | None:
        if isinstance(getattr(self, "browsing_song_data", None), dict):
            return self.browsing_song_data

        current_item = self.song_list.currentItem()

        if current_item:
            song_data = current_item.data(Qt.ItemDataRole.UserRole)

            if isinstance(song_data, dict) and not song_data.get("demo"):
                return song_data

        if self.current_song_path:
            return self.find_song_data_by_path(self.current_song_path)

        return None

    def update_side_info_panel(self) -> None:
        if not hasattr(self, "side_info_panel"):
            return

        song_data = self.get_current_info_song_data()

        if not song_data:
            self.side_artist_detail.setText("未知艺术家")
            self.side_album_detail.setText("未知专辑")
            self.side_like_detail.setText("未收藏")
            self.side_play_count_detail.setText("0 次")
            self.side_listen_time_detail.setText("0:00")
            self.side_last_played_detail.setText("还没有播放记录")
            self.side_lyrics_status_value.setText("等待选择歌曲")
            self.side_file_detail.setText("")
            return

        artist = song_data.get("artist", "未知艺术家")
        album = song_data.get("album", "未知专辑")
        song_path = self.normalize_song_path(song_data.get("path", ""))

        stats = self.song_stats.get(
            song_path,
            {
                "play_count": 0,
                "total_listen_time": 0,
                "last_played": 0,
            },
        )

        play_count = int(stats.get("play_count", 0))
        total_listen_time = int(stats.get("total_listen_time", 0))
        last_played = int(stats.get("last_played", 0))

        if hasattr(self, "lyrics_status_label"):
            lyrics_status = self.lyrics_status_label.text().replace("歌词：", "").strip()
        else:
            lyrics_status = "未知"

        self.side_artist_detail.setText(str(artist))
        self.side_album_detail.setText(str(album))
        self.side_like_detail.setText("已收藏" if self.is_song_liked(song_path) else "未收藏")
        self.side_play_count_detail.setText(f"{play_count} 次")
        self.side_listen_time_detail.setText(self.format_listen_time(total_listen_time))
        self.side_last_played_detail.setText(self.format_last_played_text(last_played))
        self.side_lyrics_status_value.setText(lyrics_status or "未知")
        self.side_file_detail.setText(song_path)
'''

    if "def set_right_panel_mode" not in text:
        text = insert_before(
            text,
            '''    def _create_full_lyrics_page(self) -> QFrame:
''',
            info_methods,
            "插入右侧信息面板方法",
        )

    new_show_library_page = r'''    def show_library_page(self) -> None:
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentIndex(0)

        self.set_right_panel_mode("lyrics")
'''

    new_show_liked_playlist_page = r'''    def show_liked_playlist_page(self) -> None:
        self.show_library_page()
        self.set_library_view("liked")
'''

    new_show_full_lyrics_page = r'''    def show_full_lyrics_page(self) -> None:
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentIndex(1)

        self.set_right_panel_mode("info")
        self.refresh_full_lyrics_page()
'''

    text = replace_method(text, "show_library_page", new_show_library_page)
    text = replace_method(text, "show_liked_playlist_page", new_show_liked_playlist_page)
    text = replace_method(text, "show_full_lyrics_page", new_show_full_lyrics_page)

    old_status_snippet = '''        if hasattr(self, "full_lyrics_status"):
            self.full_lyrics_status.setText(message)

        QApplication.processEvents()
'''

    new_status_snippet = '''        if hasattr(self, "full_lyrics_status"):
            self.full_lyrics_status.setText(message)

        if hasattr(self, "side_lyrics_status_value"):
            self.side_lyrics_status_value.setText(message)

        QApplication.processEvents()
'''

    if old_status_snippet in text and "self.side_lyrics_status_value.setText(message)" not in text:
        text = text.replace(old_status_snippet, new_status_snippet, 1)

    # 在选择歌曲、收藏变化、播放统计变化后刷新右侧信息面板。
    for needle in (
        "self.update_current_song_stats_label()",
        "self.update_like_button()",
        "self.set_lyrics_status(\"已手动绑定歌词\")",
    ):
        lines = text.splitlines()
        result = []

        for index, line in enumerate(lines):
            result.append(line)

            if needle not in line:
                continue

            next_line = lines[index + 1] if index + 1 < len(lines) else ""

            if "self.update_side_info_panel()" in next_line:
                continue

            indent = line[: len(line) - len(line.lstrip())]
            result.append(indent + "self.update_side_info_panel()")

        text = "\n".join(result) + "\n"

    if "QFrame#sideInfoPanel" not in text:
        style_marker = '''        QLabel#lyricsStatus {
            color: #7c8595;
            font-size: 12px;
        }
'''
        side_info_style = '''        QFrame#sideInfoPanel {
            background: transparent;
            border: none;
        }

        QLabel#sideInfoTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: 800;
        }

        QLabel#sideInfoHint {
            color: #747c8b;
            font-size: 12px;
        }

        QFrame#sideInfoRow {
            background: #111319;
            border: 1px solid #252a35;
            border-radius: 12px;
        }

        QLabel#sideInfoName {
            color: #6f7786;
            font-size: 11px;
            font-weight: 700;
        }

        QLabel#sideInfoValue {
            color: #dfe3ec;
            font-size: 13px;
        }

        QLabel#sideInfoFileValue {
            color: #8d93a1;
            font-size: 11px;
        }
'''
        text = replace_once(
            text,
            style_marker,
            style_marker + "\n" + side_info_style,
            "添加右侧信息面板样式",
        )

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.7.1 歌词页打开时右侧小歌词会隐藏，并显示歌曲信息。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
