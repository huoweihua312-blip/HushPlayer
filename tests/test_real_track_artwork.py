from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mutagen.id3 import APIC, ID3
from PySide6.QtCore import QBuffer, QCoreApplication, QEvent, QIODevice, QObject, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication

from app.services.local_artwork import LocalArtworkResolver
from app.services.online_artwork_service import OnlineArtworkService
from app.ui_v2.adapters.library_collection import LibraryCollectionAdapter
from app.ui_v2.adapters.online_adapter import OnlineAdapter
from app.ui_v2.adapters.playlist_adapter import PlaylistAdapter
from app.ui_v2.adapters.real_library_adapter import RealLibraryAdapter, _SnapshotThread
from app.ui_v2.widgets.artwork_thumbnail import artwork_pixmap_for_track
from tests.test_ui_v2_online_discovery_q5a import FakeSearchService, FakeSourceClient
from tests.test_ui_v2_real_library_adapter import _snapshot_with_title


def _png(color: str, width: int = 40, height: int = 40) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


class _Reply(QObject):
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.data = b""
        self.aborted = False

    def abort(self) -> None:
        self.aborted = True
        self.finished.emit()

    def error(self):
        return QNetworkReply.NetworkError.NoError

    def readAll(self):
        return self.data

    def finish(self, data: bytes) -> None:
        self.data = data
        self.finished.emit()


class RealTrackArtworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="hushplayer-artwork-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resolver = LocalArtworkResolver(self.root / "cache")

    def _audio(self, name: str = "song.mp3", color: str = "#1ac078") -> Path:
        path = self.root / name
        tags = ID3()
        tags.add(APIC(mime="image/png", type=3, data=_png(color)))
        tags.save(path)
        return path

    def _color(self, path: str | None) -> str:
        self.assertIsNotNone(path)
        image = QImage(str(path))
        self.assertFalse(image.isNull())
        return image.pixelColor(0, 0).name()

    def _cache_online(self, service, url, color="#1ac078") -> bytes:
        data = _png(color)
        path = service.cache_dir / "online"
        path.mkdir(parents=True, exist_ok=True)
        (path / (hashlib.sha256(url.encode()).hexdigest() + ".img")).write_bytes(data)
        return data

    def _adapter(self, service):
        collection = LibraryCollectionAdapter((), read_only=True)
        playlists = PlaylistAdapter(collection, seed_mock=False, read_only=True)
        search = FakeSearchService()
        runtime = SimpleNamespace(
            search_service=search, client=FakeSourceClient(),
            artwork_service=service, bridge=None,
        )
        adapter = OnlineAdapter(collection, playlists, timer_enabled=False, discovery=runtime)
        self.addCleanup(adapter.shutdown)
        self.addCleanup(service.cancel)
        return adapter, search

    def test_local_priority_and_files_remain_unchanged(self) -> None:
        audio = self._audio()
        original = audio.read_bytes()
        explicit = self.root / "bound.png"
        explicit.write_bytes(_png("#e04050"))
        (self.root / "cover.jpg").write_bytes(_png("#3050e0"))
        record = {"path": str(audio), "local_cover_path": str(explicit)}
        self.assertEqual(self._color(self.resolver.resolve(record)), "#e04050")
        self.assertEqual(
            self._color(self.resolver.resolve({"path": str(audio)})), "#1ac078"
        )
        self.assertEqual(audio.read_bytes(), original)
        self.assertEqual(record["local_cover_path"], str(explicit))

    def test_corrupt_explicit_and_embedded_images_fall_back_to_named_sidecar(self) -> None:
        audio = self.root / "corrupt.mp3"
        tags = ID3()
        tags.add(APIC(mime="image/png", type=3, data=b"broken image"))
        tags.save(audio)
        bad = self.root / "bad.png"
        bad.write_bytes(b"invalid")
        (self.root / "Folder.PNG").write_bytes(_png("#3050e0"))
        result = self.resolver.resolve({"path": str(audio), "cover_path": str(bad)})
        self.assertEqual(self._color(result), "#3050e0")

    def test_missing_audio_does_not_select_arbitrary_photograph(self) -> None:
        (self.root / "holiday.png").write_bytes(_png("#e04050"))
        self.assertIsNone(self.resolver.resolve({"path": str(self.root / "missing.mp3")}))
        self.assertIsNone(self.resolver.resolve({"path": "bad\0path.mp3"}))

    def test_embedded_cache_reuse_and_invalid_cache_recovery(self) -> None:
        audio = self._audio()
        record = {"path": str(audio)}
        path = self.resolver.resolve(record)
        self.assertEqual(self._color(path), "#1ac078")
        with patch("app.services.local_artwork.ID3", side_effect=AssertionError("cache missed")):
            fresh = LocalArtworkResolver(self.root / "cache")
            self.assertEqual(fresh.resolve(record), path)
        Path(path).write_bytes(b"corrupt cache")
        fresh = LocalArtworkResolver(self.root / "cache")
        self.assertEqual(self._color(fresh.resolve(record)), "#1ac078")

    def test_front_cover_preferred_and_thumbnails_bounded(self) -> None:
        audio = self.root / "large.mp3"
        tags = ID3()
        tags.add(APIC(mime="image/png", type=4, desc="back", data=_png("#e04050")))
        tags.add(APIC(mime="image/png", type=3, desc="front", data=_png("#1ac078", 1600, 1000)))
        tags.save(audio)
        path = self.resolver.resolve({"path": str(audio)})
        self.assertEqual(self._color(path), "#1ac078")
        self.assertEqual(QImage(path).width(), 768)

    def test_flac_and_mp4_metadata_use_existing_reader(self) -> None:
        for name, metadata in (
            ("song.flac", SimpleNamespace(pictures=[SimpleNamespace(type=3, data=_png("#1ac078"))], tags={})),
            ("song.m4a", SimpleNamespace(tags={"covr": [_png("#1ac078")]})),
        ):
            audio = self.root / name
            audio.write_bytes(b"metadata reader fixture")
            with self.subTest(name=name), patch(
                "app.services.local_artwork.MutagenFile", return_value=metadata
            ):
                self.assertEqual(self._color(self.resolver.resolve({"path": str(audio)})), "#1ac078")

    def test_readonly_cache_preserves_valid_sidecar(self) -> None:
        cover = self.root / "cover.png"
        cover.write_bytes(_png("#1ac078"))
        with patch.object(self.resolver, "_save", return_value=None):
            self.assertEqual(
                self.resolver.resolve({"path": str(self.root / "missing.mp3")}), str(cover)
            )

    def test_worker_mapping_and_shared_renderer_receive_local_cover(self) -> None:
        audio = self._audio()
        snapshot = _snapshot_with_title("Artwork")
        record = dict(snapshot.library.tracks[0], path=str(audio))
        snapshot = replace(snapshot, library=replace(snapshot.library, tracks=(record,)))
        data = RealLibraryAdapter.map_snapshot(snapshot, {}, artwork_resolver=self.resolver)
        track = data.tracks[0]
        self.assertTrue(track.artwork_path)
        self.assertFalse(track.artwork_data)
        self.assertEqual(track.local_path, str(audio))
        for size in (40, 56, 340):
            pixmap = artwork_pixmap_for_track(track, size, size)
            self.assertEqual(pixmap.toImage().pixelColor(0, 0).name(), "#1ac078")

    def test_cover_extraction_runs_in_existing_snapshot_thread(self) -> None:
        audio = self._audio()
        snapshot = _snapshot_with_title("Artwork")
        record = dict(snapshot.library.tracks[0], path=str(audio))
        snapshot = replace(snapshot, library=replace(snapshot.library, tracks=(record,)))
        worker = _SnapshotThread(
            1, SimpleNamespace(load_snapshot=lambda: snapshot),
            SimpleNamespace(load_tracks=lambda: {}),
        )
        worker._artwork_cache_dir = self.root / "cache"
        thread_ids = []
        completed = []
        resolve = LocalArtworkResolver.resolve

        def observed(resolver, record):
            thread_ids.append(threading.get_ident())
            return resolve(resolver, record)

        worker.completed.connect(lambda *args: completed.append(args))
        with patch.object(LocalArtworkResolver, "resolve", observed):
            worker.start()
            self.assertTrue(worker.wait(5000))
            self.app.processEvents()
        self.assertTrue(thread_ids)
        self.assertNotIn(threading.get_ident(), thread_ids)
        self.assertEqual(completed[0][2], "")
        self.assertTrue(completed[0][1].tracks[0].artwork_path)

    def test_cache_hits_reach_adapter_including_results_after_32(self) -> None:
        service = OnlineArtworkService(self.root)
        adapter, search = self._adapter(service)
        url = "https://fixture.invalid/cover.png"
        expected = self._cache_online(service, url)
        adapter.set_query("artwork")
        search.emit_results([
            {"id": str(index), "sourceId": "north", "title": str(index), "artworkUrl": url}
            for index in range(40)
        ])
        for _ in range(20):
            self.app.processEvents()
        self.assertEqual(len(adapter.results()), 40)
        self.assertTrue(all(track.artwork_data == expected for track in adapter.results()))

    def test_new_search_rejects_old_cover_for_same_track(self) -> None:
        service = OnlineArtworkService(self.root)
        adapter, search = self._adapter(service)
        url = "https://fixture.invalid/old.png"
        self._cache_online(service, url)
        adapter.set_query("old")
        raw = {"id": "same", "sourceId": "north", "title": "same", "artworkUrl": url}
        search.emit_results([raw])
        old_generation = service.generation
        key = adapter.results()[0].id
        adapter.set_query("new")
        search.emit_results([dict(raw, artworkUrl="")])
        service.imageReady.emit(old_generation, key, _png("#e04050"))
        self.assertFalse(adapter.results()[0].artwork_data)

    def test_download_queue_is_bounded_and_cancel_discards_pending(self) -> None:
        service = OnlineArtworkService(self.root)
        self.addCleanup(service.cancel)
        replies = []
        ready = []
        service.imageReady.connect(lambda *value: ready.append(value))

        def get(request):
            reply = _Reply()
            replies.append(reply)
            return reply

        with patch.object(service.network, "get", side_effect=get):
            service.request_many([
                (str(index), f"https://fixture.invalid/{index}.png") for index in range(40)
            ])
            self.assertEqual(len(replies), 4)
            for index in range(40):
                replies[index].finish(_png("#1ac078"))
                self.app.processEvents()
                self.assertLessEqual(len(service._replies), 4)
            self.assertEqual(len(ready), 40)
            service.request_many([("x", "https://fixture.invalid/new.png")] * 12)
            service.cancel()
            count = len(replies)
            self.app.processEvents()
            self.assertEqual(len(replies), count)
            self.assertFalse(service._pending)
            self.assertFalse(service._replies)

    def test_metadata_cover_change_replaces_old_cached_cover(self) -> None:
        service = OnlineArtworkService(self.root)
        adapter, search = self._adapter(service)
        old_url = "https://fixture.invalid/old.png"
        new_url = "https://fixture.invalid/new.png"
        self._cache_online(service, old_url)
        expected = self._cache_online(service, new_url, "#e04050")
        adapter.set_query("artwork")
        search.emit_results([{
            "id": "song", "sourceId": "north", "title": "song", "artwork_url": old_url,
        }])
        track = adapter.results()[0]
        adapter.request_metadata(track.id)
        client = adapter.discovery.client
        request_id, source_id, _ = client.metadata_requests[-1]
        client.emit_metadata(request_id, source_id, {"artworkUrl": new_url})
        self.assertEqual(adapter.results()[0].artwork_url, new_url)
        self.assertEqual(adapter.results()[0].artwork_data, expected)

    def test_cancel_search_rejects_delayed_image(self) -> None:
        service = OnlineArtworkService(self.root)
        adapter, search = self._adapter(service)
        adapter.set_query("artwork")
        url = "https://fixture.invalid/cover.png"
        expected = self._cache_online(service, url)
        search.emit_results([{
            "id": "song", "sourceId": "north", "title": "song", "artworkUrl": url,
        }])
        generation = service.generation
        track = adapter.results()[0]
        adapter.cancel_search()
        service.imageReady.emit(generation, track.id, _png("#e04050"))
        self.assertEqual(adapter.results()[0].artwork_data, expected)

    def test_local_artwork_reaches_player_and_details_without_changing_song(self) -> None:
        from app.ui_v2.shell.main_window import MainWindow

        audio = self._audio()
        snapshot = _snapshot_with_title("Artwork")
        record = dict(snapshot.library.tracks[0], path=str(audio))
        snapshot = replace(snapshot, library=replace(snapshot.library, tracks=(record,)))
        track = RealLibraryAdapter.map_snapshot(
            snapshot, {}, artwork_resolver=self.resolver
        ).tracks[0]
        window = MainWindow(data_mode="mock", settings_path=self.root / "settings.json")
        try:
            window.playback_adapter._timer_enabled = False
            window.resize(1200, 800)
            window.show()
            window.playback_adapter.set_queue((track,))
            window.playback_adapter.play_track(track.id)
            window.navigation_adapter.set_route("immersive_now_playing")
            self.app.processEvents()
            shell = window.router.currentWidget()
            for thumbnail in (window.player_bar.artwork, shell.now_playing_page.artwork):
                image = thumbnail._artwork_pixmap.toImage()
                self.assertEqual(image.pixelColor(image.width() // 2, image.height() // 2).name(), "#1ac078")
            self.assertEqual(window.playback_adapter.state.current_track.id, track.id)
            self.assertEqual([item.id for item in window.playback_adapter.queue_tracks], [track.id])
        finally:
            window.close()
            self.app.processEvents()

    def test_invalid_download_keeps_placeholder(self) -> None:
        service = OnlineArtworkService(self.root)
        self.addCleanup(service.cancel)
        failed = []
        ready = []
        service.failed.connect(lambda *value: failed.append(value))
        service.imageReady.connect(lambda *value: ready.append(value))
        reply = _Reply()
        with patch.object(service.network, "get", return_value=reply):
            service.request("x", "https://fixture.invalid/broken.png")
            reply.finish(b"not an image")
        self.assertEqual(len(failed), 1)
        self.assertFalse(ready)

    def test_real_http_download_and_second_request_use_cache(self) -> None:
        expected = _png("#1ac078")
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(expected)))
                self.end_headers()
                self.wfile.write(expected)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        service = OnlineArtworkService(self.root)
        received = []
        service.imageReady.connect(lambda *args: received.append(args))
        url = f"http://127.0.0.1:{server.server_port}/cover.png"
        try:
            service.request("song", url)
            deadline = time.monotonic() + 5
            while not received and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0][2], expected)
            service.request("song", url)
            self.assertEqual(len(received), 2)
            self.assertEqual(hits, ["/cover.png"])
        finally:
            service.cancel()
            service.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            server.shutdown()
            server.server_close()
            thread.join(5)

    def test_separate_library_warmup_does_not_cancel_search(self) -> None:
        search = OnlineArtworkService(self.root)
        library = OnlineArtworkService(self.root)
        self.addCleanup(search.cancel)
        self.addCleanup(library.cancel)
        replies = [_Reply(), _Reply()]
        with patch.object(search.network, "get", return_value=replies[0]), patch.object(
            library.network, "get", return_value=replies[1]
        ):
            search.request("search", "https://fixture.invalid/search.png")
            library.request("library", "https://fixture.invalid/library.png")
            self.assertFalse(replies[0].aborted)
            self.assertEqual(len(search._replies), 1)
            library.cancel()
            self.assertFalse(replies[0].aborted)


if __name__ == "__main__":
    unittest.main()
