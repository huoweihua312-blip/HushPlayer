from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app.services.online_download_manager import OnlineDownloadManager
from app.services.online_source_client import OnlineSourceClient
from app.services.source_registry import SourceRegistryManager
from app.ui.online_source_pages import OnlineSearchPage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_ROOT = PROJECT_ROOT / "source_runtime" / "sources" / "staging"
TEST_ROOT = STAGING_ROOT / f"hushplayer_qprocess_{os.getpid()}"


def wait_until(predicate, timeout_ms: int = 5000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def prepare_fixture() -> Path:
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    plugin_path = TEST_ROOT / "open_fixture.js"
    plugin_path.write_text(
        """module.exports = {
            resolvePlayback: async (track) => {
                await new Promise((resolve) => setTimeout(resolve, Number(track.delay || 0)));
                if (track.fail) throw new Error("fixture failure");
                return { url: `http://127.0.0.1:8765/${track.id}.mp3`, headers: {} };
            }
        };\n""",
        encoding="utf-8",
    )
    registry_path = TEST_ROOT / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "open_fixture",
                        "name": "Open fixture",
                        "filename": plugin_path.relative_to(PROJECT_ROOT / "source_runtime").as_posix(),
                        "enabled": True,
                        "contentPolicy": "open",
                        "capabilities": {"playback": True, "download": False},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry_path


def test_qprocess_client(app: QApplication, registry_path: Path) -> None:
    os.environ["HUSHPLAYER_SOURCE_REGISTRY"] = str(registry_path)
    client = OnlineSourceClient(PROJECT_ROOT)
    resolved: list[tuple[int, dict]] = []
    failures: list[tuple[int, str, str]] = []
    stopped: list[bool] = []
    client.playbackResolved.connect(lambda request_id, _source, data: resolved.append((request_id, data)))
    client.requestFailed.connect(lambda request_id, action, message: failures.append((request_id, action, message)))
    client.processStopped.connect(lambda: stopped.append(True))
    assert client.start()
    assert wait_until(client.is_running)

    old_id = client.resolve_playback("open_fixture", {"id": "old", "delay": 250})
    current_id = client.resolve_playback("open_fixture", {"id": "current", "delay": 10})
    assert client.cancel_request(old_id)
    assert wait_until(lambda: any(item[0] == current_id for item in resolved))
    assert not any(item[0] == old_id for item in resolved)
    assert resolved[-1][1]["url"].endswith("/current.mp3")

    error_id = client.resolve_playback("open_fixture", {"id": "error", "fail": True})
    assert wait_until(lambda: any(item[0] == error_id for item in failures))
    timeout_id = client.resolve_playback(
        "open_fixture",
        {"id": "timeout", "delay": 1800},
        timeout_ms=1000,
    )
    assert wait_until(lambda: any(item[0] == timeout_id for item in failures), 3000)
    assert "超时" in next(item[2] for item in failures if item[0] == timeout_id)

    client.stop()
    assert wait_until(lambda: bool(stopped))
    assert not client.is_running()
    client.deleteLater()
    app.processEvents()


def test_search_page_signals() -> None:
    client = OnlineSourceClient(PROJECT_ROOT)
    page = OnlineSearchPage(client)
    emitted: list[dict] = []
    page.play_requested.connect(emitted.append)

    unsupported = QListWidgetItem("unsupported")
    unsupported.setData(
        Qt.ItemDataRole.UserRole,
        {"sourceId": "closed", "id": "1", "capabilities": {"playback": False}},
    )
    page.request_playback(unsupported)
    assert not emitted
    assert "未启用播放能力" in page.status_label.text()

    supported = QListWidgetItem("supported")
    supported.setData(
        Qt.ItemDataRole.UserRole,
        {"sourceId": "open", "id": "2", "capabilities": {"playback": True}},
    )
    page.request_playback(supported)
    assert len(emitted) == 1
    assert "正在获取播放地址" in page.status_label.text()
    page.deleteLater()
    client.deleteLater()


def test_download_manager() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_download_") as temp_dir:
        root = Path(temp_dir)
        payload = b"RIFF" + b"\x00" * 4092
        (root / "fixture.wav").write_bytes(payload)

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, _format: str, *args) -> None:
                pass

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(QuietHandler, directory=str(root)),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            manager = OnlineDownloadManager()
            finished: list[str] = []
            failures: list[str] = []
            manager.finished.connect(finished.append)
            manager.failed.connect(failures.append)
            target = root / "saved.wav"
            assert manager.start_download(
                {"url": f"http://127.0.0.1:{server.server_port}/fixture.wav", "headers": {}},
                str(target),
            )
            assert wait_until(lambda: bool(finished or failures))
            assert not failures
            assert target.read_bytes() == payload

            assert not manager.start_download(
                {
                    "url": f"http://127.0.0.1:{server.server_port}/fixture.wav",
                    "headers": {"Authorization": "secret"},
                },
                str(root / "blocked.wav"),
            )
            assert "附加请求头" in failures[-1]
            assert not (root / "blocked.wav").exists()
            manager.deleteLater()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_js_and_json_import_capabilities() -> None:
    with tempfile.TemporaryDirectory(prefix="hushplayer_registry_") as temp_dir:
        root = Path(temp_dir)
        manager = SourceRegistryManager(root)
        code = (
            b"module.exports = { resolvePlayback: async () => ({url: 'https://example.invalid/a.mp3'}), "
            b"resolveDownload: async () => ({url: 'https://example.invalid/a.mp3'}) };"
        )
        raw_candidate = manager.stage_bytes(code, "raw_source.js")
        assert raw_candidate["contentPolicy"] == "unknown"
        assert raw_candidate["capabilities"]["playback"] is False
        assert raw_candidate["capabilities"]["download"] is False

        user_sources = root / "user_sources"
        user_sources.mkdir(parents=True)
        (user_sources / "open_source.js").write_bytes(code)
        manifest = {
            "id": "open_source",
            "name": "Open source",
            "filename": "../user_sources/open_source.js",
            "contentPolicy": "open",
            "capabilities": {"playback": True, "download": True},
        }
        manifest_candidate = manager.stage_bytes(
            json.dumps(manifest).encode("utf-8"),
            "open_source.json",
        )
        assert manifest_candidate["capabilities"]["playback"] is True
        assert manifest_candidate["capabilities"]["download"] is True


