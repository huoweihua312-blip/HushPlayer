import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0484"


NEW_IMMERSIVE_CLASS = r'''class ImmersiveLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.transparent_mode = True
        self.cover_background_enabled = True
        self.background_alpha = 68
        self.cover_background_pixmap = None

        self.setWindowTitle("HushPlayer 沉浸歌词")
        self.setObjectName("immersiveLyricsWindow")
        self.setMinimumSize(900, 620)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowOpacity(1.0)

        self.cover_background_label = QLabel(self)
        self.cover_background_label.setObjectName("immersiveCoverBackground")
        self.cover_background_label.setScaledContents(True)
        self.cover_background_label.hide()

        self.cover_blur_effect = QGraphicsBlurEffect(self.cover_background_label)
        self.cover_blur_effect.setBlurRadius(42)
        self.cover_background_label.setGraphicsEffect(self.cover_blur_effect)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.background_panel = QFrame()
        self.background_panel.setObjectName("immersiveBackgroundPanel")

        outer_layout.addWidget(self.background_panel)

        layout = QVBoxLayout(self.background_panel)
        layout.setContentsMargins(46, 34, 46, 34)
        layout.setSpacing(22)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(18)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(7)

        self.song_title = ElidedLabel("还没有播放音乐")
        self.song_title.setObjectName("immersiveSongTitle")
        self.song_title.setMinimumWidth(520)

        self.song_artist = ElidedLabel("双击歌曲或右键播放后打开沉浸歌词")
        self.song_artist.setObjectName("immersiveSongArtist")
        self.song_artist.setMinimumWidth(520)

        self.status_label = QLabel("等待播放歌曲")
        self.status_label.setObjectName("immersiveStatus")

        title_box.addWidget(self.song_title)
        title_box.addWidget(self.song_artist)
        title_box.addWidget(self.status_label)

        self.fullscreen_btn = QPushButton("副屏全屏")
        self.fullscreen_btn.setObjectName("immersiveButton")
        self.fullscreen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_btn.clicked.connect(self.show_on_best_screen)

        self.window_btn = QPushButton("窗口模式")
        self.window_btn.setObjectName("immersiveButton")
        self.window_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.window_btn.clicked.connect(self.show_windowed)

        self.transparent_btn = QPushButton("切换纯黑")
        self.transparent_btn.setObjectName("immersiveButton")
        self.transparent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.transparent_btn.clicked.connect(self.toggle_transparent_mode)

        self.cover_bg_btn = QPushButton("切换纯色")
        self.cover_bg_btn.setObjectName("immersiveButton")
        self.cover_bg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cover_bg_btn.clicked.connect(self.toggle_cover_background)

        self.close_btn = QPushButton("退出沉浸")
        self.close_btn.setObjectName("immersiveButton")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)

        button_box = QHBoxLayout()
        button_box.setContentsMargins(0, 0, 0, 0)
        button_box.setSpacing(10)
        button_box.addWidget(self.fullscreen_btn)
        button_box.addWidget(self.window_btn)
        button_box.addWidget(self.transparent_btn)
        button_box.addWidget(self.cover_bg_btn)
        button_box.addWidget(self.close_btn)

        alpha_box = QHBoxLayout()
        alpha_box.setContentsMargins(0, 0, 0, 0)
        alpha_box.setSpacing(10)

        self.alpha_label = QLabel("遮罩不透明度 68%")
        self.alpha_label.setObjectName("immersiveOpacityLabel")

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setObjectName("immersiveOpacitySlider")
        self.alpha_slider.setRange(35, 100)
        self.alpha_slider.setValue(self.background_alpha)
        self.alpha_slider.setFixedWidth(240)
        self.alpha_slider.valueChanged.connect(self.change_background_alpha)

        alpha_box.addWidget(self.alpha_label)
        alpha_box.addWidget(self.alpha_slider)

        control_box = QVBoxLayout()
        control_box.setContentsMargins(0, 0, 0, 0)
        control_box.setSpacing(10)
        control_box.addLayout(button_box)
        control_box.addLayout(alpha_box)

        header.addLayout(title_box, 1)
        header.addLayout(control_box)

        self.lyrics_view = LyricsView()
        self.lyrics_view.setObjectName("immersiveLyricsView")
        self.lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "播放一首歌后，这里会显示沉浸歌词",
        )

        self.footer = QLabel("Esc 退出沉浸 · 当前：封面模糊背景 · 可调节黑色遮罩")
        self.footer.setObjectName("immersiveFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(header)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.footer)

        self.apply_immersive_style()

    def apply_immersive_style(self) -> None:
        self.setWindowOpacity(1.0)

        if self.transparent_mode:
            alpha = max(0, min(255, int(self.background_alpha / 100 * 255)))
            background = f"rgba(5, 6, 9, {alpha})"
            button_background = "rgba(31, 35, 44, 190)"
            mode_name = "封面模糊背景" if self.cover_background_enabled else "半透明纯色背景"
            footer_text = f"Esc 退出沉浸 · 当前：{mode_name} · 遮罩不透明度 {self.background_alpha}%"
            button_text = "切换纯黑"
            slider_enabled = True
        else:
            background = "#050609"
            button_background = "#1f232c"
            footer_text = "Esc 退出沉浸 · 当前：纯黑背景"
            button_text = "切换半透明"
            slider_enabled = False

        if self.cover_background_enabled:
            cover_button_text = "切换纯色"
        else:
            cover_button_text = "切换封面"

        self.footer.setText(footer_text)
        self.transparent_btn.setText(button_text)
        self.cover_bg_btn.setText(cover_button_text)
        self.alpha_label.setText(f"遮罩不透明度 {self.background_alpha}%")
        self.alpha_slider.setEnabled(slider_enabled)

        self.setStyleSheet(
            "QWidget#immersiveLyricsWindow { background: transparent; color: #ffffff; font-family: 'Microsoft YaHei UI'; }"
            f"QFrame#immersiveBackgroundPanel {{ background: {background}; }}"
            "QLabel#immersiveSongTitle { color: #ffffff; font-size: 30px; font-weight: 900; }"
            "QLabel#immersiveSongArtist { color: #d0d5df; font-size: 15px; }"
            "QLabel#immersiveStatus { color: #9aa3b2; font-size: 12px; }"
            "QLabel#immersiveFooter { color: #8e96a5; font-size: 12px; }"
            "QLabel#immersiveOpacityLabel { color: #c7ceda; font-size: 12px; }"
            f"QPushButton#immersiveButton {{ background: {button_background}; color: #dfe3ec; border: none; border-radius: 12px; padding: 10px 14px; font-size: 13px; }}"
            "QPushButton#immersiveButton:hover { background: #2f68d8; color: #ffffff; }"
            "QSlider#immersiveOpacitySlider::groove:horizontal { height: 5px; background: rgba(255,255,255,55); border-radius: 3px; }"
            "QSlider#immersiveOpacitySlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; background: #ffffff; border-radius: 8px; }"
            "QSlider#immersiveOpacitySlider::sub-page:horizontal { background: #2f68d8; border-radius: 3px; }"
            "QSlider#immersiveOpacitySlider:disabled::handle:horizontal { background: #6f7786; }"
            "QScrollArea#immersiveLyricsView, QScrollArea#lyricsView { background: transparent; border: none; }"
            "QWidget#lyricsContent { background: transparent; }"
            "QLabel#lyricPlaceholderTitle { color: #ffffff; font-size: 28px; font-weight: 900; }"
            "QLabel#lyricPlaceholderSubtitle { color: #c1c7d2; font-size: 15px; }"
            "QLabel#lyricLine { color: #8a92a3; font-size: 24px; font-weight: 600; padding: 4px 10px; }"
            "QLabel#lyricLine[lyricState='near'] { color: #d3d8e2; font-size: 31px; font-weight: 800; }"
            "QLabel#lyricLine[lyricState='current'] { color: #ffffff; font-size: 48px; font-weight: 950; }"
        )

        self.refresh_cover_background()

    def change_background_alpha(self, value: int) -> None:
        self.background_alpha = int(value)
        self.apply_immersive_style()

    def toggle_transparent_mode(self) -> None:
        self.transparent_mode = not self.transparent_mode
        self.apply_immersive_style()

    def toggle_cover_background(self) -> None:
        self.cover_background_enabled = not self.cover_background_enabled
        self.apply_immersive_style()

    def update_background_cover(self, pixmap) -> None:
        if pixmap is None or pixmap.isNull():
            self.cover_background_pixmap = None
        else:
            self.cover_background_pixmap = pixmap.copy()

        self.refresh_cover_background()

    def refresh_cover_background(self) -> None:
        if not hasattr(self, "cover_background_label"):
            return

        if (
            not self.transparent_mode
            or not self.cover_background_enabled
            or self.cover_background_pixmap is None
            or self.cover_background_pixmap.isNull()
        ):
            self.cover_background_label.hide()
            return

        target_size = self.size()

        if target_size.width() <= 0 or target_size.height() <= 0:
            self.cover_background_label.hide()
            return

        scaled = self.cover_background_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        crop_x = max(0, (scaled.width() - target_size.width()) // 2)
        crop_y = max(0, (scaled.height() - target_size.height()) // 2)

        cropped = scaled.copy(
            crop_x,
            crop_y,
            target_size.width(),
            target_size.height(),
        )

        self.cover_background_label.setGeometry(self.rect())
        self.cover_background_label.setPixmap(cropped)
        self.cover_background_label.show()
        self.cover_background_label.lower()
        self.background_panel.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_cover_background()

    def show_on_best_screen(self) -> None:
        screens = QApplication.screens()
        target_screen = None

        if len(screens) >= 2:
            target_screen = screens[1]
        elif screens:
            target_screen = screens[0]

        if target_screen:
            self.setGeometry(target_screen.availableGeometry())

        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def show_windowed(self) -> None:
        self.showNormal()
        self.resize(1100, 720)
        self.raise_()
        self.activateWindow()

    def update_song_info(self, title: str, artist_album: str, status: str) -> None:
        self.song_title.setText(title)
        self.song_artist.setText(artist_album)
        self.status_label.setText(status)

    def set_lyrics(self, lyrics: list[tuple[int, str]]) -> None:
        if lyrics:
            self.lyrics_view.set_lyrics(lyrics)
        else:
            self.lyrics_view.set_placeholder(
                "当前歌曲暂无歌词",
                "可以右键歌曲手动绑定歌词，或者重新搜索歌词",
            )

    def update_position(self, position: int, lyrics: list[tuple[int, str]]) -> None:
        self.lyrics_view.update_by_position(position, lyrics)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.setWindowOpacity(1.0)

        if getattr(self.main_window, "immersive_lyrics_window", None) is self:
            self.main_window.immersive_lyrics_window = None

        super().closeEvent(event)
'''


