import os
import sys
import time
from argparse import ArgumentParser
from typing import Sequence

PROCESS_STARTED_AT = time.perf_counter()

qt_import_started_at = time.perf_counter()
from PySide6.QtCore import QTimer
from app.startup import create_application_context
print(f"[startup] PySide6 导入：{(time.perf_counter() - qt_import_started_at) * 1000:.1f} ms")


def parse_startup_arguments(argv: Sequence[str] | None = None):
    parser = ArgumentParser(
        prog=(list(argv)[0] if argv else None),
        description="Start HushPlayer.",
    )
    parser.add_argument(
        "--ui-v2",
        action="store_true",
        help="Keep the explicit Quiet Orbit compatibility switch.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use isolated deterministic UI V2 data for development and acceptance.",
    )
    return parser.parse_args(list(argv)[1:] if argv is not None else None)


def _install_packaging_node_smoke(app, window) -> None:
    smoke_exit_text = str(
        os.environ.get("HUSHPLAYER_PACKAGING_SMOKE_EXIT_MS") or ""
    ).strip()
    if not smoke_exit_text:
        return
    try:
        smoke_exit_ms = max(500, int(smoke_exit_text))
    except ValueError:
        smoke_exit_ms = 0
    if not smoke_exit_ms:
        return

    def fail_packaging_node_smoke(message: str) -> None:
        print(
            f"[packaging-smoke] Node runner failed: {message}",
            file=sys.stderr,
        )
        app.exit(2)

    def start_packaging_node_smoke() -> None:
        client = getattr(window, "online_source_client", None)
        if client is None:
            fail_packaging_node_smoke(
                "online source client is unavailable"
            )
            return
        client.sourceReady.connect(
            lambda _data: print(
                "[packaging-smoke] Node runner ready"
            )
        )
        client.processError.connect(fail_packaging_node_smoke)
        client.requestFailed.connect(
            lambda _request_id, _action, message: (
                fail_packaging_node_smoke(message)
            )
        )
        client.ping(timeout_ms=max(1000, smoke_exit_ms - 1000))

    QTimer.singleShot(0, start_packaging_node_smoke)
    QTimer.singleShot(smoke_exit_ms, window.close)


def _install_startup_smoke_exit(app, window) -> None:
    """Close an isolated startup smoke without starting optional services."""

    smoke_exit_text = str(os.environ.get("HUSHPLAYER_STARTUP_SMOKE_EXIT_MS") or "").strip()
    if not smoke_exit_text:
        return
    try:
        smoke_exit_ms = max(100, int(smoke_exit_text))
    except ValueError:
        return
    QTimer.singleShot(smoke_exit_ms, window.close)
    QTimer.singleShot(smoke_exit_ms + 50, app.quit)


def run_legacy_application(argv: Sequence[str] | None = None) -> int:
    app_started_at = time.perf_counter()
    context = create_application_context(
        argv if argv is not None else sys.argv,
        startup_started_at=PROCESS_STARTED_AT,
        ui_flavor="legacy",
    )
    app = context.app
    print(f"[startup] QApplication 创建：{(time.perf_counter() - app_started_at) * 1000:.1f} ms")

    window_import_started_at = time.perf_counter()
    from app.ui.main_window import MainWindow, apply_dark_application_theme
    print(f"[startup] 主窗口模块导入：{(time.perf_counter() - window_import_started_at) * 1000:.1f} ms")

    theme_started_at = time.perf_counter()
    apply_dark_application_theme(app)
    print(f"[startup] 应用主题：{(time.perf_counter() - theme_started_at) * 1000:.1f} ms")

    window_started_at = time.perf_counter()
    window = MainWindow()
    window.setWindowIcon(context.icon)
    print(f"[startup] MainWindow 构造：{(time.perf_counter() - window_started_at) * 1000:.1f} ms")

    show_started_at = time.perf_counter()
    window.show()
    print(f"[startup] window.show：{(time.perf_counter() - show_started_at) * 1000:.1f} ms")
    QTimer.singleShot(
        0,
        lambda: print(
            f"[startup] 首轮事件循环：{(time.perf_counter() - PROCESS_STARTED_AT) * 1000:.1f} ms"
        ),
    )
    _install_packaging_node_smoke(app, window)
    _install_startup_smoke_exit(app, window)
    return app.exec()


def run_ui_v2_from_main(
    argv: Sequence[str] | None = None,
    *,
    data_mode: str = "real",
) -> int:
    from app.ui_v2.startup import run_ui_v2_application

    try:
        return run_ui_v2_application(
            argv if argv is not None else sys.argv,
            data_mode=data_mode,
        )
    except Exception as error:
        print(f"[startup] UI V2 启动失败：{error}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_startup_arguments(argv if argv is not None else sys.argv)
    return run_ui_v2_from_main(
        argv if argv is not None else sys.argv,
        data_mode="mock" if arguments.mock else "real",
    )


if __name__ == "__main__":
    raise SystemExit(main())
