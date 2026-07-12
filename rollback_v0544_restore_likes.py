import py_compile
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"

CURRENT_BROKEN_BACKUP = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_broken_v0544_like_layout"

RESTORE_CANDIDATES = [
    PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0543",
    PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0542",
    PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0541",
]


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到当前文件：{MAIN_WINDOW_FILE}")

    restore_file = None

    for candidate in RESTORE_CANDIDATES:
        if candidate.exists():
            restore_file = candidate
            break

    if restore_file is None:
        candidates_text = "\n".join(str(path) for path in RESTORE_CANDIDATES)
        raise FileNotFoundError(
            "没有找到可恢复的备份文件。\n"
            "我尝试找这些文件：\n"
            f"{candidates_text}\n\n"
            "请把这个报错发给我，我会换一种方式修。"
        )

    shutil.copy2(MAIN_WINDOW_FILE, CURRENT_BROKEN_BACKUP)
    shutil.copy2(restore_file, MAIN_WINDOW_FILE)

    py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)

    print(f"已备份当前问题文件：{CURRENT_BROKEN_BACKUP}")
    print(f"已恢复到：{restore_file}")
    print("恢复完成。现在可以运行：python main.py")
    print("这一步的目标是先把“我喜欢”和收藏按钮恢复正常。")


if __name__ == "__main__":
    main()
