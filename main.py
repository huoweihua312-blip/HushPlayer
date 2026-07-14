import ctypes
import os
import sys
import time

PROCESS_STARTED_AT = time.perf_counter()

qt_import_started_at = time.perf_counter()
from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication
from app.core.app_paths import APP_NAME, APP_VERSION, AppPaths
print(f"[startup] PySide6 导入：{(time.perf_counter() - qt_import_started_at) * 1000:.1f} ms")

window_import_started_at = time.perf_counter()
from app.ui.main_window import MainWindow, apply_dark_application_theme
print(f"[startup] 主窗口模块导入：{(time.perf_counter() - window_import_started_at) * 1000:.1f} ms")


def main() -> None:
    QCoreApplication.setOrganizationName(APP_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "HushPlayer.Desktop.0.5"
        )
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app_started_at = time.perf_counter()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app_icon = QIcon(
        str(
            AppPaths.resolve().resource_path(
                "assets",
                "icons",
                "HushPlayer.ico",
            )
        )
    )
    app.setWindowIcon(app_icon)
    app.setProperty("hushStartupStartedAt", PROCESS_STARTED_AT)
    print(f"[startup] QApplication 创建：{(time.perf_counter() - app_started_at) * 1000:.1f} ms")

    theme_started_at = time.perf_counter()
    apply_dark_application_theme(app)
    print(f"[startup] 应用主题：{(time.perf_counter() - theme_started_at) * 1000:.1f} ms")

    window_started_at = time.perf_counter()
    window = MainWindow()
    window.setWindowIcon(app_icon)
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
    smoke_exit_text = str(
        os.environ.get("HUSHPLAYER_PACKAGING_SMOKE_EXIT_MS") or ""
    ).strip()
    if smoke_exit_text:
        try:
            smoke_exit_ms = max(500, int(smoke_exit_text))
        except ValueError:
            smoke_exit_ms = 0
        if smoke_exit_ms:
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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
