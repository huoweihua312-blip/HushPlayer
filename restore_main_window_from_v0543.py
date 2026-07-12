import py_compile
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_WINDOW = PROJECT_ROOT / "app" / "ui" / "main_window.py"
BACKUP_CLEAN = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_v0543"
BROKEN_BACKUP = PROJECT_ROOT / "app" / "ui" / "main_window.py.bak_codex_mojibake_before_restore"


def main() -> None:
    if not MAIN_WINDOW.exists():
        raise FileNotFoundError(f"找不到当前文件：{MAIN_WINDOW}")

    if not BACKUP_CLEAN.exists():
        raise FileNotFoundError(
            f"找不到干净备份：{BACKUP_CLEAN}\n"
            "请确认 app/ui 目录里有 main_window.py.bak_v0543。"
        )

    shutil.copy2(MAIN_WINDOW, BROKEN_BACKUP)
    shutil.copy2(BACKUP_CLEAN, MAIN_WINDOW)

    py_compile.compile(str(MAIN_WINDOW), doraise=True)

    print("已备份乱码文件到：")
    print(BROKEN_BACKUP)
    print()
    print("已从干净备份恢复：")
    print(BACKUP_CLEAN)
    print()
    print("语法检查通过。现在可以运行：")
    print(r".\.venv\Scripts\python.exe main.py")


if __name__ == "__main__":
    main()
