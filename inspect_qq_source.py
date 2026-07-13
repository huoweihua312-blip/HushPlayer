from pathlib import Path
import re


SOURCE_PATH = Path("user_sources/qq.js")


def main() -> None:
    code = SOURCE_PATH.read_text(encoding="utf-8")

    modules = sorted(
        set(
            re.findall(
                r"""require\(\s*["']([^"']+)["']\s*\)""",
                code,
            )
        )
    )

    print("检测到的 require 模块：")

    if not modules:
        print("没有识别到模块")
    else:
        for module in modules:
            print(f"- {module}")

    print("\nrequire 调用附近的代码：")

    pattern = re.compile(r"""require\(\s*["'][^"']+["']\s*\)""")

    for index, match in enumerate(pattern.finditer(code), start=1):
        start = max(0, match.start() - 100)
        end = min(len(code), match.end() + 100)
        context = code[start:end].replace("\n", " ")

        print(f"\n[{index}] {context}")


if __name__ == "__main__":
    main()