def replace_immersive_class(text: str) -> str:
    pattern = re.compile(
        r"\nclass ImmersiveLyricsWindow\(QWidget\):.*?\n\nclass MainWindow\(QMainWindow\):",
        flags=re.S,
    )

    if not pattern.search(text):
        raise RuntimeError("没有找到 ImmersiveLyricsWindow 类。请先确认已经升级到 v0.4.8.4。")

    return pattern.sub("\n" + NEW_IMMERSIVE_CLASS.strip() + "\n\nclass MainWindow(QMainWindow):", text, count=1)


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def insert_before_method(text: str, marker_method_name: str, content: str) -> str:
    marker = f"\n    def {marker_method_name}("
    if marker not in text:
        raise RuntimeError(f"没有找到插入位置：{marker_method_name}")

    return text.replace(marker, "\n" + content.rstrip() + "\n" + marker, 1)


def ensure_imports(text: str) -> str:
    if "QGraphicsBlurEffect" not in text:
        if "    QFrame,\n" in text:
            text = text.replace("    QFrame,\n", "    QFrame,\n    QGraphicsBlurEffect,\n", 1)
        else:
            raise RuntimeError("没有找到 QFrame 导入位置，无法加入 QGraphicsBlurEffect。")

    if "QPixmap" not in text:
        if "from PySide6.QtGui import (" in text:
            text = text.replace("from PySide6.QtGui import (", "from PySide6.QtGui import (\n    QPixmap,", 1)
        else:
            text = text.replace(
                "from PySide6.QtCore import",
                "from PySide6.QtGui import QPixmap\nfrom PySide6.QtCore import",
                1,
            )

    return text


