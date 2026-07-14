import sys
import time

PROCESS_STARTED_AT = time.perf_counter()

qt_import_started_at = time.perf_counter()
from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from app.core.app_paths import APP_NAME, APP_VERSION
print(f"[startup] PySide6 导入：{(time.perf_counter() - qt_import_started_at) * 1000:.1f} ms")

window_import_started_at = time.perf_counter()
from app.ui.main_window import MainWindow, apply_dark_application_theme
print(f"[startup] 主窗口模块导入：{(time.perf_counter() - window_import_started_at) * 1000:.1f} ms")


def main() -> None:
    QCoreApplication.setOrganizationName(APP_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app_started_at = time.perf_counter()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setProperty("hushStartupStartedAt", PROCESS_STARTED_AT)
    print(f"[startup] QApplication 创建：{(time.perf_counter() - app_started_at) * 1000:.1f} ms")

    theme_started_at = time.perf_counter()
    apply_dark_application_theme(app)
    print(f"[startup] 应用主题：{(time.perf_counter() - theme_started_at) * 1000:.1f} ms")

    window_started_at = time.perf_counter()
    window = MainWindow()
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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