def test_main_window_online_entry() -> None:
    from app.ui.main_window import MainWindow

    original_initialize = MainWindow.initialize_online_source_framework
    original_restore = MainWindow.restore_playback_session
    MainWindow.initialize_online_source_framework = lambda self: None
    MainWindow.restore_playback_session = lambda self: None
    try:
        window = MainWindow()
        track = {
            "sourceId": "open_fixture",
            "id": "fixture",
            "title": "Online fixture",
            "artist": "Test artist",
            "album": "Test album",
        }
        preserved_context = {"kind": "library", "ordered_paths": ["C:/music/local.mp3"]}
        window.current_song_path = "C:/music/local.mp3"
        window.playback_context = preserved_context
        window.pending_online_track = dict(track)
        window.pending_online_playback_request = 71
        window.on_online_playback_resolved(
            71,
            "open_fixture",
            {"url": "http://127.0.0.1:8765/header.mp3", "headers": {"Referer": "x"}},
        )
        assert window.current_song_path == "C:/music/local.mp3"
        assert window.current_track_kind == "local"
        assert "附加请求头" in window.online_search_page.status_label.text()

        window.pending_online_track = dict(track)
        window.pending_online_playback_request = 72
        window.on_online_playback_resolved(
            72,
            "open_fixture",
            {"url": "http://127.0.0.1:8765/audio.mp3", "headers": {}},
        )
        assert window.current_track_kind == "online"
        assert window.current_song_path is None
        assert window.current_online_track == track
        assert window.playback_context is preserved_context
        assert window.media_player.source().toString().startswith("http://127.0.0.1:8765/")
        window.media_player.stop()
        window.online_source_client.stop()
        window.deleteLater()
        QApplication.processEvents()
    finally:
        MainWindow.initialize_online_source_framework = original_initialize
        MainWindow.restore_playback_session = original_restore


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    registry_path = prepare_fixture()
    try:
        test_qprocess_client(app, registry_path)
        test_search_page_signals()
        test_download_manager()
        test_js_and_json_import_capabilities()
        test_main_window_online_entry()
        print("online playback QProcess/UI smoke: OK")
        return 0
    finally:
        resolved_root = TEST_ROOT.resolve()
        resolved_staging = STAGING_ROOT.resolve()
        if resolved_root.parent == resolved_staging and resolved_root.name.startswith("hushplayer_qprocess_"):
            shutil.rmtree(resolved_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
