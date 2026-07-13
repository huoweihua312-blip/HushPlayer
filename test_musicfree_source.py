from __future__ import annotations

import hashlib
import json
from pathlib import Path

import quickjs
import requests


SOURCE_URL = "http://music.haitangw.net/cqapi/qq.js"
OUTPUT_PATH = Path("user_sources") / "qq.js"


def download_source() -> str:
    print(f"正在下载音源：{SOURCE_URL}")

    response = requests.get(
        SOURCE_URL,
        timeout=25,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()

    # 尽量正确判断中文编码
    response.encoding = response.apparent_encoding or "utf-8"
    code = response.text

    if not code.strip():
        raise RuntimeError("服务器返回了空内容")

    if "<html" in code[:1000].lower():
        raise RuntimeError("服务器返回的是 HTML 页面，不是 JavaScript 源码")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(code, encoding="utf-8")

    sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()

    print("下载成功")
    print(f"保存位置：{OUTPUT_PATH.resolve()}")
    print(f"源码大小：{len(code):,} 个字符")
    print(f"SHA-256：{sha256}")

    return code


def static_scan(code: str) -> None:
    print("\n========== 静态扫描 ==========")

    keywords = [
        "module.exports",
        "exports.",
        "require(",
        "fetch(",
        "axios",
        "request(",
        "CryptoJS",
        "Buffer",
        "process.",
        "child_process",
        "eval(",
        "new Function",
        "WebSocket",
        "getMediaSource",
        "getLyric",
        "search",
    ]

    found = False

    for keyword in keywords:
        count = code.count(keyword)
        if count:
            found = True
            print(f"{keyword:<20} 出现 {count} 次")

    if not found:
        print("没有发现常见关键字，脚本可能经过压缩、混淆或加密。")


def quickjs_load_test(code: str) -> None:
    print("\n========== QuickJS 加载测试 ==========")

    ctx = quickjs.Context()

    # 避免脚本无限循环或占用过多内存
    ctx.set_time_limit(3.0)
    ctx.set_memory_limit(64 * 1024 * 1024)
    ctx.set_max_stack_size(1024 * 1024)

    # MusicFree 插件是 CommonJS 模块，先提供最基础的 module/exports
    ctx.eval(
        """
        var module = { exports: {} };
        var exports = module.exports;
        """
    )

    try:
        ctx.eval(code)
    except quickjs.JSException as exc:
        print("音源无法直接在纯 QuickJS 中加载。")
        print("\n第一处错误：")
        print(exc)
        print("\n这是很有价值的测试结果，它能告诉我们缺少哪种宿主能力。")
        return

    print("JavaScript 语法执行成功。")

    try:
        export_types_json = ctx.eval(
            """
            JSON.stringify(
                Object.fromEntries(
                    Object.entries(module.exports).map(
                        ([key, value]) => [key, typeof value]
                    )
                )
            )
            """
        )

        export_types = json.loads(export_types_json or "{}")

        print("\n插件导出内容：")
        if not export_types:
            print("module.exports 为空，插件可能使用了其他导出方式。")
        else:
            print(json.dumps(export_types, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(f"读取 module.exports 失败：{exc}")


def main() -> None:
    try:
        code = download_source()
    except Exception as exc:
        print("\n音源下载失败：")
        print(f"{type(exc).__name__}: {exc}")
        return

    static_scan(code)
    quickjs_load_test(code)


if __name__ == "__main__":
    main()