from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.ui.search_page import SearchPage


WIDTH_MODES = {
    900: "narrow",
    1100: "compact",
    1400: "compact",
}


def local_track(index: int) -> dict:
    return {
        "title": f"本地歌曲 {index}",
        "artist": "本地歌手",
        "album": "本地专辑",
        "path": f"C:/fixtures/local-{index}.mp3",
        "media_type": "local",
    }


def online_track(index: int) -> dict:
    return {
        "title": f"在线歌曲 {index}",
        "artist": "在线歌手",
        "album": "在线专辑",
        "media_type": "online",
        "source_id": "custom_source_fixture",
        "source_name": "本机模拟来源",
        "track_id": f"remote-{index}",
        "availability": "available",
        "can_play": True,
        "can_download": False,
    }


def process_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def assert_local_page(page: SearchPage) -> None:
    assert page.current_tab() == "local"
    assert page.results_stack.currentWidget() is page.local_container
    assert page.local_container.isVisibleTo(page)
    assert page.local_view.isVisibleTo(page)
    assert not page.online_container.isVisibleTo(page)
    assert not page.online_results.isVisibleTo(page)
    assert page.local_status_label.isVisibleTo(page)


def assert_online_page(page: SearchPage) -> None:
    assert page.current_tab() == "online"
    assert page.results_stack.currentWidget() is page.online_container
    assert page.online_container.isVisibleTo(page)
    assert page.online_results.isVisibleTo(page)
    assert not page.local_container.isVisibleTo(page)
    assert not page.local_view.isVisibleTo(page)
    assert not page.local_status_label.isVisibleTo(page)


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    page = SearchPage(local_only=False)
    page.show()

    for width, mode in WIDTH_MODES.items():
        page.resize(width, 640)
        page.set_responsive_mode(mode)
        process_events(app)

        page.show_tab("local")
        page.set_local_results("不存在", [])
        page.set_online_status("输入至少 2 个字符后才会搜索在线来源。")
        page.set_online_results("不存在", [], {"final": True})
        process_events(app)
        assert_local_page(page)
        assert "找到 0 首歌曲" in page.local_status_label.text()

        # A background online refresh must not reveal the hidden online page.
        page.set_local_results("测试", [local_track(1), local_track(2)])
        page.set_online_results(
            "测试",
            [online_track(1), online_track(2)],
            {"final": True},
        )
        process_events(app)
        assert_local_page(page)
        assert "找到 2 首歌曲" in page.local_status_label.text()

        page.local_only_checkbox.setChecked(True)
        process_events(app)
        assert page.local_only_checkbox.isChecked()
        assert_local_page(page)
        page.local_only_checkbox.setChecked(False)
        process_events(app)
        assert not page.local_only_checkbox.isChecked()

        page.show_tab("online")
        process_events(app)
        assert_online_page(page)
        assert page.online_results.result_list.count() == 3

        page.set_online_results("没有结果", [], {"final": True})
        process_events(app)
        assert_online_page(page)
        assert page.online_results.result_list.count() == 0

        page.show_tab("local")
        process_events(app)
        assert_local_page(page)

    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    print(
        "search page visibility smoke: OK",
        f"scale={scale}",
        f"devicePixelRatio={page.devicePixelRatioF():.2f}",
    )
    page.hide()
    page.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