def ensure_version(text: str) -> str:
    old_versions = (
        "HushPlayer/0.4.8.4 (local music player prototype)",
        "HushPlayer/0.4.8.3 (local music player prototype)",
        "HushPlayer/0.4.8.2 (local music player prototype)",
        "HushPlayer/0.4.8.1 (local music player prototype)",
        "HushPlayer/0.4.8 (local music player prototype)",
    )

    for old in old_versions:
        text = text.replace(old, "HushPlayer/0.4.9 (local music player prototype)")

    return text


COVER_HELPER_METHOD = r'''    def get_immersive_background_pixmap(self, playing_path: str | None):
        normalized_path = self.normalize_song_path(playing_path)

        if not normalized_path:
            return None

        try:
            browsing_path = self.normalize_song_path(getattr(self, "browsing_song_path", ""))

            if browsing_path == normalized_path and hasattr(self, "cover_label"):
                current_pixmap = self.cover_label.pixmap()

                if current_pixmap and not current_pixmap.isNull():
                    return current_pixmap
        except Exception:
            pass

        try:
            cache_path = self.get_song_cache_path(normalized_path, self.cover_cache_dir, ".jpg")

            if cache_path and cache_path.exists():
                cached_pixmap = QPixmap(str(cache_path))

                if not cached_pixmap.isNull():
                    return cached_pixmap
        except Exception as error:
            print("读取沉浸封面缓存失败：", error)

        try:
            song_dir = Path(normalized_path).parent
            cover_names = [
                "cover.jpg",
                "cover.png",
                "cover.jpeg",
                "folder.jpg",
                "folder.png",
                "folder.jpeg",
                "front.jpg",
                "front.png",
                "front.jpeg",
                "album.jpg",
                "album.png",
                "album.jpeg",
            ]

            for cover_name in cover_names:
                cover_path = song_dir / cover_name

                if not cover_path.exists():
                    continue

                folder_pixmap = QPixmap(str(cover_path))

                if not folder_pixmap.isNull():
                    return folder_pixmap
        except Exception as error:
            print("读取沉浸文件夹封面失败：", error)

        return None
'''

