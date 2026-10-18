"""Launch the real application offscreen and capture page screenshots.

Usage:  .venv\\Scripts\\python.exe tools\\shot_app.py [scene ...]
Output: artifacts/shots/<scene>_<mode>.png
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "artifacts" / "shots"
FIXTURES = ROOT / "tests" / "fixtures" / "audio"
TEMP = ROOT / "artifacts" / "tmp_shots"
if os.environ.get("HUSH_OFFSCREEN") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HUSHPLAYER_DATA_DIR"] = str(TEMP / "data")
os.environ["HUSH_CONSOLE"] = "0"

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hushplayer.app import HushApp  # noqa: E402
from hushplayer.core import paths  # noqa: E402
from hushplayer.ui.context import ctx  # noqa: E402



LYRICS_ZH = """[00:00.60]<00:00.60>夜<00:01.00>航<00:01.35>信<00:01.70>号
[00:02.40]<00:02.40>穿<00:02.80>过<00:03.10>无<00:03.45>人<00:03.80>的<00:04.10>跑<00:04.45>道
[00:05.00]<00:05.00>城<00:05.40>市<00:05.75>在<00:06.10>身<00:06.40>后<00:06.70>退<00:07.00>潮
[00:07.60]<00:07.60>我<00:08.00>把<00:08.35>频<00:08.70>率<00:09.05>调<00:09.40>到<00:09.70>最<00:10.00>高
[00:10.80]<00:10.80>听<00:11.10>见<00:11.45>海<00:11.80>的<00:12.10>心<00:12.45>跳
"""

LYRICS_EN = """[00:00.60]Night flight signal
[00:02.40]Running through the empty lanes
[00:05.00]The city ebbing far behind
[00:07.60]I tune the frequency up high
[00:10.80]And hear the ocean's heart
"""


def write_lyrics(media: Path) -> None:
    target = media / "夜航信号" / "01 - 夜航信号.lrc"
    if target.exists():
        return
    target.write_text(LYRICS_ZH, encoding="utf-8")
    target.with_name("01 - 夜航信号.trans.lrc").write_text(LYRICS_EN, encoding="utf-8")
    plain = media / "Long Way Home" / "01 - Long Way Home.lrc"
    plain.write_text(
        "[00:00.80]Long way home\n[00:03.20]Paper lanterns in the rain\n[00:06.20]Every mile a quiet song\n",
        encoding="utf-8",
    )


def prepare_library() -> None:
    media = TEMP / "music"
    media.mkdir(parents=True, exist_ok=True)
    if not any(media.iterdir()):
        shutil.copytree(FIXTURES, media, dirs_exist_ok=True)
    write_lyrics(media)
    library = ctx().library
    files = [str(p) for p in media.rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    result = library.import_files(files)
    print("imported", result.added, "tracks")
    if not library.playlists_all():
        pass
    playlists = [p for p in library.playlists_all() if not p.system]
    if not playlists:
        pid = library.create_playlist("晚间驾驶")
        tracks = library.tracks_page()
        library.add_to_playlist(pid, tracks[:5])
        pid2 = library.create_playlist("深夜代码")
        library.add_to_playlist(pid2, tracks[3:8])
    favorites = library.favorites()
    if not favorites:
        for track in library.tracks_page()[:3]:
            library.set_favorite(track, True)
    library.record_play(library.tracks_page()[1])


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HushPlayer")
    app.setStyle("Fusion")
    hush = HushApp(app)
    hush.start()
    window = hush.window
    window.resize(1280, 820)
    window.show()

    prepare_library()
    playlist_id = next(p.id for p in ctx().library.playlists_all() if not p.system)
    scenes = sys.argv[1:] or [
        "home",
        "songs",
        "albums",
        "artists",
        "favorites",
        "playlist",
        "search",
        "queue",
        "settings",
        "album",
        "artist",
        "lyrics",
    ]
    steps: list[tuple[str, object]] = []
    for scene in scenes:
        if scene == "playlist":
            steps.append((scene, playlist_id))
        elif scene == "search":
            steps.append((scene, "夜"))
        elif scene == "album":
            album = ctx().library.albums()[0]
            steps.append((scene, album.id))
        elif scene == "artist":
            artist = ctx().library.artists()[0]
            steps.append((scene, artist.id))
        else:
            steps.append((scene, None))

    OUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    def pump_until(predicate, timeout_s: float = 25.0) -> bool:
        from PySide6.QtCore import QEventLoop

        import time as _time

        deadline = _time.monotonic() + timeout_s
        while _time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            loop = QEventLoop()
            QTimer.singleShot(120, loop.quit)
            loop.exec()
        return False

    def shoot(scene: str, payload: object, mode: str) -> None:
        hush.settings.set("appearance.theme", mode)
        hush.apply_theme()
        app.processEvents()
        if scene == "queue":
            window.navigate("songs")
            app.processEvents()
            window.queue_panel.open_panel()
            app.processEvents()
        elif scene == "lyrics":
            track = next((item for item in ctx().library.tracks_page() if "夜航" in item.title), None)
            if track is not None and ctx().player.current is not track:
                ctx().player.play_tracks([track], 0, context="专辑 · 夜航信号")
                app.processEvents()
                ctx().player.seek(4200)
                ctx().player.pause()
                app.processEvents()
            window.navigate("lyrics")
            app.processEvents()
        elif scene == "desktop_lyrics":
            track = next((item for item in ctx().library.tracks_page() if "夜航" in item.title), None)
            if track is not None:
                if ctx().player.current is not track:
                    ctx().player.play_tracks([track], 0, context="专辑 · 夜航信号")
                    app.processEvents()
                ctx().player.seek(4200)
                app.processEvents()
            from hushplayer.ui.desktop_lyrics import ensure_desktop_lyrics

            desktop = ensure_desktop_lyrics()
            if desktop is not None:
                desktop.apply_settings()
                desktop.show_lyrics()
                desktop.move(240, 160)
                for _ in range(3):
                    app.processEvents()
                backdrop = QPixmap(desktop.width(), desktop.height())
                backdrop.fill(QColor(26, 27, 32))
                painter = QPainter(backdrop)
                painter.drawPixmap(0, 0, desktop.grab())
                painter.end()
                pixmap = backdrop
        elif scene in ("immersive", "immersive_lyrics"):
            track = next((item for item in ctx().library.tracks_page() if "夜航" in item.title), None)
            if track is not None and ctx().player.current is not track:
                ctx().player.play_tracks([track], 0, context="专辑 · 夜航信号")
                app.processEvents()
                ctx().player.seek(4200)
                ctx().player.pause()
                app.processEvents()
            window.open_immersive()
            app.processEvents()
            immersive = getattr(window, "_immersive", None)
            if immersive is not None:
                immersive.set_mode("lyrics" if scene == "immersive_lyrics" else "cover", animate=False)
                app.processEvents()
        elif scene == "online":
            window.navigate("search")
            app.processEvents()
            page = window._page("search")
            page.segments.set_current(1, emit=True)
            page.field.set_text("周杰伦 晴天")
            page._run_online("周杰伦 晴天", force=True)
            ok = pump_until(lambda: page.online_list.table.model().rowCount() > 0, 30.0)
            print("online rows:", page.online_list.table.model().rowCount(), "ready:", ok)
            app.processEvents()
        elif scene == "narrow":
            window.resize(960, 680)
            window.navigate("songs")
            app.processEvents()
        else:
            window.navigate(scene, payload)
            app.processEvents()
        index = 0
        while index < 6:
            app.processEvents()
            index += 1
        path = OUT / f"{scene}_{mode}.png"
        pixmap = None if scene == "desktop_lyrics" else window.grab()
        if pixmap is None:
            pixmap = backdrop
        if scene in ("immersive", "immersive_lyrics"):
            immersive = getattr(window, "_immersive", None)
            if immersive is not None:
                # The window is translucent; the first grab can happen before the
                # ambient background has painted, which renders as a washed-out
                # frame. Force one full repaint and discard that grab.
                immersive.repaint()
                app.processEvents()
                immersive.grab()
                app.processEvents()
                pixmap = immersive.grab()
        ok = pixmap.save(str(path))
        print(("saved " if ok else "FAILED ") + path.name, pixmap.width(), "x", pixmap.height())
        if scene == "narrow":
            window.resize(1280, 820)
            app.processEvents()
        if not ok:
            errors.append(path.name)

    state = {"i": 0, "mode": "dark", "busy": False}

    def tick() -> None:
        if state["busy"]:
            return
        index = state["i"]
        if index >= len(steps) * 2:
            app.quit()
            return
        state["busy"] = True
        scene, payload = steps[index // 2]
        mode = "dark" if index % 2 == 0 else "light"
        try:
            shoot(scene, payload, mode)
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            errors.append(f"{scene}:{exc}")
        state["i"] += 1
        state["busy"] = False
        QTimer.singleShot(260, tick)

    QTimer.singleShot(700, tick)
    code = app.exec()
    try:
        hush.shutdown()
    except Exception as exc:  # noqa: BLE001
        print("shutdown:", exc)
    print("errors:", errors)
    return code


if __name__ == "__main__":
    raise SystemExit(run())
