import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0472"


def replace_method(text: str, method_name: str, new_method: str) -> str:
    pattern = rf"\n    def {method_name}\(.*?\n(?=    def |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise RuntimeError(f"没有找到方法：{method_name}")

    return text[:match.start()] + "\n" + new_method.rstrip() + "\n\n" + text[match.end():]


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")

    if "HushPlayer/0.4.7.3" in text:
        print("当前文件看起来已经升级到 v0.4.7.3 了，不需要重复升级。")
        return

    if "def set_right_panel_mode" not in text:
        raise RuntimeError("没有找到右侧面板切换代码。请先确认已经升级到 v0.4.7.2 或 v0.4.7.1。")

    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份旧文件：{BACKUP_FILE}")

    text = text.replace(
        "HushPlayer/0.4.7.2 (local music player prototype)",
        "HushPlayer/0.4.7.3 (local music player prototype)",
    )
    text = text.replace(
        "HushPlayer/0.4.7.1 (local music player prototype)",
        "HushPlayer/0.4.7.3 (local music player prototype)",
    )
    text = text.replace(
        "HushPlayer/0.4.7 (local music player prototype)",
        "HushPlayer/0.4.7.3 (local music player prototype)",
    )

    new_set_right_panel_mode = r'''    def set_right_panel_mode(self, mode: str) -> None:
        if not hasattr(self, "lyrics_view"):
            return

        if hasattr(self, "side_info_panel"):
            self.side_info_panel.hide()

        self.lyrics_view.show()

        lyrics_content = self.lyrics_view.widget()

        if mode == "info":
            if lyrics_content:
                lyrics_content.hide()

            self.lyrics_view.setEnabled(False)
            self.lyrics_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        else:
            if lyrics_content:
                lyrics_content.show()

            self.lyrics_view.setEnabled(True)
            self.lyrics_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
'''

    text = replace_method(text, "set_right_panel_mode", new_set_right_panel_mode)

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print("升级完成：v0.4.7.3 进入歌词页时只隐藏右侧歌词内容，并保留原布局位置。")
    print("现在可以运行：python main.py")


if __name__ == "__main__":
    main()