NEW_SYNC_IMMERSIVE = r'''    def sync_immersive_lyrics(self) -> None:
        if self.immersive_lyrics_window is None:
            return

        title, artist_album, status = self.get_playing_song_display_data()
        self.immersive_lyrics_window.update_song_info(title, artist_album, status)

        playing_path = self.normalize_song_path(self.current_song_path)
        background_pixmap = self.get_immersive_background_pixmap(playing_path)
        self.immersive_lyrics_window.update_background_cover(background_pixmap)

        displayed_path = self.normalize_song_path(getattr(self, "displayed_lyrics_song_path", ""))

        if playing_path and displayed_path == playing_path and self.current_lyrics:
            self.immersive_lyrics_window.set_lyrics(self.current_lyrics)
            self.immersive_lyrics_window.update_position(
                self.media_player.position(),
                self.current_lyrics,
            )
        else:
            self.immersive_lyrics_window.set_lyrics([])
'''


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.9" in text:
        print("当前文件看起来已经升级到 v0.4.9 了，不需要重复升级。")
        return

    if "class ImmersiveLyricsWindow(QWidget):" not in text:
        raise RuntimeError("没有找到沉浸歌词窗口。请先确认已经升级到 v0.4.8.4。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_imports(text)
    text = ensure_version(text)
    text = replace_immersive_class(text)

    if "def get_immersive_background_pixmap" not in text:
        text = insert_before_method(text, "sync_immersive_lyrics", COVER_HELPER_METHOD)

    text = replace_method(text, "sync_immersive_lyrics", NEW_SYNC_IMMERSIVE)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
    print("升级完成：v0.4.9 沉浸歌词封面模糊背景已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
