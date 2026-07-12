import re
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_FILE = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_fix_v048_indent"


def fix_bad_immersive_update_indent(text: str) -> tuple[str, int]:
    pattern = re.compile(
        r"(?m)^([ \t]*)if self\.immersive_lyrics_window is not None:\n"
        r"[ \t]*self\.immersive_lyrics_window\.update_position\(position, self\.current_lyrics\)"
    )

    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        count += 1
        indent = match.group(1)
        return (
            f"{indent}if self.immersive_lyrics_window is not None:\n"
            f"{indent}    self.immersive_lyrics_window.update_position(position, self.current_lyrics)"
        )

    return pattern.sub(repl, text), count


def main() -> None:
    if not MAIN_WINDOW_FILE.exists():
        raise FileNotFoundError(f"找不到文件：{MAIN_WINDOW_FILE}")

    text = MAIN_WINDOW_FILE.read_text(encoding="utf-8")
    BACKUP_FILE.write_text(text, encoding="utf-8")
    print(f"已备份当前文件：{BACKUP_FILE}")

    text, fixed_count = fix_bad_immersive_update_indent(text)

    if fixed_count == 0:
        print("没有找到典型的沉浸歌词缩进错误块。")
        print("我会继续尝试按行号附近修复。")

        lines = text.splitlines()
        for index, line in enumerate(lines):
            if "if self.immersive_lyrics_window is not None:" not in line:
                continue

            if index + 1 >= len(lines):
                continue

            next_line = lines[index + 1]

            if "self.immersive_lyrics_window.update_position(position, self.current_lyrics)" not in next_line:
                continue

            indent = line[: len(line) - len(line.lstrip())]
            lines[index + 1] = indent + "    self.immersive_lyrics_window.update_position(position, self.current_lyrics)"
            fixed_count += 1

        text = "\n".join(lines) + "\n"

    MAIN_WINDOW_FILE.write_text(text, encoding="utf-8")
    print(f"已修复缩进块数量：{fixed_count}")

    try:
        py_compile.compile(str(MAIN_WINDOW_FILE), doraise=True)
        print("语法检查通过。现在可以运行：python main.py")
    except Exception as error:
        print("语法检查仍未通过，下面是新的错误：")
        print(error)
        raise


if __name__ == "__main__":
    main()
