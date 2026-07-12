import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow, apply_dark_application_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("HushPlayer")
    apply_dark_application_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
