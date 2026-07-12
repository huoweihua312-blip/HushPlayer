import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v049"


NEW_IMMERSIVE_CLASS = r'''class ImmersiveLyricsWindow(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()

        self.main_window = main_window
        self.transparent_mode = True
        self.cover_background_enabled = True
        self.background_alpha = 68
        self.cover_background_pixmap = None
        self.ui_visible = True
        self.auto_hide_enabled = True

        self.setWindowTitle("HushPlayer 沉浸歌词")
        self.setObjectName("immersiveLyricsWindow")
        self.setMinimumSize(900, 620)
        self.setMouseTracking(True)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowOpacity(1.0)

        self.hide_ui_timer = QTimer(self)
        self.hide_ui_timer.setSingleShot(True)
        self.hide_ui_timer.timeout.connect(self.hide_controls_if_needed)

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
        self.background_panel.setMouseTracking(True)
        self.background_panel.installEventFilter(self)

        outer_layout.addWidget(self.background_panel)

        layout = QVBoxLayout(self.background_panel)
        layout.setContentsMargins(46, 34, 46, 34)
        layout.setSpacing(22)

        self.control_header = QFrame()
        self.control_header.setObjectName("immersiveControlHeader")
        self.control_header.setMouseTracking(True)
        self.control_header.installEventFilter(self)

        header = QHBoxLayout(self.control_header)
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

        self.auto_hide_btn = QPushButton("常显 UI")
        self.auto_hide_btn.setObjectName("immersiveButton")
        self.auto_hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_hide_btn.clicked.connect(self.toggle_auto_hide)

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
        button_box.addWidget(self.auto_hide_btn)
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
        self.lyrics_view.setMouseTracking(True)
        self.lyrics_view.installEventFilter(self)

        if self.lyrics_view.viewport():
            self.lyrics_view.viewport().setMouseTracking(True)
            self.lyrics_view.viewport().installEventFilter(self)

        self.lyrics_view.set_placeholder(
            "还没有正在播放的歌词",
            "播放一首歌后，这里会显示沉浸歌词",
        )

        self.footer = QLabel("移动鼠标显示控制栏 · Esc 退出沉浸 · 当前：封面模糊背景")
        self.footer.setObjectName("immersiveFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.setMouseTracking(True)
        self.footer.installEventFilter(self)

        layout.addWidget(self.control_header)
        layout.addWidget(self.lyrics_view, 1)
        layout.addWidget(self.footer)

        self.apply_immersive_style()
        self.show_controls_temporarily()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.Enter,
            QEvent.Type.MouseButtonPress,
        ):
            self.show_controls_temporarily()

        return super().eventFilter(watched, event)

    def mouseMoveEvent(self, event) -> None:
        self.show_controls_temporarily()
        super().mouseMoveEvent(event)

    def show_controls_temporarily(self) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)

        if not self.ui_visible:
            self.control_header.show()
            self.footer.show()
            self.ui_visible = True

        if self.auto_hide_enabled:
            self.hide_ui_timer.start(2200)

    def hide_controls_if_needed(self) -> None:
        if not self.auto_hide_enabled:
            return

        if not self.isVisible():
            return

        self.control_header.hide()
        self.footer.hide()
        self.ui_visible = False
        self.setCursor(Qt.CursorShape.BlankCursor)

    def toggle_auto_hide(self) -> None:
        self.auto_hide_enabled = not self.auto_hide_enabled

        if self.auto_hide_enabled:
            self.auto_hide_btn.setText("常显 UI")
            self.show_controls_temporarily()
        else:
            self.hide_ui_timer.stop()
            self.control_header.show()
            self.footer.show()
            self.ui_visible = True
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.auto_hide_btn.setText("隐藏 UI")

        self.apply_immersive_style()

    def apply_immersive_style(self) -> None:
        self.setWindowOpacity(1.0)

        if self.transparent_mode:
            alpha = max(0, min(255, int(self.background_alpha / 100 * 255)))
            background = f"rgba(5, 6, 9, {alpha})"
            button_background = "rgba(31, 35, 44, 190)"
            mode_name = "封面模糊背景" if self.cover_background_enabled else "半透明纯色背景"
            footer_text = f"移动鼠标显示控制栏 · Esc 退出沉浸 · 当前：{mode_name} · 遮罩不透明度 {self.background_alpha}%"
            button_text = "切换纯黑"
            slider_enabled = True
        else:
            background = "#050609"
            button_background = "#1f232c"
            footer_text = "移动鼠标显示控制栏 · Esc 退出沉浸 · 当前：纯黑背景"
            button_text = "切换半透明"
            slider_enabled = False

        if self.cover_background_enabled:
            cover_button_text = "切换纯色"
        else:
            cover_button_text = "切换封面"

        if self.auto_hide_enabled:
            auto_hide_text = "常显 UI"
        else:
            auto_hide_text = "隐藏 UI"

        self.footer.setText(footer_text)
        self.transparent_btn.setText(button_text)
        self.cover_bg_btn.setText(cover_button_text)
        self.auto_hide_btn.setText(auto_hide_text)
        self.alpha_label.setText(f"遮罩不透明度 {self.background_alpha}%")
        self.alpha_slider.setEnabled(slider_enabled)

        self.setStyleSheet(
            "QWidget#immersiveLyricsWindow { background: transparent; color: #ffffff; font-family: 'Microsoft YaHei UI'; }"
            f"QFrame#immersiveBackgroundPanel {{ background: {background}; }}"
            "QFrame#immersiveControlHeader { background: transparent; }"
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
        self.show_controls_temporarily()

    def toggle_cover_background(self) -> None:
        self.cover_background_enabled = not self.cover_background_enabled
        self.apply_immersive_style()
        self.show_controls_temporarily()

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
        self.show_controls_temporarily()

    def show_windowed(self) -> None:
        self.showNormal()
        self.resize(1100, 720)
        self.raise_()
        self.activateWindow()
        self.show_controls_temporarily()

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

        if event.key() == Qt.Key.Key_Space:
            self.toggle_auto_hide()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.setWindowOpacity(1.0)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hide_ui_timer.stop()

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
        raise RuntimeError("没有找到 ImmersiveLyricsWindow 类。请先确认已经升级到 v0.4.9。")

    return pattern.sub("\n" + NEW_IMMERSIVE_CLASS.strip() + "\n\nclass MainWindow(QMainWindow):", text, count=1)


def ensure_qtcore_imports(text: str) -> str:
    match = re.search(r"from PySide6\.QtCore import \((.*?)\)", text, flags=re.S)

    if match:
        imports_block = match.group(1)
        names = [name.strip().rstrip(",") for name in imports_block.splitlines() if name.strip()]
        needed = ["QEvent", "QTimer"]

        for needed_name in needed:
            if needed_name not in names:
                names.append(needed_name)

        sorted_names = sorted(set(names), key=lambda x: x.lower())
        new_block = "from PySide6.QtCore import (\n" + "".join(f"    {name},\n" for name in sorted_names) + ")"
        return text[:match.start()] + new_block + text[match.end():]

    if "from PySide6.QtCore import " in text:
        line_match = re.search(r"from PySide6\.QtCore import ([^\n]+)", text)

        if line_match:
            names = [name.strip() for name in line_match.group(1).split(",")]
            for needed_name in ("QEvent", "QTimer"):
                if needed_name not in names:
                    names.append(needed_name)

            new_line = "from PySide6.QtCore import " + ", ".join(names)
            return text[:line_match.start()] + new_line + text[line_match.end():]

    raise RuntimeError("没有找到 PySide6.QtCore 导入位置。")


def ensure_version(text: str) -> str:
    old_versions = (
        "HushPlayer/0.4.9 (local music player prototype)",
        "HushPlayer/0.4.8.4 (local music player prototype)",
    )

    for old in old_versions:
        text = text.replace(old, "HushPlayer/0.4.9.1 (local music player prototype)")

    return text


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.9.1" in text:
        print("当前文件看起来已经升级到 v0.4.9.1 了，不需要重复升级。")
        return

    if "class ImmersiveLyricsWindow(QWidget):" not in text:
        raise RuntimeError("没有找到沉浸歌词窗口。请先确认已经升级到 v0.4.9。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text = ensure_qtcore_imports(text)
    text = ensure_version(text)
    text = replace_immersive_class(text)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
    print("升级完成：v0.4.9.1 沉浸歌词自动隐藏 UI 已加入。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
