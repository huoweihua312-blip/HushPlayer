from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.services.remote_track_store import RemoteTrackStore
from app.services.source_registry import SourceRegistryManager
from app.ui.custom_source_manager_page import CustomSourceManagerPage


class FakeOnlineSourceClient(QObject):
    sourceListReceived = Signal(list)
    requestFailed = Signal(int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self.next_id = 1
        self.reload_calls: list[str] = []

    def list_sources(self, timeout_ms: int = 8000) -> int:
        assert timeout_ms == 8000
        request_id = self.next_id
        self.next_id += 1
        return request_id

    def reload_sources(self, source_id: str = "", timeout_ms: int = 10000) -> int:
        assert timeout_ms == 10000
        self.reload_calls.append(str(source_id or ""))
        request_id = self.next_id
        self.next_id += 1
        return request_id


class SourceHandler(BaseHTTPRequestHandler):
    payloads = {
        "/source_one.js": (
            b"module.exports = { name: 'Open One', search: async () => [], "
            b"getMediaSource: async () => ({url: 'https://example.invalid/audio.ogg'}) };"
        ),
        "/source_two.json": (
            b'{"name":"Open Two","url":"https://example.invalid/audio-two.ogg"}'
        ),
    }

    def do_GET(self) -> None:
        payload = self.payloads.get(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if self.path.endswith(".json") else "application/javascript")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args) -> None:
        return


def wait_until(app: QApplication, predicate, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for Qt network operation")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    server = ThreadingHTTPServer(("127.0.0.1", 0), SourceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="hushplayer_sources_") as temp_dir:
            root = Path(temp_dir)
            registry = SourceRegistryManager(root)
            client = FakeOnlineSourceClient()
            page = CustomSourceManagerPage(registry, client)
            base_url = f"http://127.0.0.1:{server.server_port}"
            js_url = f"{base_url}/source_one.js"
            json_url = f"{base_url}/source_two.json"
            page.url_input.setPlainText(f"{js_url}\n{json_url}\n{js_url}")
            page.confirm_checkbox.setChecked(True)
            urls, errors, duplicates = page.prepare_import_urls(page.url_input.toPlainText())
            assert len(urls) == 2
            assert errors == []
            assert duplicates == 1
            page.start_batch_import()
            wait_until(
                app,
                lambda: page._active_reply is None
                and not page._import_queue
                and page._completed_count == 2,
            )
            sources = registry.list_sources()
            assert len(sources) == 2
            assert all(str(source.get("id") or "").startswith("custom_source_") for source in sources)
            first_id = str(registry.find_by_source_url(js_url)["id"])
            second_id = str(registry.find_by_source_url(json_url)["id"])
            restarted = SourceRegistryManager(root)
            assert restarted.find_by_source_url(js_url)["id"] == first_id
            assert restarted.find_by_source_url(json_url)["id"] == second_id

            page.url_input.setPlainText(f"{js_url}\n{json_url}")
            page.start_batch_import()
            assert len(registry.list_sources()) == 2
            assert "重复" in page.status_label.text()

            runtime_sources = []
            for source in registry.list_sources():
                runtime = dict(source)
                runtime.update({"fileExists": True, "scanError": ""})
                runtime_sources.append(runtime)
            page.on_source_list_received(runtime_sources)
            page.source_list.setCurrentRow(0)
            page.name_input.setText("Renamed Open Source")
            page.save_selected_name()
            assert registry.get_source(first_id)["name"] == "Renamed Open Source"
            page.toggle_selected_source()
            assert registry.get_source(first_id)["enabled"] is False
            registry.set_enabled(first_id, True)

            selected_runtime = dict(registry.get_source(first_id))
            selected_runtime.update({"fileExists": True, "scanError": ""})
            page.on_source_list_received([selected_runtime])
            page.source_list.setCurrentRow(0)
            page.confirm_checkbox.setChecked(True)
            page.update_selected_source()
            wait_until(
                app,
                lambda: page._active_reply is None and not page._import_queue,
            )
            assert page._skipped_count == 1
            assert registry.get_source(first_id)["id"] == first_id

            changed_candidate = registry.stage_bytes(
                SourceHandler.payloads["/source_one.js"] + b"\n// fixture update",
                "source_one.js",
                source_url=js_url,
                content_policy="open",
                user_installed=True,
            )
            registry.update_candidate(first_id, changed_candidate)
            assert registry.get_source(first_id)["name"] == "Renamed Open Source"

            failed_runtime = dict(registry.get_source(first_id))
            failed_runtime.update({"fileExists": True, "scanError": "fixture scan error"})
            page.on_source_list_received([failed_runtime])
            assert "能力检测失败" in page.source_list.item(0).text()
            page._operation_errors[first_id] = "更新失败"
            page.on_source_list_received([failed_runtime])
            assert "更新失败" in page.source_list.item(0).text()

            registry.remove_source(first_id)
            assert registry.get_source(first_id) is None
            assert registry.get_source(second_id) is not None
            stable_id, remote_record = RemoteTrackStore.build_record(
                {
                    "sourceId": first_id,
                    "id": "removed-source-track",
                    "title": "Retained fixture",
                    "artist": "Artist",
                    "album": "Album",
                },
                source_url=js_url,
            )
            unavailable = RemoteTrackStore.to_song_data(
                stable_id,
                remote_record,
                source_available=False,
            )
            assert unavailable["onlineStatus"] == "来源不可用"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print("custom source management smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
